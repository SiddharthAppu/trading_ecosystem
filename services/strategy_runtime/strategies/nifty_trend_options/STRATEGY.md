# Strategy: nifty_trend_options

**Location:** `services/strategy_runtime/strategies/nifty_trend_options/`  
**Status:** Active — paper trading ready  
**Instrument:** NIFTY50 weekly options (CE or PE, 1 lot at a time)  
**Timeframe:** 5-minute bars on the NIFTY50 index  

---

## 1. Concept

A trend-following, directional options strategy. On every 5-minute bar it checks whether the NIFTY50 index has a clear directional bias using two filters: a dual-moving-average crossover (EMA vs SMA) and MACD momentum. When both agree, it buys a call option (CE) for bullish bias or a put option (PE) for bearish bias. Only one position is held at a time. Entry is sized by finding an option whose current premium is close to a target value (default ₹200), so risk-per-trade stays consistent regardless of the strike chosen.

---

## 2. Signal Logic

### Entry

Both conditions must be true simultaneously:

| Bias     | EMA vs SMA         | MACD line      | Action      |
| :------- | :----------------- | :------------- | :---------- |
| Bullish  | `EMA(20) > SMA(20)` | MACD line > 0 | Buy CE option |
| Bearish  | `EMA(20) < SMA(20)` | MACD line < 0 | Buy PE option |

- **No trade** if the two filters disagree or either indicator is unavailable (insufficient warmup bars).

### Option Selection

Once a direction is confirmed:
1. Fetch the option chain for the current (or configured) weekly expiry.
2. Scan up to `NIFTY_STRIKE_SCAN_COUNT` strikes in each direction from ATM.
3. Select the strike whose current premium is closest to `NIFTY_TARGET_PREMIUM` **and** falls within `±NIFTY_PREMIUM_TOLERANCE`.
4. If no strike qualifies, the trade is skipped for that bar.

### Exit

Checked on every subsequent 5-minute bar while in position:

| Condition                                        | Action         |
| :----------------------------------------------- | :------------- |
| Current price ≥ `entry + 2 × risk`               | Exit at profit (TARGET) |
| Current price ≤ `entry − risk`                   | Exit at stop (STOP)     |
| Position disappears from portfolio (broker stop)  | Reset state    |

Where `risk = entry_premium × NIFTY_STOP_LOSS_PREMIUM_PCT`.

**Risk-reward ratio is always 2 : 1** — every target is exactly 2× the stop distance.

---

## 3. Parameters

All parameters are read from environment variables. Copy `strategy.env.example` as your starting point.

| Env Variable                     | Default | Description |
| :------------------------------- | :------ | :---------- |
| `NIFTY_TARGET_PREMIUM`           | 200     | Target option premium for strike selection (₹) |
| `NIFTY_PREMIUM_TOLERANCE`        | 50      | Accept strikes within ±tolerance of target (₹) |
| `NIFTY_STOP_LOSS_PREMIUM_PCT`    | 0.50    | Risk per trade as fraction of entry premium (50%) |
| `NIFTY_STRIKE_SCAN_COUNT`        | 10      | Strikes to scan in each direction from ATM |
| `NIFTY_OPTION_EXPIRY`            | _(blank)_ | ISO date "YYYY-MM-DD". Blank = nearest weekly |
| `STRATEGY_RUNTIME_LOOKBACK_BARS` | 60      | Bars to load for indicator warmup |
| `STRATEGY_RUNTIME_INDICATORS`    | `ema_20,sma_20,macd` | Indicators the runtime must compute |

### Indicator periods (currently fixed in `compute_indicator_rows`)

| Indicator | Period  |
| :-------- | :------ |
| EMA       | 20 bars |
| SMA       | 20 bars |
| MACD      | 12 / 26 / 9 |

> To test alternate periods use the backtest scripts (Section 6). Editing the live runtime requires changes in `packages/trading_core/trading_core/analytics/__init__.py`.

---

## 4. Files

| File | Purpose |
| :--- | :------ |
| `strategy.py` | Entry, exit and position management logic |
| `config.py` | Reads env vars into default params dict |
| `strategy.env.example` | Template — copy and fill before running |

---

## 5. How to Run (Live Paper)

### Prerequisites
- Upstox auth token in `config/auth/` (run `python scripts/authenticate_broker.py`)
- `config/strategy_runtime.paper_live.env` populated (copy from `strategy.env.example`)
- `DATABASE_URL` set in `config/.env`

### Start
```powershell
.\scripts\start_strategy_runtime_live_paper.ps1
```

The launcher:
1. Triggers Upstox auth if no valid token exists.
2. Starts the FastAPI strategy_runtime server.
3. The runtime loads 60 historical bars for indicator warmup, then polls every 30 seconds.

### Decision log
Every signal decision is written to:
```
logs/strategy_runtime/nifty_trend_decisions_YYYY-MM-DD.txt
```

### Broker status
```
GET http://localhost:8000/broker/status
```

---

## 6. Backtesting

### Why a standalone script instead of the replay engine

The `replay_engine` streams historical index bars correctly, but the live strategy calls `adapter.get_quotes()` for option pricing on each bar — that always returns *today's* price, not the historical one. A standalone script using `master_broker.options_ohlc_1m_fromupstox` is the only way to get true historical option P&L.

### Data sources used

| Table | Usage |
| :---- | :---- |
| `master_broker.ohlcv_1m` | NIFTY50 1m index bars → aggregated to 5m |
| `master_broker.options_ohlc_1m_fromupstox` | Historical option OHLC for entry/exit pricing |

### Backtest script

**File:** `scripts/backtest_nifty_trend.py`

Mirrors the live strategy logic exactly:
- Aggregates 1m index bars to 5m
- Computes EMA, SMA, MACD with configurable periods
- Applies the same EMA>SMA + MACD>0 / <0 signal logic
- Selects the nearest-to-target-premium option from DB
- Tracks option price bar-by-bar; exits on target or stop
- Prints every trade and a summary

**Basic run:**
```powershell
python scripts/backtest_nifty_trend.py `
    --from 2026-04-01 --to 2026-04-28 `
    --export-trades trades.csv
```

**Full parameter reference:**
```
--from              YYYY-MM-DD  Start date (inclusive)
--to                YYYY-MM-DD  End date (inclusive)
--ema-period        int         EMA period (default 20)
--sma-period        int         SMA period (default 20)
--macd-fast         int         MACD fast EMA (default 12)
--macd-slow         int         MACD slow EMA (default 26)
--macd-signal       int         MACD signal EMA (default 9)
--target-premium    float       Target option premium in ₹ (default 200)
--premium-tolerance float       ±tolerance around target (default 50)
--sl-pct            float       Stop as fraction of entry (default 0.5)
--lot-size          int         Lot size for P&L (default 75)
--index-symbol      str         Index symbol in DB (default NSE:NIFTY50-INDEX)
--export-trades     FILE        Write all trades to CSV
```

### Parameter optimizer

**File:** `scripts/optimize_nifty_trend.py`

Runs the backtest for every combination in the GRID defined at the top of the script, then ranks by total PnL (or win rate or trade count).

**Run:**
```powershell
python scripts/optimize_nifty_trend.py `
    --from 2026-04-01 --to 2026-04-28 `
    --top 10 --sort-by total_pnl
```

**Sort options:** `total_pnl` · `win_rate_pct` · `total_trades`

**Default search grid** (edit in `optimize_nifty_trend.py` to narrow or widen):

| Parameter | Values searched |
| :-------- | :-------------- |
| EMA period | 10, 14, 20, 26 |
| SMA period | 10, 14, 20, 26 |
| MACD fast | 9, 12 |
| MACD slow | 21, 26 |
| MACD signal | 7, 9 |
| Target premium | 150, 200, 250 |
| Premium tolerance | 40, 60 |
| SL % | 35%, 50%, 65% |

Total combinations: **1 152**

### Recommended testing workflow

```
Step 1 – Sanity check
    Run the backtest on 1 week of data with default params.
    Goal: confirm trades are being generated and the output looks sane
    (entries at real signal bars, exit prices match option data).

Step 2 – In-sample optimization
    Run the optimizer on 2–3 months of data (your full history).
    Take note of the top 3–5 parameter sets.

Step 3 – Out-of-sample validation
    Hold back the most recent month from the optimizer.
    Re-run the backtest for that month using the winning params.
    If PnL remains positive → the params are robust.
    If PnL collapses → the params are curve-fitted; use the next best set.

Step 4 – Deploy
    Set the validated params in config/strategy_runtime.paper_live.env.
    Run live paper for 2–4 weeks before considering real capital.

Step 5 – Re-optimize quarterly
    Market regimes change. Re-run the optimizer every quarter
    and validate before updating production params.
```

---

## 7. Backtest Results Log

Record results here after each test run. Keep in-sample and out-of-sample separate.

---

### Run 001 — [Date: ___________]

| Field | Value |
| :---- | :---- |
| Data range | ___ to ___ |
| Type | ☐ In-sample  ☐ Out-of-sample |
| EMA period | |
| SMA period | |
| MACD | fast= slow= signal= |
| Target premium | |
| Premium tolerance | |
| SL % | |
| Lot size | |

**Results:**

| Metric | Value |
| :----- | :---- |
| Total trades | |
| Wins | |
| Losses | |
| Win rate | % |
| Total PnL | ₹ |
| Avg win | ₹ |
| Avg loss | ₹ |

**Notes / Observations:**

> _(e.g. Most trades entered between 9:30–11:00. Stop hit frequently in choppy mid-session.)_

---

### Run 002 — [Date: ___________]

| Field | Value |
| :---- | :---- |
| Data range | ___ to ___ |
| Type | ☐ In-sample  ☐ Out-of-sample |
| EMA period | |
| SMA period | |
| MACD | fast= slow= signal= |
| Target premium | |
| Premium tolerance | |
| SL % | |
| Lot size | |

**Results:**

| Metric | Value |
| :----- | :---- |
| Total trades | |
| Wins | |
| Losses | |
| Win rate | % |
| Total PnL | ₹ |
| Avg win | ₹ |
| Avg loss | ₹ |

**Notes / Observations:**

> _(Add results here after running the backtest.)_

---

### Run 003 — [Date: ___________]

| Field | Value |
| :---- | :---- |
| Data range | ___ to ___ |
| Type | ☐ In-sample  ☐ Out-of-sample |
| EMA period | |
| SMA period | |
| MACD | fast= slow= signal= |
| Target premium | |
| Premium tolerance | |
| SL % | |
| Lot size | |

**Results:**

| Metric | Value |
| :----- | :---- |
| Total trades | |
| Wins | |
| Losses | |
| Win rate | % |
| Total PnL | ₹ |
| Avg win | ₹ |
| Avg loss | ₹ |

**Notes / Observations:**

> _(Add results here after running the backtest.)_

---

## 8. Optimizer Results Log

Paste the optimizer output table here after each optimization run.

---

### Optimization Run 001 — [Date: ___________]

**In-sample range:** ___ to ___  
**Sort metric:** total_pnl  
**Min trades filter:** 3  

```
(paste optimizer table output here)
```

**Selected params for out-of-sample test:**

| Param | Value |
| :---- | :---- |
| EMA period | |
| SMA period | |
| MACD | |
| Target premium | |
| Premium tolerance | |
| SL % | |

---

### Optimization Run 002 — [Date: ___________]

**In-sample range:** ___ to ___  
**Sort metric:**  
**Min trades filter:**  

```
(paste optimizer table output here)
```

**Selected params for out-of-sample test:**

| Param | Value |
| :---- | :---- |
| EMA period | |
| SMA period | |
| MACD | |
| Target premium | |
| Premium tolerance | |
| SL % | |

---

## 9. Deployed Parameter History

Track what was actually deployed to live paper trading and when.

| Date deployed | EMA | SMA | MACD | Target ₹ | Tol ₹ | SL% | Reason for change |
| :------------ | :-- | :-- | :--- | :------- | :---- | :-- | :---------------- |
| _(initial)_   | 20  | 20  | 12/26/9 | 200   | 50    | 50% | Default (untested) |
|               |     |     |      |          |       |     |                   |
|               |     |     |      |          |       |     |                   |

---

## 10. Known Limitations

- **Option data lag:** `master_broker.options_ohlc_1m_fromupstox` is populated by the EOD sync script (`scripts/lib/sync_options_to_master.py`). If a day is missed, that day has no option data and will show zero trades in the backtest.
- **Illiquid strikes:** Deep OTM options may have stale or zero prices in the DB. The backtest skips bars where option price is 0.
- **No slippage / brokerage:** Backtest uses exact option close prices. Real trades will have bid-ask spread and STT costs. Add ~₹5–10 per entry+exit to each trade cost when evaluating results.
- **One position at a time:** The strategy does not pyramid. A strongly trending day generates only one trade.
- **5m bar delay:** The signal is generated at bar close. The option entry price used in the backtest is the option close of that same 5m bar. In live trading there will be a few seconds of execution delay.
- **No RSI filter:** RSI is not currently used in this strategy. It could be added as an additional entry filter (e.g. RSI < 60 for CE entries). The backtest script would need a corresponding update.
