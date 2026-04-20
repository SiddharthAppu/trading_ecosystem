# Upstox Historical Options Downloader: User Guide

Welcome to the Upstox Historical Options Downloader. This module automates the mass-downloading of expired 1-minute historical OHLC option candles directly from the Upstox API and stores them efficiently in your TimescaleDB database. 

## 1. Core Logic & "ATM Tracking" Strategy
To prevent downloading terabytes of useless OTM data, this system utilizes an **ATM Tracking** strategy:
1. It queries the historical spot price of the underlying asset (`NSE:NIFTY50-INDEX`) at market open (09:15 AM) on every trade date.
2. It rounds that spot price to the nearest strike step (e.g., Strike step 50 for NIFTY). This becomes the precise **ATM Strike**.
3. It maps exactly **43 option contracts**:
   - The primary ATM Strike (defaults to CE).
   - 21 CE (Call) contracts above the ATM strike.
   - 21 PE (Put) contracts below the ATM strike.
4. It iterates this across all expiries active within a rolling `35-day window` of the trade date.

## 2. Prerequisites
Before running the download script, ensure the following are active:
* **The PostgreSQL/TimescaleDB Database:** Ensure your Database container is running locally (`broker_upstox.options_ohlc` and `broker_upstox.ohlcv_1m` must exist).
* **Upstox Authorization:** The scripts require a valid, non-expired API bearer token. Ensure you have authorized via `authenticate.py` or the platform auth service.

## 3. How to Run the Downloader (`upstox_options_sync.py`)

The primary orchestration script is located at:
`services/data_collector/scripts/upstox_options_sync.py`

### Basic Syntax
```bash
python services/data_collector/scripts/upstox_options_sync.py --start-date 2024-01-01 --end-date 2024-01-31
```

### Advanced Flags & CLI Options
You can heavily customize the pipeline using the flags below:
* `--start-date` **(Required)**: Start date in YYYY-MM-DD.
* `--end-date` **(Required)**: End date in YYYY-MM-DD.
* `--underlying-symbol`: Base index/script to use for tracking the ATM Spot. (Default: `NSE:NIFTY50-INDEX`).
* `--expiry-window-days`: How many real-time days ahead to view an expiry as "active". (Default: `35`).
* `--max-expiries-per-day`: Put a hard cap on how many expiries are fetched per day (Default `0` for no cap).
* `--limit-days`: A developer tool to cap total days fetched (useful for small testing).
* `--dry-run`: Will run the entire logic engine, mapping ATM strikes and calculating expiries, but will **not** trigger any live API downloads or Database commits.
* `--verbose`: Turn on heavy debug logging.

## 4. API Throttling & Rate Limit Protections
The Upstox historical endpoints (`/v2/expired-instruments/historical-candle...`) are deeply protected by strict rate limiters.
This module has built-in protections:
1. **Paced Firing:** Network requests are rigidly staggered at `~2.85` requests per second.
2. **The 400ms Rule:** A mandatory `0.4s` sleep is injected after every single outbound GET request.
3. **Ghost Limit Checking:** Upstox occasionally throttles by returning `Status 200` but yielding an empty `{}` candle array. The script specifically scans for this edge case.
4. **Retry Loop:** Upon detecting throttling or ghost limits, the system pauses execution for 5 seconds and loops a retry (up to 3 times per batch). If it fully exhausts, an integrity `[ERROR]` is printed.

## 5. Built-in Integrity Logging
You will see explicit Integrity outputs as your data pulls happen:
> `Fetched 375 rows for NIFTY24APR22000CE. Expected 375. Match: OK.`

This verifies that not only did the API respond, but it yielded an absolutely complete 1-minute time series block (375 minutes in a trading day). If short, it will flag `MISMATCH`. 

## 6. Post-Download Validation (`audit_upstox_options.py`)

No matter how robust the logic is, you must verify large data pulls. A standalone script is provided just for this purpose.

**How to Audit:**
```bash
python services/data_collector/scripts/audit_upstox_options.py --samples 15
```

**How it Works:** 
It plucks exactly 15 truly random historical entries that have already been saved to your local `options_ohlc` database. It dynamically queries Upstox's live API servers one last time for that exact contract key on that exact timestamp and forcefully asserts that the row counts downloaded live structurally match what is sitting offline in your database. 
