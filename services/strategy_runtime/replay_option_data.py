from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from datetime import date
from statistics import median
from typing import Any

from trading_core.db import DatabaseManager

logger = logging.getLogger(__name__)

# Timeout (seconds) for individual database queries to prevent hangs during backtest intrabar checks.
QUERY_TIMEOUT_SECONDS = 5.0


class ReplayOptionDataResolver:
    """Resolve option expiries/chain/quotes from historical DB for replay mode."""

    def __init__(self, settings):
        self.settings = settings
        configured_table = str(getattr(settings, "options_source_table", "") or "").strip()
        self.options_table = configured_table or os.getenv(
            "STRATEGY_RUNTIME_REPLAY_OPTIONS_TABLE",
            "master_broker.options_ohlc_1m_fromupstox",
        )

    async def _pool(self):
        pool = await DatabaseManager.get_pool()
        if pool is None:
            raise RuntimeError("Database pool unavailable; cannot resolve replay option data")
        return pool

    @staticmethod
    def _normalize_option_type(raw: str | None, symbol: str) -> str:
        v = (raw or "").strip().upper()
        if v in {"CE", "PE"}:
            return v
        symbol_up = symbol.upper()
        if symbol_up.endswith("CE"):
            return "CE"
        if symbol_up.endswith("PE"):
            return "PE"
        return v

    async def get_option_expiries(self, underlying_symbol: str, as_of_time: datetime) -> list[str]:
        del underlying_symbol  # Not needed for master options table (already NIFTY-specific rows)

        sql = f"""
            SELECT DISTINCT expiry_date
            FROM {self.options_table}
            WHERE time <= $1
              AND expiry_date >= $2::date
            ORDER BY expiry_date ASC;
        """
        pool = await self._pool()
        try:
            async with pool.acquire() as conn:
                rows = await asyncio.wait_for(
                    conn.fetch(sql, as_of_time, as_of_time.date()),
                    timeout=QUERY_TIMEOUT_SECONDS
                )
        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout ({QUERY_TIMEOUT_SECONDS}s) querying option expiries from {self.options_table}; "
                f"returning empty list to avoid blocking backtest."
            )
            return []
        except Exception as exc:
            logger.error(f"Error querying option expiries: {exc}; returning empty list.")
            return []

        return [str(row["expiry_date"]) for row in rows if row.get("expiry_date") is not None]

    async def nearest_expiry(self, underlying_symbol: str, as_of_time: datetime) -> str:
        expiries = await self.get_option_expiries(underlying_symbol, as_of_time)
        return expiries[0] if expiries else ""

    async def get_option_chain_symbols(
        self,
        underlying_symbol: str,
        expiry_date: str,
        strike_count: int,
        as_of_time: datetime,
        spot_hint: float | None = None,
    ) -> dict[str, Any]:
        del underlying_symbol

        sql = f"""
            SELECT DISTINCT ON (symbol)
                time,
                symbol,
                strike_price,
                expiry_date,
                option_type,
                close,
                nifty_spot
            FROM {self.options_table}
            WHERE time <= $1
              AND expiry_date = $2::date
              AND close IS NOT NULL
              AND close > 0
            ORDER BY symbol, time DESC;
        """

        pool = await self._pool()
        expiry_param: date | str = expiry_date
        if isinstance(expiry_date, str):
            try:
                expiry_param = datetime.fromisoformat(expiry_date).date()
            except ValueError:
                expiry_param = expiry_date
        
        try:
            async with pool.acquire() as conn:
                rows = await asyncio.wait_for(
                    conn.fetch(sql, as_of_time, expiry_param),
                    timeout=QUERY_TIMEOUT_SECONDS
                )
        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout ({QUERY_TIMEOUT_SECONDS}s) querying option chain for expiry {expiry_date}; "
                f"returning empty chain to avoid blocking backtest."
            )
            return {"atm": 0.0, "spot": 0.0, "symbols": [], "contracts": []}
        except Exception as exc:
            logger.error(f"Error querying option chain: {exc}; returning empty chain.")
            return {"atm": 0.0, "spot": 0.0, "symbols": [], "contracts": []}

        if not rows:
            return {"atm": 0.0, "spot": 0.0, "symbols": [], "contracts": []}

        contracts: list[dict[str, Any]] = []
        spot_values: list[float] = []
        for row in rows:
            symbol = str(row["symbol"])
            strike = float(row.get("strike_price") or 0)
            opt_type = self._normalize_option_type(row.get("option_type"), symbol)
            if row.get("nifty_spot") is not None:
                spot_values.append(float(row["nifty_spot"]))
            if strike <= 0 or opt_type not in {"CE", "PE"}:
                continue
            contracts.append(
                {
                    "instrument_key": symbol,
                    "strike_price": strike,
                    "instrument_type": opt_type,
                    "expiry": str(row.get("expiry_date")),
                }
            )

        if not contracts:
            return {"atm": 0.0, "spot": 0.0, "symbols": [], "contracts": []}

        spot = float(spot_hint) if spot_hint is not None else (median(spot_values) if spot_values else 0.0)

        strikes = sorted({float(c["strike_price"]) for c in contracts})
        atm = min(strikes, key=lambda s: abs(s - spot)) if spot > 0 else strikes[len(strikes) // 2]
        atm_idx = strikes.index(atm)
        selected = set(strikes[max(0, atm_idx - strike_count) : atm_idx + strike_count + 1])

        selected_contracts = [c for c in contracts if float(c["strike_price"]) in selected]
        selected_contracts.sort(key=lambda c: (float(c["strike_price"]), c["instrument_type"]))

        return {
            "atm": atm,
            "spot": spot,
            "symbols": [c["instrument_key"] for c in selected_contracts],
            "contracts": selected_contracts,
        }

    async def get_quotes(self, symbols: list[str], as_of_time: datetime) -> list[dict[str, Any]]:
        if not symbols:
            return []

        sql = f"""
            SELECT DISTINCT ON (symbol)
                symbol,
                time,
                open,
                high,
                low,
                close
            FROM {self.options_table}
            WHERE symbol = ANY($1::text[])
              AND time <= $2
              AND close IS NOT NULL
              AND close > 0
            ORDER BY symbol, time DESC;
        """

        pool = await self._pool()
        try:
            async with pool.acquire() as conn:
                rows = await asyncio.wait_for(
                    conn.fetch(sql, symbols, as_of_time),
                    timeout=QUERY_TIMEOUT_SECONDS
                )
        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout ({QUERY_TIMEOUT_SECONDS}s) querying {len(symbols)} option quotes from {self.options_table}; "
                f"returning empty quotes to avoid blocking backtest intrabar checks."
            )
            return []
        except Exception as exc:
            logger.error(f"Error querying option quotes: {exc}; returning empty quotes.")
            return []

        by_symbol = {
            str(row["symbol"]): {
                "instrument_key": str(row["symbol"]),
                "last_price": float(row["close"]),
                "open": float(row["open"]) if row.get("open") is not None else None,
                "high": float(row["high"]) if row.get("high") is not None else None,
                "low": float(row["low"]) if row.get("low") is not None else None,
                "close": float(row["close"]) if row.get("close") is not None else None,
            }
            for row in rows
        }

        # Preserve input symbol order to keep strategy behavior deterministic.
        return [by_symbol[s] for s in symbols if s in by_symbol]
