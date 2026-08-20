# XAUUSD Historical Data

XAUUSD (Gold vs USD) 1-minute historical data pipeline and analysis tools.
Data source: Exness MT5 (`XAUUSDm`), 28 April 2017 → August 2026, 3,276,127 bars.
Every row is a genuine 1-minute candle (sparse pre-M1 rows before 2017-04-28
have been removed).

## Files

| File | Description |
|---|---|
| `fetch_xauusd_m1.py` | Downloads M1 bars from a running MetaTrader 5 terminal, cleans them (dedupe, OHLC validation, gap report), saves CSV/Parquet |
| `find_unreturned_prices.py` | Finds price levels the market never returned to, groups them into zones with width/spacing (adjustable time window and grid step) |
| `xauusd_m1_full.parquet` | Full cleaned M1 dataset (3,277,893 bars, 2017-2026) |
| `xauusd_d1_daily.csv` | Daily candles resampled from M1 (2,951 rows) |
| `xauusd_unreturned_levels.csv` | Every $1 price level with last-touch date and days-not-returned |
| `xauusd_unreturned_zones.csv` | Un-returned zones for the 300-700 day window |
| `xauusd_explorer.html` | Self-contained interactive candlestick chart (open in a browser) |

The full M1 CSV (235 MB) is not committed — it exceeds GitHub's 100 MB file
limit. Regenerate it from the Parquet file:

```python
import pandas as pd
pd.read_parquet("xauusd_m1_full.parquet").to_csv("xauusd_m1_full.csv")
```

## Refresh the data

Requires Windows, a logged-in MetaTrader 5 terminal, and `pip install MetaTrader5 pandas pyarrow`:

```powershell
python fetch_xauusd_m1.py --symbol XAUUSDm --start 2017-01-01 --out xauusd_m1_full.parquet
```

Timestamps are Exness server time (UTC-labelled). The dataset starts
2017-04-28, the first date with full minute coverage; a re-fetch will
re-download the sparse earlier rows, so re-trim if you refresh.
