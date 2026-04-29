"""
nifty_trend_options — Paper/live strategy for NIFTY50 trend-following via options.

Logic summary
-------------
1. On each 5-minute bar (NIFTY50 index):
   a. If a position is open, check exit conditions first (target / stop).
   b. If no position, determine trend via EMA + MACD.
   c. Bullish trend → find near-Rs200 CE option and buy 1 lot.
      Bearish trend → find near-Rs200 PE option and buy 1 lot.
2. Exit conditions (checked every bar while in position):
   - Price ≥ target_price  → exit at profit (2× risk)
   - Price ≤ stop_price    → exit at stop (1× risk)
3. Risk model:
   - risk = entry_premium × stop_loss_premium_pct  (default 50%)
   - target_premium = entry_premium + 2 × risk
   - stop_premium   = entry_premium − risk
4. One position at a time; no pyramiding.

The strategy calls get_adapter(provider) directly to fetch live option quotes.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from typing import Optional

from trading_core import get_adapter
from trading_core.strategies import Strategy

logger = logging.getLogger("strategy_runtime.nifty_trend_options")

# ---------------------------------------------------------------------------
# Decision log file helper
# ---------------------------------------------------------------------------
_decision_log_dir = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "..", "logs", "strategy_runtime"
)


def _decision_log_path() -> str:
    today = date.today().isoformat()
    os.makedirs(_decision_log_dir, exist_ok=True)
    return os.path.join(_decision_log_dir, f"nifty_trend_decisions_{today}.txt")


def _log_decision(msg: str) -> None:
    line = f"[{_ts()}] {msg}"
    logger.info(line)
    try:
        with open(_decision_log_path(), "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        logger.warning("Could not write decision log: %s", exc)


def _ts() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Trend helpers
# ---------------------------------------------------------------------------

def _is_bullish(snapshot) -> bool:
    """EMA > SMA AND MACD line > 0."""
    ema = snapshot.indicators.get("ema_20")
    sma = snapshot.indicators.get("sma_20")
    macd_val = snapshot.indicators.get("macd")  # MACD returns dict; runtime stores {"macd": v, "signal": s, "hist": h}
    if ema is None or sma is None:
        return False
    macd_line = macd_val.get("macd", 0) if isinstance(macd_val, dict) else (macd_val or 0)
    return ema > sma and macd_line > 0


def _is_bearish(snapshot) -> bool:
    """EMA < SMA AND MACD line < 0."""
    ema = snapshot.indicators.get("ema_20")
    sma = snapshot.indicators.get("sma_20")
    macd_val = snapshot.indicators.get("macd")
    if ema is None or sma is None:
        return False
    macd_line = macd_val.get("macd", 0) if isinstance(macd_val, dict) else (macd_val or 0)
    return ema < sma and macd_line < 0


# ---------------------------------------------------------------------------
# Option quote fetch (blocking, run in thread)
# ---------------------------------------------------------------------------

def _fetch_option_quotes(adapter, underlying_symbol: str, expiry_date: str, strike_count: int) -> dict:
    """Call adapter synchronously; returns get_option_chain_symbols result."""
    return adapter.get_option_chain_symbols(underlying_symbol, expiry_date, strike_count)


def _fetch_quotes(adapter, symbols: list[str]) -> list[dict]:
    return adapter.get_quotes(symbols)


def _nearest_expiry(adapter, underlying_symbol: str) -> str:
    expiries = adapter.get_option_expiries(underlying_symbol)
    today = date.today().isoformat()
    future = [e for e in expiries if e >= today]
    return future[0] if future else (expiries[0] if expiries else "")


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class StrategyImpl(Strategy):
    """NIFTY50 trend options strategy."""

    def __init__(self, context):
        super().__init__(context)
        # Per-trade state
        self._option_symbol: Optional[str] = None  # currently held option instrument key
        self._entry_price: Optional[float] = None
        self._target_price: Optional[float] = None
        self._stop_price: Optional[float] = None
        self._trade_direction: Optional[str] = None  # "CE" or "PE"

    # ------------------------------------------------------------------
    # Required override (bar-level hook; actual logic in evaluate_snapshot)
    # ------------------------------------------------------------------

    async def on_bar(self, _bar):
        return None

    # ------------------------------------------------------------------
    # Main evaluation (called by runtime after indicators are computed)
    # ------------------------------------------------------------------

    async def evaluate_snapshot(self, snapshot):
        # --- 0. Load params ---
        provider = self.ctx.get_param("provider", "upstox")
        underlying = self.ctx.get_param("underlying_symbol", "NSE_INDEX|Nifty 50")
        target_premium = float(self.ctx.get_param("target_premium", 200.0))
        tolerance = float(self.ctx.get_param("premium_tolerance", 50.0))
        sl_pct = float(self.ctx.get_param("stop_loss_premium_pct", 0.5))
        qty = int(self.ctx.get_param("quantity", 1))
        scan_count = int(self.ctx.get_param("strike_scan_count", 10))
        configured_expiry = self.ctx.get_param("option_expiry", "")

        # --- 1. If we have an open option position, check exit first ---
        if self._option_symbol is not None:
            await self._check_exit(provider, qty)
            return

        # --- 2. No open position — check trend ---
        bullish = _is_bullish(snapshot)
        bearish = _is_bearish(snapshot)

        if not bullish and not bearish:
            _log_decision(
                f"SKIP — no clear trend. "
                f"EMA={snapshot.indicators.get('ema_20')}, "
                f"SMA={snapshot.indicators.get('sma_20')}, "
                f"MACD={snapshot.indicators.get('macd')}"
            )
            return

        direction = "CE" if bullish else "PE"
        _log_decision(f"TREND={direction} — scanning option chain …")

        # --- 3. Fetch option chain and find near-target-premium strike ---
        try:
            adapter = get_adapter(provider)
        except Exception as exc:
            _log_decision(f"ERROR getting adapter '{provider}': {exc}")
            return

        try:
            expiry_date = configured_expiry or await asyncio.to_thread(_nearest_expiry, adapter, underlying)
            if not expiry_date:
                _log_decision("ERROR: No expiry available from adapter")
                return

            chain_data = await asyncio.to_thread(
                _fetch_option_quotes, adapter, underlying, expiry_date, scan_count
            )
        except Exception as exc:
            _log_decision(f"ERROR fetching option chain: {exc}")
            return

        option_symbols = [
            s for s in chain_data.get("symbols", [])
            if direction in s.upper()
        ]
        if not option_symbols:
            _log_decision(f"ERROR: No {direction} symbols in chain for expiry {expiry_date}")
            return

        # Fetch live quotes for all candidate option symbols
        try:
            quotes = await asyncio.to_thread(_fetch_quotes, adapter, option_symbols)
        except Exception as exc:
            _log_decision(f"ERROR fetching option quotes: {exc}")
            return

        if not quotes:
            _log_decision("ERROR: Empty quotes response from adapter")
            return

        # Select the symbol whose last_price is nearest to target_premium and within tolerance
        best_symbol: Optional[str] = None
        best_price: Optional[float] = None
        best_dist = float("inf")

        for q in quotes:
            lp = q.get("last_price")
            if lp is None:
                continue
            dist = abs(lp - target_premium)
            if dist < best_dist and dist <= tolerance:
                best_dist = dist
                best_symbol = q.get("instrument_key", "")
                best_price = lp

        if best_symbol is None:
            _log_decision(
                f"SKIP — no {direction} option within ±{tolerance} of Rs{target_premium}. "
                f"Nearest price checked: {min((q.get('last_price', 0) for q in quotes), default='N/A')}"
            )
            return

        # --- 4. Enter position ---
        risk = best_price * sl_pct
        target_p = best_price + 2 * risk
        stop_p = best_price - risk

        _log_decision(
            f"ENTRY → symbol={best_symbol} price={best_price:.2f} "
            f"SL={stop_p:.2f} TP={target_p:.2f} (risk={risk:.2f})"
        )

        self._option_symbol = best_symbol
        self._entry_price = best_price
        self._target_price = target_p
        self._stop_price = stop_p
        self._trade_direction = direction

        await self.ctx.buy(best_symbol, qty, price=best_price, tag=f"nto_entry_{direction}")

    # ------------------------------------------------------------------
    # Exit check — called when we have an open position
    # ------------------------------------------------------------------

    async def _check_exit(self, provider: str, qty: int) -> None:
        if self._option_symbol is None:
            return

        # Check if the runtime portfolio still shows the position (could have been closed by stop layer)
        position = self.ctx.get_position(self._option_symbol)
        if position is None:
            _log_decision(f"POSITION GONE externally for {self._option_symbol} — resetting state")
            self._reset_trade_state()
            return

        # Fetch current price
        try:
            adapter = get_adapter(provider)
            quotes = await asyncio.to_thread(_fetch_quotes, adapter, [self._option_symbol])
            current_price = quotes[0].get("last_price") if quotes else None
        except Exception as exc:
            _log_decision(f"ERROR fetching exit quote for {self._option_symbol}: {exc}")
            return

        if current_price is None:
            _log_decision(f"WARNING: No price for {self._option_symbol}, holding position")
            return

        should_exit = False
        reason = ""

        if current_price >= self._target_price:
            should_exit = True
            reason = f"TARGET HIT price={current_price:.2f} >= target={self._target_price:.2f}"
        elif current_price <= self._stop_price:
            should_exit = True
            reason = f"STOP HIT price={current_price:.2f} <= stop={self._stop_price:.2f}"

        if should_exit:
            _log_decision(f"EXIT → {reason} | entry={self._entry_price:.2f} pnl≈{current_price - self._entry_price:.2f}")
            await self.ctx.sell(self._option_symbol, position.quantity, price=current_price, tag="nto_exit")
            self._reset_trade_state()
        else:
            _log_decision(
                f"HOLD {self._option_symbol} current={current_price:.2f} "
                f"[SL={self._stop_price:.2f} TP={self._target_price:.2f}]"
            )

    def _reset_trade_state(self) -> None:
        self._option_symbol = None
        self._entry_price = None
        self._target_price = None
        self._stop_price = None
        self._trade_direction = None
