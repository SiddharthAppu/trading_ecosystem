# Strategy: ema_cross

**Location:** `services/strategy_runtime/strategies/ema_cross/`  
**Status:** Active — paper replay ready  
**Instrument:** Any single symbol (default: `NSE:NIFTY50-INDEX`)  
**Timeframe:** Configurable (default: 5-minute bars)

---

## 1. Concept

A classic trend-following equity/index strategy built on a dual moving-average crossover. It goes long when price is above a fast EMA and the EMA is itself above a slow SMA, indicating upward momentum. It exits when price crosses back below the EMA. Position sizing supports both fixed-lot and compounding modes. The strategy trades the underlying directly (no options), making it suitable for index futures, ETFs, or equity paper trading.

---

## 2. Signal Logic

### Entry

All three conditions must hold simultaneously on the current bar:

| Condition | Expression | Meaning |
| :-------- | :--------- | :------ |
| Price above fast EMA | `close > EMA(20)` | Price is in an uptrend relative to short-term average |
| Fast EMA above slow SMA | `EMA(20) > SMA(20)` | Short-term momentum confirms medium-term trend |
| No open position | `position is None` | Only one position held at a time |

When all three are met → **`BUY`** `effective_units` of the symbol (tagged `ema_cross_entry`).

### Exit

Checked on every bar while in position:

| Condition | Expression | Action |
| :-------- | :--------- | :----- |
| Price below fast EMA | `close < EMA(20)` | **`SELL`** full position (tagged `ema_cross_exit`) |

No explicit stop-loss or target is coded inside the strategy; the runtime environment can apply `STRATEGY_RUNTIME_STOP_LOSS_PCT` and `STRATEGY_RUNTIME_TRAILING_STOP_PCT` as runtime-level guards.

### Indicators Required

| Indicator | Config key | Notes |
| :-------- | :--------- | :---- |
| EMA(20)   | `ema_20`   | 20-period Exponential Moving Average |
| SMA(20)   | `sma_20`   | 20-period Simple Moving Average |
| RSI(14)   | `rsi_14`   | Loaded but not used in signal logic (available for future extensions) |
| MACD      | `macd`     | Loaded but not used in signal logic |

> Set `STRATEGY_RUNTIME_INDICATORS=ema_20,sma_20,rsi_14,macd` so the runtime computes all four.

---

## 3. Position Sizing

### Non-compounding (default)

```
effective_units = lot_quantity × lot_size
```

`lot_quantity` and `lot_size` are fixed at runtime regardless of P&L.

### Compounding

When `STRATEGY_RUNTIME_CAPITAL_MODEL=compounding`, the number of lots is recalculated on each entry:

```
capital_available = initial_capital + total_realised_pnl
effective_lots    = floor(capital_available / (close × lot_size))
effective_units   = effective_lots × lot_size   (minimum 1 lot)
```

This grows (or shrinks) position size as the account equity changes.

---

## 4. Parameters

All parameters are read from environment variables. Use `strategy.env.example` as a template.

### Strategy-local parameters

| Env Variable | Default | Description |
| :----------- | :------ | :---------- |
| `STRATEGY_RUNTIME_LOT_QUANTITY` | `1` | Fixed number of lots per trade |
| `STRATEGY_RUNTIME_LOT_SIZE` | `1` | Units per lot (e.g. 75 for NIFTY futures) |
| `STRATEGY_RUNTIME_CAPITAL_MODEL` | `non_compounding` | `non_compounding` or `compounding` |
| `STRATEGY_RUNTIME_INITIAL_CAPITAL` | `100000` | Starting capital used for compounding calc (₹) |

### Runtime parameters (from the env config)

| Env Variable | Example value | Description |
| :----------- | :------------ | :---------- |
| `STRATEGY_RUNTIME_SYMBOL` | `NSE:NIFTY50-INDEX` | Symbol to trade |
| `STRATEGY_RUNTIME_TIMEFRAME` | `5m` | Bar aggregation interval |
| `STRATEGY_RUNTIME_LOOKBACK_BARS` | `120` | Bars loaded for indicator warmup |
| `STRATEGY_RUNTIME_INDICATORS` | `ema_20,sma_20,rsi_14,macd` | Indicators the runtime must compute |
| `STRATEGY_RUNTIME_STOP_LOSS_PCT` | `0.01` | Runtime-level hard stop (1%) |
| `STRATEGY_RUNTIME_TRAILING_STOP_PCT` | `0.015` | Runtime-level trailing stop (1.5%) |
| `STRATEGY_RUNTIME_MAX_POSITION_LOTS` | `1` | Maximum concurrent lots |
| `STRATEGY_RUNTIME_MAX_NOTIONAL` | `250000` | Maximum notional exposure (₹) |

---

## 5. Files

| File | Purpose |
| :--- | :------ |
| `strategy.py` | Entry, exit, and position sizing logic |
| `config.py` | Returns strategy-local default params dict |
| `strategy.env.example` | Template — merge into a runtime env file before running |
| `__init__.py` | Package marker |

---

## 6. How to Run (Paper Replay)

### Prerequisites
- Replay engine running on `ws://localhost:8765`
- `config/strategy_runtime.ema_cross.paper_replay.env` populated (use `strategy.env.example` as reference)
- `DATABASE_URL` set in `config/.env`

### Start
```powershell
# From workspace root
$env:STRATEGY_RUNTIME_ENV = "config/strategy_runtime.ema_cross.paper_replay.env"
python services/strategy_runtime/main.py
```

The runtime:
1. Loads `STRATEGY_RUNTIME_LOOKBACK_BARS` historical bars for indicator warmup.
2. Connects to the replay WebSocket and begins receiving bars.
3. Calls `evaluate_snapshot()` on each completed bar.
4. Logs decisions to `logs/strategy_runtime/runtime.log`.

### Replay window (example config)
```
STRATEGY_RUNTIME_REPLAY_START_TIME=2026-04-30T09:15:00+05:30
STRATEGY_RUNTIME_REPLAY_END_TIME=2026-04-30T15:30:00+05:30
STRATEGY_RUNTIME_REPLAY_SPEED=5
```

### Broker status
```
GET http://localhost:8000/broker/status
```

---

## 7. Notes

- The strategy only goes **long** — there is no short-selling leg.
- RSI(14) and MACD are computed by the runtime but are not consumed by the signal logic. They are available on `snapshot.indicators` for future enhancements.
- The runtime-level stop-loss (`STRATEGY_RUNTIME_STOP_LOSS_PCT`) acts as a safety net independent of the strategy code; it will close the position before `evaluate_snapshot` runs if the price drops past the threshold.
- When `lot_size=75` (NIFTY lot), ensure `STRATEGY_RUNTIME_MAX_NOTIONAL` is set appropriately to prevent over-leveraging during compounding.
