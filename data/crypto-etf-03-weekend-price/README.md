# Crypto ETF weekend price study

This directory contains the frozen results used by `articles/crypto-etf-03-weekend-gap.md`.

## Files

- `all-weekends-scan.csv`: all 122 Friday-to-Monday pairs, sorted by absolute BTC return
- `top-weekend-cases.csv`: exact comparison data for the three largest BTC moves
- `../../images/crypto-etf-03-weekend-price/`: figures generated from the top-case CSV data

## Method

- Window: IBIT launch through 2026-09-15; only consecutive Friday-to-Monday pairs
  with three calendar days between the dates are included.
- BTC: Coinbase Exchange `BTC-USD` five-minute candles. Use the open of the candle
  beginning Friday 16:00 ET and Monday 09:30 ET.
- IBIT: Nasdaq historical daily OHLC. Use unadjusted Friday close and Monday open.
- Returns: `end / start - 1`.
- Residual: `(IBIT Monday open / IBIT Friday close - 1) - BTC weekend return`,
  expressed in percentage points. This is not a premium/discount calculation.
- Time zone: `America/New_York`, including daylight-saving transitions.
- Retrieved: 2026-09-16.

## Reproduce

From the repository root:

```bash
uv run --with pandas==2.2.3 --with matplotlib==3.10.5 python analysis/crypto_etf_weekend_gap.py
```

The script queries Nasdaq's historical data endpoint and Coinbase Exchange's public
candles endpoint, writes both CSV files, and regenerates the figures.
