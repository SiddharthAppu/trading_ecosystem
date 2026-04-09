# Upstox Historical Options Data Downloader

## Goal
To implement an iterative, daily workflow for downloading 1-minute historical data for all expired Nifty 50 option contracts. Based on the user's feedback, we will leverage our existing Nifty 50 spot data instead of downloading it from scratch, and we will iteratively find the available expiries, compute the ATM dynamically from our local database, determine the relevant symbols for each trading day, and download all active option contracts for those dates.

## User Review Required

> [!IMPORTANT]
> **Approval Needed**: Please review this updated iterative plan.
> It looks like you already have a `broker_upstox.options_ohlc` table set up, and plenty of data in `broker_upstox.ohlcv_1m` and `broker_fyers.ohlcv_1m`. 
> I have answered your questions below and updated the workflow. Let me know if you approve this approach!

**Answering your Questions:**
1. *"what do you mean by symbol mapper?"*
   - Because the Upstox Historical Candle API requires a specific internal `instrument_key` (like `NSE_FO|73507|24-04-2025`), a "symbol mapper" is simply a Python helper function that converts our requirements (e.g., "Nifty 22450 CE for April 24") into the exact `instrument_key` that Upstox expects so we can actually build the download URL.
2. *"how do we plan to ingest this? we already have..."*
   - You are totally right! I verified the local database and found `580,367` rows in `broker_fyers.ohlcv_1m` and `275,166` rows in `broker_upstox.ohlcv_1m`. Instead of re-downloading spot data, we will simply query our own TimescaleDB to grab the `09:15:00` Open price for any given day.

## Proposed Iterative Workflow

Instead of one massive bulk process, we will do this day-by-day:

### [NEW] `services/data_collector/scripts/upstox_options_sync.py`
This will be our main orchestrator script that runs the following iterative loop:

1. **Get Available Expiries**: 
   - Call Upstox `GET /v2/expired-instruments/metadata/expiries` to determine exactly which Nifty 50 expiry dates exist historically. (This perfectly handles the historical shift from Thursdays to Tuesdays without us needing to hardcode anything!)
2. **Iterate Trading Days**:
   - For all valid trading days in the available expiry windows (we get the valid trading days simply by SELECTing distinct dates from our `broker_upstox.ohlcv_1m` table, which automatically skips all market holidays):
3. **Lookup Spot locally**:
   - Query our TimescaleDB (`broker_upstox.ohlcv_1m` table) for the Nifty 50 Open price at exactly `09:15 AM` on that specific day.
4. **Determine Target Strikes for ALL Active Expiries**:
   - For a given trading day, identify *all* expiries that are currently active (e.g., current week, next week, etc.).
   - Calculate the ATM strike: `round(Spot / 50) * 50`.
   - For *each* active expiry on that day, identify 43 relevant target strikes (Spot + 21 CE + 21 PE). So if 3 different expiries are active today, we will have 3 * 43 = 129 targets.
5. **Map to Instrument Keys**:
   - Use the `GET /v2/expired-instruments/option/contract` API to convert those 43 targets into valid Upstox `instrument_key`s.
6. **Download & Upsert**:
   - Use asyncio to concurrently download the 1-minute OHLC data for those 43 symbols for that day.
   - Bulk insert the data directly into our existing `broker_upstox.options_ohlc` table.

### [NEW] `packages/trading_core/trading_core/providers/upstox_historical.py`
We need to add a few functions to interact with the Upstox Plus APIs:
- Fetching expired metadata.
- Fetching option contracts.
- Rate-limited concurrent downloading.

## Approval Status
All open questions are resolved. 
- **DB Source**: `broker_upstox.ohlcv_1m`
- **Multiple Expiries**: Yes, each active expiry on a given day will have its own 43 targets.
- **Holidays/Shifts**: Implicitly handled by the data and API.

If this looks good, we will proceed to execution!
