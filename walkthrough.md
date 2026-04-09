# Upstox Expired Options Sync Walkthrough

## What Was Added

- `services/data_collector/scripts/upstox_options_sync.py` implements the historical Upstox options sync flow.
- `packages/trading_core/trading_core/providers/upstox_historical.py` now uses the documented expired-instruments expiry and contract endpoints.
- `packages/trading_core/trading_core/__init__.py` and `packages/trading_core/trading_core/providers/__init__.py` now use lazy imports so standalone Upstox scripts do not pull unrelated Fyers dependencies at import time.

## Sync Flow

1. Load historical expiries for the configured underlying from Upstox.
2. Query `broker_upstox.ohlcv_1m` for all trading days that have a `09:15:00` spot candle.
3. For each trading day, round the spot open to the nearest 50-point ATM strike.
4. Select active expiries within a configurable forward window.
5. For each active expiry, resolve a 43-symbol contract set:
   - 21 PE strikes below ATM
   - 1 ATM contract using `--atm-option-type`
   - 21 CE strikes above ATM
6. Download 1-minute expired-contract candles from Upstox with async rate limiting.
7. Upsert the results into `broker_upstox.options_ohlc`.

## CLI Usage

Example dry run:

```powershell
d:/SID/sid_projects/trading/trading_ecosystem/.venv/Scripts/python.exe services/data_collector/scripts/upstox_options_sync.py --start-date 2025-04-16 --end-date 2025-04-16 --limit-days 1 --max-expiries-per-day 1 --dry-run --verbose
```

Example write run:

```powershell
d:/SID/sid_projects/trading/trading_ecosystem/.venv/Scripts/python.exe services/data_collector/scripts/upstox_options_sync.py --start-date 2025-04-16 --end-date 2025-04-16 --limit-days 1 --max-expiries-per-day 1 --verbose
```

## Notes

- Upstox historical expiries currently cover a bounded historical window, so dates outside that returned expiry set are skipped.
- Validation on `2025-04-16` with one active expiry wrote `16,125` rows and produced `43` symbols for each of `375` one-minute bars.