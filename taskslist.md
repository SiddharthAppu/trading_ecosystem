# Task List: Replay Tick Aggregation, Replay Studio, and Service Modes

This file is the working tracker for the replay/tick-aggregation project. It is intended to be updated incrementally during implementation.

## Scope

- Keep `market_ticks` immutable as raw source data.
- Create derived 1-minute candle tables named `ohlcv_1min_from_ticks` under each provider schema.
- Keep existing vendor-sourced `ohlcv_1m` untouched.
- Continue using existing Replay Studio in historical UI.
- Add replay/timeframe/indicator support on top of current replay flow.
- Add selective start/stop modes for platform scripts.

## Current decisions

- `[x]` EOD aggregation is acceptable; real-time 1-minute aggregation is out of scope for now.
- `[x]` Derived candles will live in new tables: `broker_fyers.ohlcv_1min_from_ticks` and `broker_upstox.ohlcv_1min_from_ticks`.
- `[x]` Aggregation should be SQL-based by default.
- `[x]` Replay Studio in historical UI is sufficient; a separate replay route is optional.
- `[x]` Historical UI is not required for live data collection.
- `[x]` Current live recorder flow depends on the data collector backend API.

## Phase 1: Database and aggregation design

- `[x]` Confirm table schema for `ohlcv_1min_from_ticks` in both provider schemas.
- `[x]` Decide whether table structure exactly mirrors `ohlcv_1m` or includes lineage metadata.
- `[x]` Define indexes and uniqueness constraint for `(time, symbol)`.
- `[x]` Define SQL aggregation logic from `market_ticks` to 1-minute OHLCV buckets.
- `[x]` Define idempotent rerun strategy for a day/provider/symbol range.
- `[x]` Define reconciliation checks: missing buckets, duplicate buckets, expected session counts.
- `[ ]` Decide whether aggregation job writes directly to final table or through a staging table.

## Phase 2: Batch trigger and operational flow

- `[x]` Decide batch entrypoint shape: `.bat` file calling Python script vs direct SQL runner.
- `[ ]` Define EOD trigger timing after market close.
- `[x]` Define manual rerun/backfill arguments for provider, date, and symbol.
- `[x]` Decide log/output format for aggregation runs.
- `[ ]` Decide whether to integrate later with Windows Task Scheduler.

## Phase 3: Backend replay contract changes

- `[x]` Add timeframe concept to replay request contract.
- `[x]` Define which timeframes are supported in first pass: `1m`, `5m`, `10m`.
- `[x]` Define whether `5m` and `10m` are aggregated from `ohlcv_1min_from_ticks` in replay service or upstream query layer.
- `[x]` Add source metadata in replay responses: provider, data type, source table, timeframe, record count.
- `[x]` Define error contract for invalid provider, invalid symbol, unsupported timeframe, and no-data cases.
- `[ ]` Decide where symbol/timeframe capability metadata should live: data collector API vs replay engine support endpoint.

## Phase 4: Replay Studio enhancements

- `[x]` Add timeframe selector to Replay Studio.
- `[x]` Keep existing selection order: provider -> data type -> symbol.
- `[x]` Extend selection order to: provider -> data type -> symbol -> timeframe -> speed -> optional time range.
- `[x]` Define indicator selector UX for first-pass indicators.
- `[x]` Decide first-pass indicators: `EMA`, `SMA`, `RSI`, `MACD`.
- `[x]` Define chart rendering rules for overlays vs separate panes.
- `[x]` Define how replay metadata/status should be surfaced in UI.

## Phase 5: Indicator computation strategy

- `[x]` Confirm indicators are backend-computed, not chart-library-computed.
- `[x]` Define indicator request parameters and defaults.
- `[x]` Define timestamp alignment and warmup/null handling for indicators.
- `[ ]` Decide whether indicator computation is replay-specific or reusable across chart pages.

## Phase 6: Startup and shutdown modes

- `[x]` Add start mode design for `start_platform.bat`.
- `[x]` Define supported presets: `all`, `collector`, `replay`, `execution`, `uis-only`, `collector+replay`.
- `[x]` Add stop mode design for `stop_platform.bat`.
- `[x]` Ensure presets preserve current default behavior when no arguments are passed.
- `[ ]` Ensure env propagation is consistent in launcher scripts: `PYTHONPATH`, `TRADING_CONFIG_DIR`, `TRADING_AUTH_DIR`.
- `[x]` Decide whether replay mode should start only DB + replay engine, or DB + replay engine + metadata API.

## Phase 7: Validation and rollout

- `[x]` Validate one-day aggregation output against raw ticks.
- `[x]` Validate replay from `market_ticks` still works unchanged.
- `[x]` Validate replay from `ohlcv_1min_from_ticks` works for `1m`.
- `[x]` Validate server-side aggregation for `5m` and `10m`.
- `[x]` Validate indicator overlays/panes against replay stream.
- `[x]` Validate `master_recorder.py` workflow still works with collector-only startup.
- `[x]` Validate replay-only startup mode independently.
- `[x]` Validate full `start_platform.bat` behavior remains backward compatible.

## Suggested implementation order

- `[x]` 1. Add DB schema and migration for `ohlcv_1min_from_ticks`.
- `[x]` 2. Implement SQL aggregation job and manual batch trigger.
- `[x]` 3. Validate aggregation correctness on one provider/day.
- `[x]` 4. Extend replay backend contract for timeframe + source metadata.
- `[x]` 5. Update Replay Studio for timeframe selection.
- `[x]` 6. Add first-pass indicator APIs and chart rendering.
- `[x]` 7. Add selective start/stop script presets.
- `[x]` 8. Run end-to-end workflow validation.

## Notes

- Current recorder scripts use the data collector backend API at `http://localhost:8080`; they do not require historical UI.
- Replay Studio already exists and should be enhanced rather than replaced.
- The charting library is a renderer; aggregation and indicator logic should remain backend-owned.
- Runtime validation added: `scripts/validate_replay_timeframes.py` confirms derived replay row delivery for `1m`, `5m`, and `10m`.
- Runtime validation added: `scripts/validate_market_ticks_replay.py` confirms market_ticks behavior unchanged and 5m guardrails.
- Runtime validation added: `scripts/validate_replay_indicators.py` confirms backend EMA/SMA/RSI/MACD fields are streamed.
- Runtime validation added: `scripts/validate_tick_aggregation_accuracy.py` confirms derived 1m bars exactly match direct tick aggregation for a day.
- `start_platform.bat` and `stop_platform.bat` now support presets: `all`, `collector`, `replay`, `execution`, `uis-only`, `collector+replay`.
