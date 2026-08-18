"""
Find "un-returned" prices in XAUUSD history: price levels the market touched,
left, and never came back to — and the spacing between them.

Method:
  1. Build a grid of price levels (default every $1) across the full data range.
  2. For each level, find the LAST bar whose low-high range touched it
     (H1 bars are used — their highs/lows fully cover the M1 data).
  3. days_not_returned = days between that last touch and the end of the data.
  4. Filter levels by a time window (e.g. not returned for 300-700 days,
     counted back from the end), group consecutive levels into ZONES,
     and report each zone's width and the gap (spacing) to the next zone.

Outputs (in this folder):
  xauusd_unreturned_levels.csv  — every level: last touch time, touches, days
  xauusd_unreturned_zones.csv   — filtered zones: range, width, spacing, dates

Usage:
  python find_unreturned_prices.py                     # 300-700 day window
  python find_unreturned_prices.py --min-days 100 --max-days 99999
  python find_unreturned_prices.py --step 0.5
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

SRC = r"c:\Users\Sherwyn joel\OneDrive\Desktop\historical data\xauusd_m1_full.parquet"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=float, default=1.0, help="price grid step in dollars (default 1.0)")
    ap.add_argument("--min-days", type=float, default=300, help="min days not returned (default 300)")
    ap.add_argument("--max-days", type=float, default=700, help="max days not returned (default 700)")
    args = ap.parse_args()

    df = pd.read_parquet(SRC).loc["2017-05":]
    h1 = df.resample("1h").agg({"high": "max", "low": "min"}).dropna()
    highs, lows = h1.high.values, h1.low.values
    times = h1.index
    end_time = df.index.max()
    print(f"Data: {df.index.min():%Y-%m-%d} -> {end_time:%Y-%m-%d %H:%M}  ({len(h1)} H1 bars)")

    lo_edge = np.floor(lows.min())
    hi_edge = np.ceil(highs.max())
    levels = np.arange(lo_edge, hi_edge + args.step, args.step)
    print(f"Scanning {len(levels)} price levels from {lo_edge:.0f} to {hi_edge:.0f} "
          f"(step {args.step})...")

    last_idx = np.empty(len(levels), dtype=np.int64)
    n_touch = np.empty(len(levels), dtype=np.int64)
    for i, p in enumerate(levels):
        mask = (lows <= p) & (highs >= p)
        n_touch[i] = int(mask.sum())
        last_idx[i] = int(np.flatnonzero(mask)[-1]) if n_touch[i] else -1

    touched = last_idx >= 0
    last_time = pd.DatetimeIndex([times[j] if j >= 0 else pd.NaT for j in last_idx], tz="UTC")
    days_since = np.where(touched, (end_time - last_time).total_seconds() / 86400, np.nan)

    out = pd.DataFrame({
        "level": np.round(levels, 2),
        "touches_h1": n_touch,
        "last_touch": last_time,
        "days_not_returned": np.round(days_since, 1),
    })
    out = out[out.touches_h1 > 0]
    lv_path = r"c:\Users\Sherwyn joel\OneDrive\Desktop\historical data\xauusd_unreturned_levels.csv"
    out.to_csv(lv_path, index=False)
    print(f"Wrote {len(out)} levels -> {lv_path}")

    # ---- filter window and group consecutive levels into zones -------------
    sel = out[(out.days_not_returned >= args.min_days)
              & (out.days_not_returned <= args.max_days)].reset_index(drop=True)
    print(f"\nLevels not returned for {args.min_days:g}-{args.max_days:g} days: {len(sel)}")

    zones = []
    if len(sel):
        brk = np.flatnonzero(np.diff(sel.level.values) > args.step * 1.5)
        starts = np.r_[0, brk + 1]
        ends = np.r_[brk, len(sel) - 1]
        for a, b in zip(starts, ends):
            seg = sel.iloc[a:b + 1]
            zones.append({
                "zone_low": seg.level.iloc[0],
                "zone_high": seg.level.iloc[-1],
                "width_$": round(seg.level.iloc[-1] - seg.level.iloc[0] + args.step, 2),
                "last_touch_earliest": seg.last_touch.min(),
                "last_touch_latest": seg.last_touch.max(),
                "days_not_returned_min": seg.days_not_returned.min(),
                "days_not_returned_max": seg.days_not_returned.max(),
            })
    zdf = pd.DataFrame(zones)
    if len(zdf):
        nxt = zdf.zone_low.shift(-1)
        zdf["spacing_to_next_zone_$"] = (nxt - zdf.zone_high).round(2)
    zn_path = r"c:\Users\Sherwyn joel\OneDrive\Desktop\historical data\xauusd_unreturned_zones.csv"
    zdf.to_csv(zn_path, index=False)
    print(f"Zones found: {len(zdf)} -> {zn_path}\n")
    if len(zdf):
        with pd.option_context("display.width", 160, "display.max_rows", 100):
            print(zdf.to_string(index=False))


if __name__ == "__main__":
    main()
