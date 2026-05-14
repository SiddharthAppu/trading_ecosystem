#!/usr/bin/env python3
"""
Standalone backtest entrypoint for strategy_runtime offline adapter.

Execution path:
  scripts/strategy_backtest.py
    -> services.strategy_runtime.offline_adapter.runner.run_strategy_adapter_backtest

Indicators are computed by trading_core analytics (TA-Lib when available,
in-house fallback otherwise).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from urllib.parse import urlparse

# ── DB ─────────────────────────────────────────────────────────────────────────
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 not installed.  pip install psycopg2-binary")
    sys.exit(1)

from dotenv import load_dotenv

_config_dir = os.getenv(
    "TRADING_CONFIG_DIR",
    os.path.join(os.path.dirname(__file__), "..", "config"),
)
_env_file = os.path.join(_config_dir, ".env")
if os.path.exists(_env_file):
    load_dotenv(_env_file)

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set. Check config/.env")
    sys.exit(1)


class BacktestConfigError(ValueError):
    """Raised when required backtest configuration is missing or invalid."""


def _database_descriptor(db_url: str) -> str:
    try:
        parsed = urlparse(db_url)
    except (TypeError, ValueError):
        return "unknown"
    host = parsed.hostname or "unknown-host"
    db_name = (parsed.path or "/").lstrip("/") or "unknown-db"
    return f"{host}/{db_name}"


def _require_value(name: str, value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise BacktestConfigError(f"Missing required config: {name}")
    return normalized


def _normalize_source_data_kind(raw_value: str) -> str:
    value = _require_value("source_data_kind", raw_value).lower()
    if value in {"bars", "ticks"}:
        return value
    raise BacktestConfigError(
        f"Invalid source_data_kind: {raw_value}. Expected one of: bars, ticks"
    )


def _validate_chunking_days(chunking_days: int) -> int:
    if chunking_days <= 0:
        raise BacktestConfigError("db_chunking_trading_days must be greater than 0")
    return chunking_days


def _validate_max_rows_per_chunk(max_rows_per_chunk: int) -> int:
    if max_rows_per_chunk <= 0:
        raise BacktestConfigError("max_rows_per_chunk must be greater than 0")
    return max_rows_per_chunk


def _validate_table_name(name: str, *, config_key: str) -> str:
    value = _require_value(config_key, name)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", value):
        raise BacktestConfigError(
            f"Invalid table name for {config_key}: {value}. Expected schema.table format"
        )
    return value


def _table_parts(table_name: str) -> tuple[str, str]:
    schema_name, relation_name = table_name.split(".", 1)
    return schema_name, relation_name


def _table_columns(conn, table_name: str) -> set[str]:
    schema_name, relation_name = _table_parts(table_name)
    sql = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (schema_name, relation_name))
        rows = cur.fetchall()
    return {str(row[0]) for row in rows}


def _validate_required_columns(conn, *, table_name: str, required_columns: set[str], config_key: str) -> None:
    available_columns = _table_columns(conn, table_name)
    if not available_columns:
        raise BacktestConfigError(f"Missing table: {config_key}={table_name}")
    missing_columns = sorted(required_columns - available_columns)
    if missing_columns:
        raise BacktestConfigError(
            f"Missing columns in {table_name}: {', '.join(missing_columns)}"
        )


def _validate_source_schema(conn, *, source_table: str, source_data_kind: str) -> None:
    if source_data_kind == "ticks":
        _validate_required_columns(
            conn,
            table_name=source_table,
            required_columns={"time", "symbol", "price", "volume"},
            config_key="source_table",
        )
        return

    if source_table == "master_broker.ohlcv_1m":
        _validate_required_columns(
            conn,
            table_name=source_table,
            required_columns={
                "time",
                "symbol",
                "open_upstox",
                "open_fyers",
                "high_upstox",
                "high_fyers",
                "low_upstox",
                "low_fyers",
                "master_close",
                "vol_upstox",
                "vol_fyers",
            },
            config_key="source_table",
        )
        return

    _validate_required_columns(
        conn,
        table_name=source_table,
        required_columns={"time", "symbol", "open", "high", "low", "close", "volume"},
        config_key="source_table",
    )


def _validate_options_schema(conn, *, options_source_table: str) -> None:
    _validate_required_columns(
        conn,
        table_name=options_source_table,
        required_columns={
            "time",
            "symbol",
            "open",
            "high",
            "low",
            "close",
            "expiry_date",
            "strike_price",
            "option_type",
            "nifty_spot",
        },
        config_key="options_source_table",
    )


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _runtime_components() -> tuple[type, type, type]:
    repo_root = _repo_root()
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from services.strategy_runtime.runtime import (  # noqa: PLC0415
        BarTimeframeAggregator,
        TickToOneMinuteBarAggregator,
    )
    from trading_core.models import Bar  # noqa: PLC0415

    return Bar, BarTimeframeAggregator, TickToOneMinuteBarAggregator


def _aggregate_rows_to_timeframe(rows_1m: list[dict], symbol: str, timeframe: str) -> list[dict]:
    if not rows_1m:
        return []
    if timeframe == "1m":
        return [dict(row) for row in rows_1m]

    timeframe_map = {"1m": 1, "5m": 5, "10m": 10}
    if timeframe not in timeframe_map:
        raise BacktestConfigError(f"Unsupported timeframe for aggregation: {timeframe}")

    Bar, BarTimeframeAggregator, _TickToOneMinuteBarAggregator = _runtime_components()
    aggregator = BarTimeframeAggregator(symbol, timeframe, timeframe_map[timeframe])
    aggregated_rows: list[dict] = []
    for row in rows_1m:
        bar = Bar(
            symbol=symbol,
            timestamp=row["time"],
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row.get("volume") or 0),
            timeframe="1m",
        )
        for aggregated_bar in aggregator.push_bar(bar):
            aggregated_rows.append(
                {
                    "time": aggregated_bar.timestamp,
                    "open": float(aggregated_bar.open),
                    "high": float(aggregated_bar.high),
                    "low": float(aggregated_bar.low),
                    "close": float(aggregated_bar.close),
                    "volume": int(aggregated_bar.volume),
                }
            )
    for aggregated_bar in aggregator.flush():
        aggregated_rows.append(
            {
                "time": aggregated_bar.timestamp,
                "open": float(aggregated_bar.open),
                "high": float(aggregated_bar.high),
                "low": float(aggregated_bar.low),
                "close": float(aggregated_bar.close),
                "volume": int(aggregated_bar.volume),
            }
        )
    return aggregated_rows


def _row_from_bar(bar) -> dict:
    return {
        "time": bar.timestamp,
        "open": float(bar.open),
        "high": float(bar.high),
        "low": float(bar.low),
        "close": float(bar.close),
        "volume": int(bar.volume),
    }


def _aggregate_ticks_to_timeframe(rows_ticks: list[dict], symbol: str, timeframe: str) -> tuple[list[dict], list[dict]]:
    if not rows_ticks:
        return [], []

    timeframe_map = {"1m": 1, "5m": 5, "10m": 10}
    if timeframe not in timeframe_map:
        raise BacktestConfigError(f"Unsupported timeframe for aggregation: {timeframe}")

    _Bar, BarTimeframeAggregator, TickToOneMinuteBarAggregator = _runtime_components()
    tick_to_one_min = TickToOneMinuteBarAggregator(symbol)
    one_min_to_target = (
        BarTimeframeAggregator(symbol, timeframe, timeframe_map[timeframe])
        if timeframe != "1m"
        else None
    )

    rows_1m: list[dict] = []
    bars_target: list[dict] = []

    for row in rows_ticks:
        completed_bars = tick_to_one_min.push_tick(
            row["time"],
            float(row["price"]),
            int(row.get("volume") or 0),
        )
        for completed_bar in completed_bars:
            row_1m = _row_from_bar(completed_bar)
            rows_1m.append(row_1m)
            if one_min_to_target is None:
                bars_target.append(dict(row_1m))
                continue
            for aggregated_bar in one_min_to_target.push_bar(completed_bar):
                bars_target.append(_row_from_bar(aggregated_bar))

    for completed_bar in tick_to_one_min.flush():
        row_1m = _row_from_bar(completed_bar)
        rows_1m.append(row_1m)
        if one_min_to_target is None:
            bars_target.append(dict(row_1m))
            continue
        for aggregated_bar in one_min_to_target.push_bar(completed_bar):
            bars_target.append(_row_from_bar(aggregated_bar))

    if one_min_to_target is not None:
        for aggregated_bar in one_min_to_target.flush():
            bars_target.append(_row_from_bar(aggregated_bar))

    return rows_1m, bars_target


# ── DB queries ─────────────────────────────────────────────────────────────────

def _load_master_index_bars(conn, symbol: str, from_date: str, to_date: str) -> list[dict]:
    sql = """
        SELECT
            time,
            COALESCE(open_upstox,  open_fyers)  AS open,
            COALESCE(high_upstox,  high_fyers)  AS high,
            COALESCE(low_upstox,   low_fyers)   AS low,
            master_close                         AS close,
            COALESCE(vol_upstox,   vol_fyers, 0) AS volume
        FROM master_broker.ohlcv_1m
        WHERE symbol = %s
          AND time >= %s::date
          AND time <  (%s::date + INTERVAL '1 day')
          AND master_close IS NOT NULL
        ORDER BY time
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (symbol, from_date, to_date))
        return [dict(r) for r in cur.fetchall()]


def _load_generic_bar_chunk(
    conn,
    *,
    source_table: str,
    symbol: str,
    chunk_start: date,
    chunk_end: date,
) -> list[dict]:
    sql = f"""
        SELECT time, open, high, low, close, COALESCE(volume, 0) AS volume
        FROM {source_table}
        WHERE symbol = %s
          AND time >= %s::date
          AND time < (%s::date + INTERVAL '1 day')
        ORDER BY time
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (symbol, chunk_start.isoformat(), chunk_end.isoformat()))
        return [dict(r) for r in cur.fetchall()]


def _load_tick_chunk(
    conn,
    *,
    source_table: str,
    symbol: str,
    chunk_start: date,
    chunk_end: date,
) -> list[dict]:
    sql = f"""
        SELECT time, price, COALESCE(volume, 0) AS volume
        FROM {source_table}
        WHERE symbol = %s
          AND time >= %s::date
          AND time < (%s::date + INTERVAL '1 day')
        ORDER BY time
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (symbol, chunk_start.isoformat(), chunk_end.isoformat()))
        return [dict(r) for r in cur.fetchall()]


def _chunked_dates(values: list[date], chunk_size: int) -> list[list[date]]:
    return [values[index : index + chunk_size] for index in range(0, len(values), chunk_size)]


def _load_trading_days(
    conn,
    *,
    source_table: str,
    source_data_kind: str,
    symbol: str,
    from_date: str,
    to_date: str,
) -> list[date]:
    if source_data_kind == "bars" and source_table == "master_broker.ohlcv_1m":
        sql = f"""
            SELECT DISTINCT time::date AS trade_day
            FROM {source_table}
            WHERE symbol = %s
              AND time >= %s::date
              AND time < (%s::date + INTERVAL '1 day')
              AND master_close IS NOT NULL
            ORDER BY trade_day
        """
    else:
        sql = f"""
            SELECT DISTINCT time::date AS trade_day
            FROM {source_table}
            WHERE symbol = %s
              AND time >= %s::date
              AND time < (%s::date + INTERVAL '1 day')
            ORDER BY trade_day
        """

    with conn.cursor() as cur:
        cur.execute(sql, (symbol, from_date, to_date))
        rows = cur.fetchall()
    return [row[0] for row in rows]


def _estimate_chunk_rows(
    conn,
    *,
    source_table: str,
    source_data_kind: str,
    symbol: str,
    chunk_start: date,
    chunk_end: date,
) -> int:
    if source_data_kind == "bars" and source_table == "master_broker.ohlcv_1m":
        sql = f"""
            SELECT COUNT(*)
            FROM {source_table}
            WHERE symbol = %s
              AND time >= %s::date
              AND time < (%s::date + INTERVAL '1 day')
              AND master_close IS NOT NULL
        """
    else:
        sql = f"""
            SELECT COUNT(*)
            FROM {source_table}
            WHERE symbol = %s
              AND time >= %s::date
              AND time < (%s::date + INTERVAL '1 day')
        """

    with conn.cursor() as cur:
        cur.execute(sql, (symbol, chunk_start.isoformat(), chunk_end.isoformat()))
        row = cur.fetchone()
    return int(row[0] if row else 0)


def _load_bar_chunk(
    conn,
    *,
    source_table: str,
    symbol: str,
    chunk_start: date,
    chunk_end: date,
) -> list[dict]:
    if source_table == "master_broker.ohlcv_1m":
        return _load_master_index_bars(conn, symbol, chunk_start.isoformat(), chunk_end.isoformat())
    return _load_generic_bar_chunk(
        conn,
        source_table=source_table,
        symbol=symbol,
        chunk_start=chunk_start,
        chunk_end=chunk_end,
    )


def _load_index_data(
    conn,
    *,
    source_table: str,
    source_data_kind: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    db_chunking_trading_days: int,
    max_rows_per_chunk: int,
) -> tuple[list[dict], list[dict]]:
    trading_days = _load_trading_days(
        conn,
        source_table=source_table,
        source_data_kind=source_data_kind,
        symbol=symbol,
        from_date=from_date,
        to_date=to_date,
    )
    if not trading_days:
        raise BacktestConfigError(
            f"Missing data: no trading days found in {source_table} for symbol={symbol} "
            f"between {from_date} and {to_date}"
        )

    day_chunks = _chunked_dates(trading_days, db_chunking_trading_days)
    rows_1m: list[dict] = []
    bars_target: list[dict] = []
    for day_chunk in day_chunks:
        chunk_start = day_chunk[0]
        chunk_end = day_chunk[-1]
        estimated_rows = _estimate_chunk_rows(
            conn,
            source_table=source_table,
            source_data_kind=source_data_kind,
            symbol=symbol,
            chunk_start=chunk_start,
            chunk_end=chunk_end,
        )
        if estimated_rows > max_rows_per_chunk:
            raise BacktestConfigError(
                "Chunk too large: "
                f"source_table={source_table} symbol={symbol} chunk={chunk_start.isoformat()}->{chunk_end.isoformat()} "
                f"estimated_rows={estimated_rows} max_rows_per_chunk={max_rows_per_chunk}"
            )
        if source_data_kind == "bars":
            rows_1m_chunk = _load_bar_chunk(
                conn,
                source_table=source_table,
                symbol=symbol,
                chunk_start=chunk_start,
                chunk_end=chunk_end,
            )
            rows_1m.extend(rows_1m_chunk)
            bars_target.extend(_aggregate_rows_to_timeframe(rows_1m_chunk, symbol, timeframe))
            continue

        tick_rows = _load_tick_chunk(
            conn,
            source_table=source_table,
            symbol=symbol,
            chunk_start=chunk_start,
            chunk_end=chunk_end,
        )
        rows_1m_chunk, bars_target_chunk = _aggregate_ticks_to_timeframe(tick_rows, symbol, timeframe)
        rows_1m.extend(rows_1m_chunk)
        bars_target.extend(bars_target_chunk)
    return rows_1m, bars_target


# ── Core backtest ──────────────────────────────────────────────────────────────

def run_backtest(
    conn,
    from_date: str,
    to_date: str,
    *,
    ema_period: int = 20,
    sma_period: int = 20,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal_period: int = 9,
    target_premium: float = 200.0,
    premium_tolerance: float = 50.0,
    sl_pct: float = 0.5,
    force_exit_1500_enabled: str = "false",
    force_exit_time_ist: str = "15:00",
    force_exit_debug_enabled: str = "false",
    force_exit_debug_to_journal: str = "false",
    index_symbol: str = "NSE:NIFTY50-INDEX",
    lot_size: int = 75,
    lot_quantity: int = 1,
    initial_capital: float = 100000.0,
    capital_model: str = "non_compounding",
    strategy_name: str = "nifty_trend_options",
    timeframe: str = "5m",
    log_file: str = "logs/strategy_runtime/runtime.log",
    run_name: str = "",
    source_table: str = "",
    source_data_kind: str = "",
    options_source_table: str = "",
    db_chunking_trading_days: int = 0,
    max_rows_per_chunk: int = 0,
    verbose: bool = True,
) -> dict:
    """Run backtest via strategy_runtime offline adapter."""
    source_table = _validate_table_name(source_table, config_key="source_table")
    source_data_kind = _normalize_source_data_kind(source_data_kind)
    options_source_table = _validate_table_name(options_source_table, config_key="options_source_table")
    db_chunking_trading_days = _validate_chunking_days(db_chunking_trading_days)
    max_rows_per_chunk = _validate_max_rows_per_chunk(max_rows_per_chunk)
    _validate_source_schema(conn, source_table=source_table, source_data_kind=source_data_kind)
    _validate_options_schema(conn, options_source_table=options_source_table)

    if verbose:
        _lot_qty_label = "auto (-1) — sized from capital each bar" if lot_quantity == -1 else str(lot_quantity)
        print(f"\n{'='*62}")
        print("  Backtest configuration")
        print(f"  {'─'*58}")
        print(f"  Strategy               : {strategy_name}")
        print(f"  Date range             : {from_date} -> {to_date}")
        print(f"  Timeframe              : {timeframe}")
        print(f"  Symbol                 : {index_symbol}")
        print(f"  Source table           : {source_table}")
        print(f"  Source data kind       : {source_data_kind}")
        print(f"  DB chunking days       : {db_chunking_trading_days}")
        print(f"  Max rows per chunk     : {max_rows_per_chunk}")
        print(f"  {'─'*58}")
        print(f"  Capital model          : {capital_model}")
        print(f"  Initial capital        : Rs {initial_capital:,.2f}")
        print(f"  Lot quantity           : {_lot_qty_label}")
        print(f"  Lot size               : {lot_size}")
        print(f"  {'─'*58}")
        print(f"  EMA period             : {ema_period}")
        print(f"  SMA period             : {sma_period}")
        print(f"  MACD                   : {macd_fast}/{macd_slow}/{macd_signal_period}")
        print(f"  Target premium         : {target_premium}  +/-{premium_tolerance}")
        print(f"  Stop loss pct          : {sl_pct*100:.0f}%  (options premium SL)")
        print(f"  Force exit enabled     : {force_exit_1500_enabled}")
        print(f"  Force exit time (IST)  : {force_exit_time_ist}")
        print(f"  Force-exit debug       : {force_exit_debug_enabled}")
        print(f"  Debug to journal       : {force_exit_debug_to_journal}")
        print(f"{'='*62}")

    rows_1m, bars_5m = _load_index_data(
        conn,
        source_table=source_table,
        source_data_kind=source_data_kind,
        symbol=index_symbol,
        timeframe=timeframe,
        from_date=from_date,
        to_date=to_date,
        db_chunking_trading_days=db_chunking_trading_days,
        max_rows_per_chunk=max_rows_per_chunk,
    )

    if verbose:
        if rows_1m:
            print(f"  Index: {len(rows_1m)} 1m bars → {len(bars_5m)} 5m bars")
        else:
            print(f"  No index bars found for {index_symbol} in {from_date}→{to_date}")

    return _run_strategy_adapter_mode(
        bars_5m=bars_5m,
        bars_1m=rows_1m,
        from_date=from_date,
        to_date=to_date,
        strategy_name=strategy_name,
        timeframe=timeframe,
        index_symbol=index_symbol,
        source_table=source_table,
        source_data_kind=source_data_kind,
        options_source_table=options_source_table,
        db_chunking_trading_days=db_chunking_trading_days,
        max_rows_per_chunk=max_rows_per_chunk,
        ema_period=ema_period,
        sma_period=sma_period,
        macd_fast=macd_fast,
        macd_slow=macd_slow,
        macd_signal_period=macd_signal_period,
        target_premium=target_premium,
        premium_tolerance=premium_tolerance,
        sl_pct=sl_pct,
        force_exit_1500_enabled=force_exit_1500_enabled,
        force_exit_time_ist=force_exit_time_ist,
        force_exit_debug_enabled=force_exit_debug_enabled,
        force_exit_debug_to_journal=force_exit_debug_to_journal,
        lot_size=lot_size,
        lot_quantity=lot_quantity,
        initial_capital=initial_capital,
        capital_model=capital_model,
        log_file=log_file,
        run_name=run_name,
        adapter_mode="backtest",
        verbose=verbose,
    )


def _run_strategy_adapter_mode(
    *,
    bars_5m: list[dict],
    bars_1m: list[dict],
    from_date: str,
    to_date: str,
    strategy_name: str,
    timeframe: str,
    index_symbol: str,
    source_table: str,
    source_data_kind: str,
    options_source_table: str,
    db_chunking_trading_days: int,
    max_rows_per_chunk: int,
    ema_period: int,
    sma_period: int,
    macd_fast: int,
    macd_slow: int,
    macd_signal_period: int,
    target_premium: float,
    premium_tolerance: float,
    sl_pct: float,
    force_exit_1500_enabled: str,
    force_exit_time_ist: str,
    force_exit_debug_enabled: str,
    force_exit_debug_to_journal: str,
    lot_size: int,
    lot_quantity: int,
    initial_capital: float,
    capital_model: str,
    log_file: str,
    run_name: str,
    adapter_mode: str,
    verbose: bool,
) -> dict:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    try:
        from services.strategy_runtime.offline_adapter.runner import run_strategy_adapter_backtest
    except (ImportError, OSError, ValueError) as exc:
        raise RuntimeError(f"Adapter runner unavailable: {exc}") from exc

    adapter_result = run_strategy_adapter_backtest(
        bars_5m=bars_5m,
        bars_1m=bars_1m,
        from_date=from_date,
        to_date=to_date,
        strategy_name=strategy_name,
        timeframe=timeframe,
        symbol=index_symbol,
        indicators=[f"ema_{ema_period}", f"sma_{sma_period}", "macd"],
        strategy_params={
            "lot_quantity": lot_quantity,
            "lot_size": lot_size,
            "initial_capital": initial_capital,
            "capital_model": capital_model,
            "provider": "paper",
            "underlying_symbol": index_symbol,
            "target_premium": target_premium,
            "premium_tolerance": premium_tolerance,
            "stop_loss_premium_pct": sl_pct,
            "force_exit_1500_enabled": force_exit_1500_enabled,
            "force_exit_time_ist": force_exit_time_ist,
            "force_exit_debug_enabled": force_exit_debug_enabled,
            "force_exit_debug_to_journal": force_exit_debug_to_journal,
            "strike_scan_count": 10,
            "ema_period": ema_period,
            "sma_period": sma_period,
            "macd_fast": macd_fast,
            "macd_slow": macd_slow,
            "macd_signal": macd_signal_period,
            "source_mode": adapter_mode,
            "source_db": _database_descriptor(DATABASE_URL),
            "index_source_table": source_table,
            "source_data_kind": source_data_kind,
            "options_source_table": options_source_table,
            "db_chunking_trading_days": db_chunking_trading_days,
            "max_rows_per_chunk": max_rows_per_chunk,
        },
        log_file=log_file,
        run_name=run_name or None,
    )
    if verbose:
        print(f"\n  Adapter artifacts → journal={adapter_result.journal_path}")
        print(f"  Adapter artifacts → summary={adapter_result.summary_path}")
    return {
        "trades": adapter_result.trades,
        "summary": adapter_result.summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtest nifty_trend_options with historical DB data"
    )
    parser.add_argument("--from", dest="from_date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--ema-period", type=int, default=20)
    parser.add_argument("--sma-period", type=int, default=20)
    parser.add_argument("--macd-fast", type=int, default=12)
    parser.add_argument("--macd-slow", type=int, default=26)
    parser.add_argument("--macd-signal", type=int, default=9)
    parser.add_argument("--target-premium", type=float, default=200.0)
    parser.add_argument("--premium-tolerance", type=float, default=50.0)
    parser.add_argument(
        "--sl-pct",
        type=float,
        default=0.5,
        help="Stop-loss as fraction of entry premium (0.5 = 50%%)",
    )
    parser.add_argument(
        "--force-exit-1500-enabled",
        default=os.getenv("NIFTY_FORCE_EXIT_1500_ENABLED", "false"),
        help="Enable forced exit at/after configured IST time (true/false).",
    )
    parser.add_argument(
        "--force-exit-time-ist",
        default=os.getenv("NIFTY_FORCE_EXIT_TIME_IST", "15:00"),
        help="Forced exit cutoff in IST (HH:MM).",
    )
    parser.add_argument(
        "--force-exit-debug-enabled",
        default=os.getenv("NIFTY_FORCE_EXIT_DEBUG_ENABLED", "false"),
        help="Enable forced-exit debug instrumentation (true/false).",
    )
    parser.add_argument(
        "--force-exit-debug-to-journal",
        default=os.getenv("NIFTY_FORCE_EXIT_DEBUG_TO_JOURNAL", "false"),
        help="Emit forced-exit debug payloads to JSONL journal (true/false).",
    )
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--lot-quantity", type=int, default=1)
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=100000.0,
        help="Initial capital baseline used by adapter capital model.",
    )
    parser.add_argument(
        "--capital-model",
        choices=["non_compounding", "compounding"],
        default="non_compounding",
        help="Capital model used by adapter runner.",
    )
    parser.add_argument("--index-symbol", default="NSE:NIFTY50-INDEX")
    parser.add_argument(
        "--strategy-name",
        default="nifty_trend_options",
        help="Strategy name metadata written into backtest artifacts.",
    )
    parser.add_argument(
        "--timeframe",
        default="5m",
        help="Timeframe metadata written into backtest artifacts.",
    )
    parser.add_argument(
        "--log-file",
        default="logs/strategy_runtime/runtime.log",
        help="Main log path used by backtest artifacts.",
    )
    parser.add_argument(
        "--run-name",
        default="",
        help="Optional run name for backtest artifacts.",
    )
    parser.add_argument(
        "--source-table",
        default=os.getenv("STRATEGY_RUNTIME_SOURCE_TABLE", "").strip(),
        help="Required source table for backtest input data.",
    )
    parser.add_argument(
        "--source-data-kind",
        default=os.getenv("STRATEGY_RUNTIME_SOURCE_DATA_KIND", "").strip(),
        help="Required source data kind: bars or ticks.",
    )
    parser.add_argument(
        "--options-source-table",
        default=os.getenv("STRATEGY_RUNTIME_OPTIONS_SOURCE_TABLE", "").strip(),
        help="Required historical options source table used by resolver.",
    )
    parser.add_argument(
        "--db-chunking-trading-days",
        type=int,
        default=int(os.getenv("STRATEGY_RUNTIME_DB_CHUNKING_TRADING_DAYS", "0") or "0"),
        help="Required number of trading days to load per DB chunk.",
    )
    parser.add_argument(
        "--max-rows-per-chunk",
        type=int,
        default=int(os.getenv("STRATEGY_RUNTIME_MAX_ROWS_PER_CHUNK", "0") or "0"),
        help="Required fail-fast ceiling for estimated rows per DB chunk.",
    )
    parser.add_argument(
        "--export-trades",
        metavar="FILE",
        help="Export trades to CSV (e.g. trades.csv)",
    )
    args = parser.parse_args()

    conn = psycopg2.connect(DATABASE_URL)
    try:
        result = run_backtest(
            conn,
            from_date=args.from_date,
            to_date=args.to_date,
            ema_period=args.ema_period,
            sma_period=args.sma_period,
            macd_fast=args.macd_fast,
            macd_slow=args.macd_slow,
            macd_signal_period=args.macd_signal,
            target_premium=args.target_premium,
            premium_tolerance=args.premium_tolerance,
            sl_pct=args.sl_pct,
            force_exit_1500_enabled=args.force_exit_1500_enabled,
            force_exit_time_ist=args.force_exit_time_ist,
            force_exit_debug_enabled=args.force_exit_debug_enabled,
            force_exit_debug_to_journal=args.force_exit_debug_to_journal,
            lot_size=args.lot_size,
            lot_quantity=args.lot_quantity,
            initial_capital=args.initial_capital,
            capital_model=args.capital_model,
            index_symbol=args.index_symbol,
            strategy_name=args.strategy_name,
            timeframe=args.timeframe,
            log_file=args.log_file,
            run_name=args.run_name,
            source_table=args.source_table,
            source_data_kind=args.source_data_kind,
            options_source_table=args.options_source_table,
            db_chunking_trading_days=args.db_chunking_trading_days,
            max_rows_per_chunk=args.max_rows_per_chunk,
        )
        if args.export_trades and result["trades"]:
            import csv

            with open(args.export_trades, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(result["trades"][0].keys()))
                writer.writeheader()
                writer.writerows(result["trades"])
            print(f"\n  Trades exported → {args.export_trades}")
    except BacktestConfigError as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1) from exc
    finally:
        conn.close()


if __name__ == "__main__":
    main()
