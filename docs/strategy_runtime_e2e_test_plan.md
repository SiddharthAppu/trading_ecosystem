# Strategy Runtime E2E Test Plan

## Purpose
This document validates two delivered capabilities end-to-end:
1. Optional live feed source `collector_sse` in strategy runtime.
2. Existing live default `broker` path remains unchanged.

It also includes regression checks for replay/backtest/optimize so rollout does not break existing workflows.

## Scope
- In scope:
  - Live runtime: `feed_source=broker` and `feed_source=collector_sse`.
  - Collector stream connectivity, tick ingestion, and bar aggregation behavior.
  - Replay/backtest/optimize smoke regressions.
- Out of scope:
  - Strategy-specific performance tuning.
  - Broker account authorization troubleshooting beyond token validity checks.

## Prerequisites
1. Python virtual environments are available:
   - `services/data_collector/.venv`
   - `.venv` at repository root
2. Services/ports:
   - Data collector API on `http://localhost:8080`
   - Strategy runtime API available through `services/strategy_runtime/server.py`
   - Replay engine available when testing replay mode
3. Valid broker auth token is present.
4. Database connectivity is healthy (`DATABASE_URL` resolves and connects).

## JSON Config Notes (Live Runtime)
Live runtime strategy settings are now loaded from JSON config files (for example, `config/strategy_runtime.nifty_trend_options.live_collector_sse.json.example`).

Set these values in the JSON file only when using collector-based live feed.

- `STRATEGY_RUNTIME_FEED_SOURCE=collector_sse`
- `STRATEGY_RUNTIME_COLLECTOR_BASE_URL=http://localhost:8080`
- `STRATEGY_RUNTIME_COLLECTOR_EVENTS_PATH=/recorder/events`
- `STRATEGY_RUNTIME_COLLECTOR_PROVIDER=upstox` (optional; defaults to runtime provider)
- `STRATEGY_RUNTIME_COLLECTOR_CONNECT_TIMEOUT_SECONDS=10`
- `STRATEGY_RUNTIME_COLLECTOR_RECONNECT_SECONDS=3`
- `STRATEGY_RUNTIME_COLLECTOR_STALE_TIMEOUT_SECONDS=45`
- `STRATEGY_RUNTIME_COLLECTOR_FALLBACK_POLICY=collector_only`
  - valid values: `collector_only`, `fallback_to_broker`

Default behavior remains: `runtime.feed_source=broker`

## Test Matrix
1. Live baseline: broker feed (default)
2. Live optional: collector_sse feed
3. Collector interruption behavior (reconnect/fallback)
4. Replay regression
5. Backtest bars regression
6. Backtest ticks regression
7. Optimize bars regression
8. Optimize ticks regression

---

## Scenario 1: Live Baseline (broker)
### Goal
Verify no behavior drift in existing live mode.

### Steps
1. Ensure collector may be running or stopped; broker mode should not depend on it.
2. Set:
   - `STRATEGY_RUNTIME_FEED_SOURCE=broker`
3. Launch runtime in paper mode:
   - `powershell -File scripts/start_strategy_runtime_live_paper.ps1 -Strategy ema_cross`
4. Let it run for 5-10 minutes.

### Pass Criteria
- Runtime starts and remains healthy.
- Market snapshots continue at expected cadence.
- No new startup/runtime exceptions.

---

## Scenario 2: Live Optional Path (collector_sse)
### Goal
Verify runtime can consume collector stream and produce strategy snapshots.

### Steps
1. Start collector service:
   - `services/data_collector/.venv/Scripts/python.exe services/data_collector/main.py`
2. Start live recorder orchestration (example):
   - `scripts/start_live_capture_and_strategy.ps1 -Strategy ema_cross -SkipAuthCheck`
   - or run `scripts/lib/quick_live_recorder.py` manually for target provider/expiry.
3. Set runtime env:
   - `STRATEGY_RUNTIME_FEED_SOURCE=collector_sse`
   - collector settings listed above.
4. Start strategy runtime.
5. Observe runtime logs/events for tick->bar ingestion and strategy evaluation.

### Pass Criteria
- Runtime starts with collector_sse.
- Tick events arrive and bars are produced.
- Strategy evaluation loop runs without exceptions.

---

## Scenario 3: Collector Interruption (resilience)
### Goal
Validate reconnect/fallback behavior.

### Steps
1. Run Scenario 2 successfully.
2. Stop collector service abruptly.
3. Observe runtime for at least 2 stale timeout windows.
4. Repeat with two policies:
   - `collector_only`
   - `fallback_to_broker`

### Pass Criteria
- `collector_only`: runtime retries and logs reconnect attempts; no crash loop.
- `fallback_to_broker`: runtime falls back to broker polling and continues.

---

## Scenario 4: Replay Regression
### Goal
Ensure replay path remains unchanged.

### Steps
1. Use replay config with `runtime.feed_source=replay_ws`.
2. Launch with:

```powershell
powershell -File scripts/start_strategy_runtime_paper_replay.ps1 -Strategy nifty_trend_options -StrategyConfig config/strategy_runtime.nifty_trend_options.replay_ticks.json.example
```

3. Run a known replay window and verify runtime completes normally.

### Pass Criteria
- Replay starts/finishes as before.
- No regression in replay status/aggregation output.

---

## Scenario 5: Backtest Bars Regression
### Goal
Ensure bars-source backtests still work.

### Steps
Run a short-range command with JSON strategy config:

```powershell
.\scripts\START_BACKTEST_KIT.ps1 -Mode backtest -From 2026-04-15 -To 2026-04-16 -StrategyConfig "config\strategy_runtime.nifty_trend_options.backtest_bars.json.example"
```

### Pass Criteria
- Schema preflight passes.
- Backtest completes and emits summary.

---

## Scenario 6: Backtest Ticks Regression
### Goal
Ensure ticks-source backtests still work.

### Steps
Run a short-range command with JSON strategy config:

```powershell
.\scripts\START_BACKTEST_KIT.ps1 -Mode backtest -From 2026-04-15 -To 2026-04-16 -StrategyConfig "config\strategy_runtime.nifty_trend_options.backtest_ticks_partial.json.example"
```

### Pass Criteria
- Tick source preflight passes.
- Tick aggregation and strategy run complete.

---

## Scenario 7: Optimize Bars Regression
### Goal
Ensure optimizer bars flow remains intact.

### Steps
```powershell
.\scripts\START_BACKTEST_KIT.ps1 -Mode optimize -From 2026-04-15 -To 2026-04-16 -Top 1 -StrategyConfig "config\strategy_runtime.nifty_trend_options.optimize_bars.json.example" -OptimizerConfig "config\strategy_optimize_ranges.json"
```

### Pass Criteria
- Optimizer completes.
- Ranked output produced.

---

## Scenario 8: Optimize Ticks Regression
### Goal
Ensure optimizer ticks flow remains intact.

### Steps
```powershell
.\scripts\START_BACKTEST_KIT.ps1 -Mode optimize -From 2026-04-15 -To 2026-04-16 -Top 1 -StrategyConfig "config\strategy_runtime.nifty_trend_options.optimize_ticks.json.example" -OptimizerConfig "config\strategy_optimize_ranges.json"
```

### Pass Criteria
- Optimizer completes.
- Ranked output produced.

---

## Negative Tests
1. Invalid feed source:
   - Set `STRATEGY_RUNTIME_FEED_SOURCE=invalid_mode`
   - Expected: startup fails with clear config error.
2. Invalid fallback policy:
   - Set `STRATEGY_RUNTIME_COLLECTOR_FALLBACK_POLICY=invalid`
   - Expected: startup fails with clear config error.
3. Collector unavailable + collector_only:
   - Expected: retry behavior, no process crash.

## Scenario 9: Valid JSON Loads
### Goal
Verify runtime starts when given a valid JSON config.

### Steps
1. Run:

```powershell
.venv/Scripts/python.exe services/strategy_runtime/main.py --config config/strategy_runtime.nifty_trend_options.backtest.json
```

### Pass Criteria
- Runtime starts configuration parsing without JSON/config errors.

## Scenario 10: Missing Required Replay Field
### Goal
Ensure missing replay-required values fail fast.

### Steps
1. Copy a replay JSON config and remove `replay.source_table`.
2. Run runtime with that config.

### Pass Criteria
- Startup fails with a clear `Missing required config: STRATEGY_RUNTIME_SOURCE_TABLE` error.

## Scenario 11: Invalid JSON Syntax
### Goal
Ensure malformed JSON gives a clear parse error.

### Steps
1. Introduce a trailing comma or broken brace in a copy of a JSON config.
2. Run runtime with that config.

### Pass Criteria
- Startup fails with `Invalid JSON in runtime config ...`.

## Scenario 12: strategy_params Bridge
### Goal
Verify `strategy_params` keys are bridged into `os.environ`.

### Steps
1. Set `strategy_params.NIFTY_EMA_PERIOD` to a distinct value in JSON.
2. Start runtime and inspect logs/behavior that reflect EMA period.

### Pass Criteria
- Strategy consumes the JSON value without direct strategy code changes.

## Rollback Procedure
1. Force old behavior:
   - `STRATEGY_RUNTIME_FEED_SOURCE=broker`
2. Unset collector-specific variables.
3. Restart runtime.
4. Re-run Scenario 1 baseline check.

## Final Sign-off Checklist
- [ ] Scenario 1 pass
- [ ] Scenario 2 pass
- [ ] Scenario 3 pass
- [ ] Scenario 4 pass
- [ ] Scenario 5 pass
- [ ] Scenario 6 pass
- [ ] Scenario 7 pass
- [ ] Scenario 8 pass
- [ ] Negative tests pass
- [ ] Rollback verified
