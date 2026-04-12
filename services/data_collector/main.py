import os
import re
import uvicorn
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import asyncpg

from trading_core.providers import get_adapter
from trading_core.analytics import OptionGreeks
from trading_core.db import DatabaseManager
from trading_core.config import DB_URL

# These will be the core background logic modules for the service
# I'll create these in the next file write
from services.data_collector.live_recorder import recorder_manager

app = FastAPI(title="Unified Data Collector API")

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(value: str, field_name: str) -> str:
    if not value or not IDENTIFIER_RE.match(value):
        raise HTTPException(400, f"Invalid {field_name}: {value!r}")
    return value


def _quote_ident(value: str) -> str:
    return f'"{value}"'


def _parse_datetime_input(value: str, field_name: str, end_of_day: bool = False) -> datetime:
    text = (value or "").strip()
    if not text:
        raise HTTPException(400, f"{field_name} cannot be empty")
    try:
        if len(text) == 10:
            dt = datetime.fromisoformat(f"{text}T00:00:00")
            if end_of_day:
                dt = dt + timedelta(days=1, microseconds=-1)
            return dt
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as e:
        raise HTTPException(400, f"Invalid {field_name}: {text!r}") from e


def _gap_filter_sql_for_table(table_name: str) -> str:
    # For 1m historical candles, ignore overnight/weekend boundaries when counting gaps.
    if table_name == "ohlcv_1m":
        return """
          AND time::date = prev_time::date
          AND EXTRACT(ISODOW FROM time) BETWEEN 1 AND 5
          AND time::time BETWEEN TIME '09:15' AND TIME '15:30'
          AND prev_time::time BETWEEN TIME '09:15' AND TIME '15:30'
        """
    return ""

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DownloadRequest(BaseModel):
    option_symbol: str
    underlying_symbol: str
    start_date: str
    end_date: str
    strike: float
    option_type: str
    expiry_date: str
    provider: str = "fyers"

class SubscribeRequest(BaseModel):
    symbols: List[str]
    provider: str = "fyers"

class ChainRequest(BaseModel):
    underlying_symbol: str
    expiry_date: str
    strike_count: int = 10
    provider: str = "fyers"

@app.on_event("startup")
async def startup_event():
    await DatabaseManager.get_pool()
    from trading_core.db import MigrationManager
    await MigrationManager.run_migrations()

@app.on_event("shutdown")
async def shutdown_event():
    await DatabaseManager.close_pool()

@app.get("/auth/status")
async def auth_status(provider: str = "fyers"):
    adapter = get_adapter(provider)
    return {"authenticated": adapter.validate_token()}

@app.get("/auth/url")
async def auth_url(provider: str = "fyers"):
    adapter = get_adapter(provider)
    return {"url": adapter.generate_auth_link()}

@app.post("/download")
async def download_symbol(req: DownloadRequest):
    adapter = get_adapter(req.provider)
    
    try:
        # 1. Fetch Historical OHLC for Option and Spot
        option_ohlc = adapter.get_historical_data(req.option_symbol, req.start_date, req.end_date)
        spot_ohlc = adapter.get_historical_data(req.underlying_symbol, req.start_date, req.end_date)
        
        if not option_ohlc or not spot_ohlc:
            raise HTTPException(400, "Incomplete data returned for symbols.")
            
        # 2. Extract Greeks (Simplified logic for now, using the new core)
        # Note: In the future, I'll extract these to a background task
        
        # 3. Store to DB (I'll need to port the DB insert logic to the core)
        return {"status": "success", "count": len(option_ohlc)}
        
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/recorder/start")
async def start_recorder(provider: str = "fyers", mode: str = "lite"):
    status = await recorder_manager.start(provider, mode)
    return {"status": status}

@app.post("/recorder/stop")
async def stop_recorder(provider: str = "fyers"):
    status = await recorder_manager.stop(provider)
    return {"status": status}

@app.get("/recorder/status")
async def recorder_status(provider: str = "fyers"):
    return recorder_manager.get_status(provider)

@app.post("/recorder/subscribe")
async def subscribe_recorder(req: SubscribeRequest):
    symbols = await recorder_manager.subscribe(req.provider, req.symbols)
    return {"status": "success", "symbols": symbols}

@app.post("/recorder/unsubscribe")
async def unsubscribe_recorder(req: SubscribeRequest):
    symbols = await recorder_manager.unsubscribe(req.provider, req.symbols)
    return {"status": "success", "symbols": symbols}

@app.post("/chain/generate")
async def generate_chain(req: ChainRequest):
    adapter = get_adapter(req.provider)
    try:
        data = adapter.get_option_chain_symbols(req.underlying_symbol, req.expiry_date, req.strike_count)
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/expiries/list")
async def list_expiries(provider: Optional[str] = None, underlying_symbol: str = "NSE:NIFTY50-INDEX"):
    providers = [provider.lower()] if provider else ["fyers", "upstox"]
    data = {}
    errors = {}

    for p in providers:
        try:
            adapter = get_adapter(p)
            data[p] = adapter.get_option_expiries(underlying_symbol)
        except Exception as e:
            errors[p] = str(e)

    if provider and provider.lower() in errors:
        raise HTTPException(500, errors[provider.lower()])

    return {
        "status": "success" if not errors else "partial_success",
        "underlying_symbol": underlying_symbol,
        "data": data,
        "errors": errors,
    }

@app.get("/index-ticks/recent")
async def get_recent_index_ticks(limit: int = 20, provider: str = "fyers"):
    pool = await DatabaseManager.get_pool()
    table = f"broker_{provider}.market_ticks"
    try:
        async with pool.acquire() as conn:
            records = await conn.fetch(f"SELECT * FROM {table} ORDER BY time DESC LIMIT $1", limit)
            return {"status": "success", "ticks": [dict(r) for r in records]}
    except Exception as e:
        return {"status": "error", "message": str(e), "ticks": []}


@app.get("/db/overview")
async def db_overview(
    schemas: str = Query("broker_fyers,broker_upstox,analytics"),
    gap_minutes: int = Query(5, ge=1, le=1440),
):
    requested_schemas = [_validate_identifier(s.strip(), "schema") for s in schemas.split(",") if s.strip()]
    if not requested_schemas:
        raise HTTPException(400, "At least one schema must be provided")

    pool = await DatabaseManager.get_pool()
    async with pool.acquire() as conn:
        db_name = await conn.fetchval("SELECT current_database()")
        dbs = await conn.fetch(
            """
            SELECT datname
            FROM pg_database
            WHERE datistemplate = FALSE
            ORDER BY datname
            """
        )

        table_rows = await conn.fetch(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema = ANY($1::text[])
            ORDER BY table_schema, table_name
            """,
            requested_schemas,
        )

        columns_rows = await conn.fetch(
            """
            SELECT table_schema, table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = ANY($1::text[])
            ORDER BY table_schema, table_name, ordinal_position
            """,
            requested_schemas,
        )

        col_map: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
        for row in columns_rows:
            key = (row["table_schema"], row["table_name"])
            col_map.setdefault(key, []).append(
                {
                    "name": row["column_name"],
                    "type": row["data_type"],
                    "nullable": row["is_nullable"] == "YES",
                }
            )

        schema_payload: Dict[str, List[Dict[str, Any]]] = {s: [] for s in requested_schemas}
        gap_interval = timedelta(minutes=gap_minutes)

        for t in table_rows:
            schema = t["table_schema"]
            table = t["table_name"]
            q_table = f"{_quote_ident(schema)}.{_quote_ident(table)}"
            gap_filter_sql = _gap_filter_sql_for_table(table)

            columns = col_map.get((schema, table), [])
            col_names = {c["name"] for c in columns}
            has_time = "time" in col_names
            has_symbol = "symbol" in col_names

            row_count = await conn.fetchval(f"SELECT COUNT(*)::bigint FROM {q_table}")

            min_time = None
            max_time = None
            distinct_symbols = None
            gap_events = None
            max_gap_minutes = None

            if has_time:
                time_row = await conn.fetchrow(
                    f"SELECT MIN(time) AS min_time, MAX(time) AS max_time FROM {q_table}"
                )
                min_time = time_row["min_time"]
                max_time = time_row["max_time"]
            if has_symbol:
                distinct_symbols = await conn.fetchval(f"SELECT COUNT(DISTINCT symbol)::bigint FROM {q_table}")
            if has_time and has_symbol:
                gap_row = await conn.fetchrow(
                    f"""
                    WITH ordered AS (
                        SELECT symbol, time,
                               LAG(time) OVER (PARTITION BY symbol ORDER BY time) AS prev_time
                        FROM {q_table}
                    ), gaps AS (
                        SELECT EXTRACT(EPOCH FROM (time - prev_time))/60.0 AS gap_min
                        FROM ordered
                        WHERE prev_time IS NOT NULL
                                                    {gap_filter_sql}
                          AND time - prev_time > $1::interval
                    )
                    SELECT COUNT(*)::bigint AS gap_events,
                           MAX(gap_min) AS max_gap_minutes
                    FROM gaps
                    """,
                    gap_interval,
                )
                gap_events = int(gap_row["gap_events"] or 0)
                max_gap_minutes = float(gap_row["max_gap_minutes"]) if gap_row["max_gap_minutes"] is not None else None

            schema_payload[schema].append(
                {
                    "table": table,
                    "row_count": int(row_count or 0),
                    "time_range": {
                        "min": min_time,
                        "max": max_time,
                    } if has_time else None,
                    "distinct_symbols": int(distinct_symbols) if distinct_symbols is not None else None,
                    "gap_analysis": {
                        "gap_minutes_threshold": gap_minutes,
                        "gap_events": gap_events,
                        "max_gap_minutes": max_gap_minutes,
                    } if has_time and has_symbol else None,
                    "columns": columns,
                }
            )

    return {
        "status": "success",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "database": db_name,
        "all_databases": [r["datname"] for r in dbs],
        "schemas": [
            {
                "schema": s,
                "table_count": len(schema_payload.get(s, [])),
                "tables": schema_payload.get(s, []),
            }
            for s in requested_schemas
        ],
    }


@app.get("/db/table-detail")
async def db_table_detail(
    schema: str,
    table: str,
    gap_minutes: int = Query(5, ge=1, le=1440),
    symbol_limit: int = Query(25, ge=1, le=200),
    symbol_query: Optional[str] = None,
    from_time: Optional[str] = None,
    to_time: Optional[str] = None,
):
    schema = _validate_identifier(schema, "schema")
    table = _validate_identifier(table, "table")
    q_table = f"{_quote_ident(schema)}.{_quote_ident(table)}"
    gap_filter_sql = _gap_filter_sql_for_table(table)

    pool = await DatabaseManager.get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = $1
                  AND table_name = $2
            )
            """,
            schema,
            table,
        )
        if not exists:
            raise HTTPException(404, f"Table not found: {schema}.{table}")

        columns_rows = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = $1 AND table_name = $2
            ORDER BY ordinal_position
            """,
            schema,
            table,
        )
        columns = [
            {
                "name": r["column_name"],
                "type": r["data_type"],
                "nullable": r["is_nullable"] == "YES",
            }
            for r in columns_rows
        ]
        col_names = {c["name"] for c in columns}
        has_time = "time" in col_names
        has_symbol = "symbol" in col_names

        parsed_from_time = _parse_datetime_input(from_time, "from_time") if from_time else None
        parsed_to_time = _parse_datetime_input(to_time, "to_time", end_of_day=True) if to_time else None
        normalized_symbol_query = (symbol_query or "").strip()

        where_parts: List[str] = []
        where_args: List[Any] = []

        if normalized_symbol_query:
            if not has_symbol:
                raise HTTPException(400, "symbol_query filter is not supported for tables without a symbol column")
            where_args.append(f"%{normalized_symbol_query}%")
            where_parts.append(f"symbol ILIKE ${len(where_args)}")

        if parsed_from_time is not None:
            if not has_time:
                raise HTTPException(400, "from_time filter is not supported for tables without a time column")
            where_args.append(parsed_from_time)
            where_parts.append(f"time >= ${len(where_args)}")

        if parsed_to_time is not None:
            if not has_time:
                raise HTTPException(400, "to_time filter is not supported for tables without a time column")
            where_args.append(parsed_to_time)
            where_parts.append(f"time <= ${len(where_args)}")

        if parsed_from_time is not None and parsed_to_time is not None and parsed_from_time > parsed_to_time:
            raise HTTPException(400, "from_time must be less than or equal to to_time")

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        row_count = await conn.fetchval(f"SELECT COUNT(*)::bigint FROM {q_table} {where_sql}", *where_args)

        min_time = None
        max_time = None
        if has_time:
            time_row = await conn.fetchrow(
                f"SELECT MIN(time) AS min_time, MAX(time) AS max_time FROM {q_table} {where_sql}",
                *where_args,
            )
            min_time = time_row["min_time"]
            max_time = time_row["max_time"]

        symbol_ranges = []
        if has_time and has_symbol:
            symbol_rows = await conn.fetch(
                f"""
                SELECT symbol,
                       COUNT(*)::bigint AS records,
                       MIN(time) AS min_time,
                       MAX(time) AS max_time
                FROM {q_table}
                {where_sql}
                GROUP BY symbol
                ORDER BY records DESC
                LIMIT ${len(where_args) + 1}
                """,
                *where_args,
                symbol_limit,
            )
            symbol_ranges = [
                {
                    "symbol": r["symbol"],
                    "records": int(r["records"] or 0),
                    "min_time": r["min_time"],
                    "max_time": r["max_time"],
                }
                for r in symbol_rows
            ]

            gap_rows = await conn.fetch(
                f"""
                WITH ordered AS (
                    SELECT symbol, time,
                           LAG(time) OVER (PARTITION BY symbol ORDER BY time) AS prev_time
                    FROM {q_table}
                                        {where_sql}
                )
                SELECT symbol,
                       prev_time AS gap_start,
                       time AS gap_end,
                       EXTRACT(EPOCH FROM (time - prev_time))/60.0 AS missing_minutes
                FROM ordered
                WHERE prev_time IS NOT NULL
                             {gap_filter_sql}
                                    AND time - prev_time > ${len(where_args) + 1}::interval
                ORDER BY missing_minutes DESC
                LIMIT 100
                """,
                                *where_args,
                timedelta(minutes=gap_minutes),
            )
            gap_samples = [
                {
                    "symbol": r["symbol"],
                    "gap_start": r["gap_start"],
                    "gap_end": r["gap_end"],
                    "missing_minutes": float(r["missing_minutes"]),
                }
                for r in gap_rows
            ]
        else:
            gap_samples = []

    return {
        "status": "success",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "table": {
            "schema": schema,
            "name": table,
            "row_count": int(row_count or 0),
            "time_range": {
                "min": min_time,
                "max": max_time,
            } if has_time else None,
            "has_time": has_time,
            "has_symbol": has_symbol,
        },
        "columns": columns,
        "symbol_ranges": symbol_ranges,
        "gap_analysis": {
            "gap_minutes_threshold": gap_minutes,
            "sample_gaps": gap_samples,
        } if has_time and has_symbol else None,
        "filters": {
            "symbol_query": normalized_symbol_query or None,
            "from_time": parsed_from_time,
            "to_time": parsed_to_time,
        },
    }

@app.get("/recorder/events")
async def recorder_events(provider: str = "fyers"):
    return StreamingResponse(recorder_manager.event_generator(provider), media_type="text/event-stream")


VALID_DATA_TYPES = {
    "market_ticks": "market_ticks",
    "ohlcv_1m": "ohlcv_1m",
    "ohlcv_1min_from_ticks": "ohlcv_1min_from_ticks",
    "options_ohlc": "options_ohlc",
}

@app.get("/available-symbols")
async def available_symbols(
    provider: str = Query("fyers", description="Provider: fyers or upstox"),
    data_type: str = Query("options_ohlc", description="Table: market_ticks, ohlcv_1m, ohlcv_1min_from_ticks, options_ohlc"),
):
    """Return the distinct symbols available in the selected provider/table combination."""
    p = provider.lower()
    if p not in ("fyers", "upstox"):
        raise HTTPException(400, f"Invalid provider: {provider!r}. Must be 'fyers' or 'upstox'.")
    if data_type not in VALID_DATA_TYPES:
        raise HTTPException(400, f"Invalid data_type: {data_type!r}. Must be one of {list(VALID_DATA_TYPES)}.")

    schema = "broker_upstox" if p == "upstox" else "broker_fyers"
    table = VALID_DATA_TYPES[data_type]
    q_table = f"{_quote_ident(schema)}.{_quote_ident(table)}"

    pool = await DatabaseManager.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT DISTINCT symbol FROM {q_table} ORDER BY symbol ASC"
        )

    symbols = [r["symbol"] for r in rows]
    return {"status": "success", "provider": p, "data_type": data_type, "symbols": symbols}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
