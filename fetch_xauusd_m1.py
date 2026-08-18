"""
Fetch and clean XAUUSD 1-minute historical data into a Pandas DataFrame.

Primary source: MetaTrader 5 (official `MetaTrader5` Python package).
    Requires the MT5 desktop terminal installed and logged in to a broker
    account whose Market Watch includes the symbol (e.g. "XAUUSD").

    pip install MetaTrader5 pandas

cTrader: cTrader's Open API needs a registered app (client id/secret),
    an OAuth access token, and a protobuf-over-TCP session — see the
    CTraderFetcher stub at the bottom for what plugging it in looks like.

Usage:
    python fetch_xauusd_m1.py                          # last 30 days
    python fetch_xauusd_m1.py --start 2024-01-01 --end 2024-06-30
    python fetch_xauusd_m1.py --symbol XAUUSD.a --out xauusd_m1.parquet
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

CHUNK_DAYS = 30  # fetch window per request; keeps each call well under terminal bar limits


class MT5Fetcher:
    """Fetches M1 bars from a running MetaTrader 5 terminal."""

    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = symbol

    def __enter__(self):
        import MetaTrader5 as mt5

        self.mt5 = mt5
        if not mt5.initialize():
            raise ConnectionError(
                f"MT5 initialize() failed: {mt5.last_error()}. "
                "Is the MetaTrader 5 terminal installed and logged in?"
            )
        if not mt5.symbol_select(self.symbol, True):
            mt5.shutdown()
            raise ValueError(
                f"Symbol {self.symbol!r} not found on this broker. "
                "Check the exact name in Market Watch (brokers use suffixes like XAUUSD.a)."
            )
        return self

    def __exit__(self, *exc):
        self.mt5.shutdown()
        return False

    def fetch_m1(self, start: datetime, end: datetime) -> pd.DataFrame:
        """Fetch raw M1 bars for [start, end) in chunks; returns the raw concatenated frame."""
        mt5 = self.mt5
        frames = []
        cursor = start
        while cursor < end:
            chunk_end = min(cursor + timedelta(days=CHUNK_DAYS), end)
            rates = mt5.copy_rates_range(
                self.symbol, mt5.TIMEFRAME_M1, cursor, chunk_end
            )
            if rates is None:
                raise RuntimeError(
                    f"copy_rates_range failed for {cursor:%Y-%m-%d}..{chunk_end:%Y-%m-%d}: "
                    f"{mt5.last_error()}"
                )
            n = 0
            if len(rates):
                chunk = pd.DataFrame(rates)
                # For ranges predating available history, MT5 can echo a single
                # bar stamped OUTSIDE the requested window — keep in-range bars only.
                chunk = chunk[(chunk["time"] >= cursor.timestamp())
                              & (chunk["time"] < chunk_end.timestamp())]
                n = len(chunk)
                if n:
                    frames.append(chunk)
            print(f"  fetched {cursor:%Y-%m-%d} -> {chunk_end:%Y-%m-%d}: {n:>7} bars")
            cursor = chunk_end
        if not frames:
            raise RuntimeError(
                "No bars returned. The terminal may not hold history that far back — "
                "raise 'Max bars in chart' in MT5 Tools > Options > Charts and retry."
            )
        return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------

def clean_m1(raw: pd.DataFrame, report_gaps: bool = True) -> pd.DataFrame:
    """
    Clean raw MT5 M1 bars into an analysis-ready DataFrame.

    Steps:
      1. Epoch seconds -> UTC DatetimeIndex named 'time'.
         (MT5 stamps bars in *broker server time*; treat tz consistently downstream.)
      2. Keep and order OHLCV columns.
      3. Drop duplicate timestamps (chunk boundaries overlap) and sort.
      4. Drop rows with non-positive prices or missing values.
      5. Drop rows violating OHLC integrity (high must be the max, low the min).
      6. Report intra-week minute gaps (weekend closure is expected and not flagged).
    """
    df = raw.copy()
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time")

    cols = ["open", "high", "low", "close", "tick_volume", "spread", "real_volume"]
    df = df[[c for c in cols if c in df.columns]]

    before = len(df)
    df = df[~df.index.duplicated(keep="first")].sort_index()
    dupes = before - len(df)

    price_cols = ["open", "high", "low", "close"]
    valid = df[price_cols].notna().all(axis=1) & (df[price_cols] > 0).all(axis=1)
    bad_price = int((~valid).sum())
    df = df[valid]

    integrity = (
        (df["high"] >= df[["open", "close"]].max(axis=1))
        & (df["low"] <= df[["open", "close"]].min(axis=1))
        & (df["high"] >= df["low"])
    )
    bad_ohlc = int((~integrity).sum())
    df = df[integrity]

    print(f"Cleaning: dropped {dupes} duplicates, {bad_price} bad-price rows, "
          f"{bad_ohlc} OHLC-integrity violations -> {len(df)} bars")

    if report_gaps and len(df) > 1:
        deltas = df.index.to_series().diff().dropna()
        gaps = deltas[deltas > pd.Timedelta(minutes=1)]
        # Ignore gaps that span the Fri-close -> Sun/Mon-open weekend break.
        intra_week = gaps[~gaps.index.dayofweek.isin([6, 0]) | (gaps < pd.Timedelta(hours=2))]
        if len(intra_week):
            worst = intra_week.sort_values(ascending=False).head(5)
            print(f"Note: {len(intra_week)} intra-week gaps > 1 min (missing bars are normal "
                  "in quiet minutes with no ticks). Largest:")
            for ts, gap in worst.items():
                print(f"    {ts}  gap {gap}")

    return df


# ---------------------------------------------------------------------------
# cTrader stub
# ---------------------------------------------------------------------------

class CTraderFetcher:
    """
    Placeholder for cTrader Open API.

    To implement: register an app at https://openapi.ctrader.com to get a
    client id/secret, obtain an OAuth access token for your trading account,
    then use the `ctrader-open-api` package (Twisted-based) to send
    ProtoOAGetTrendbarsReq messages with period=M1 and page through
    from/to timestamps. Map the returned trendbars (delta-encoded ticks)
    into the same raw columns MT5Fetcher produces, and reuse clean_m1().
    """

    def __init__(self, *a, **kw):
        raise NotImplementedError(self.__doc__)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch and clean XAUUSD M1 bars from MT5.")
    p.add_argument("--symbol", default="XAUUSD", help="broker symbol name (default XAUUSD)")
    p.add_argument("--start", type=lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc),
                   default=None, help="start date YYYY-MM-DD (default: 30 days ago)")
    p.add_argument("--end", type=lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc),
                   default=None, help="end date YYYY-MM-DD (default: now)")
    p.add_argument("--out", default="xauusd_m1.csv",
                   help="output file: .csv or .parquet (default xauusd_m1.csv)")
    p.add_argument("--source", choices=["mt5", "ctrader"], default="mt5")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    end = args.end or datetime.now(timezone.utc)
    start = args.start or end - timedelta(days=30)
    if start >= end:
        print("error: --start must be before --end", file=sys.stderr)
        return 2

    fetcher_cls = MT5Fetcher if args.source == "mt5" else CTraderFetcher
    print(f"Fetching {args.symbol} M1 bars {start:%Y-%m-%d} -> {end:%Y-%m-%d} via {args.source}...")
    with fetcher_cls(args.symbol) as fetcher:
        raw = fetcher.fetch_m1(start, end)

    df = clean_m1(raw)
    print(df.head())
    print(df.tail())

    if args.out.endswith(".parquet"):
        df.to_parquet(args.out)
    else:
        df.to_csv(args.out)
    print(f"Saved {len(df)} bars to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
