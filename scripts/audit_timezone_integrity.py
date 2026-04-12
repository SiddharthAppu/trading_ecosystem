import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
TRADING_CORE_DIR = ROOT_DIR / "packages" / "trading_core"
if str(TRADING_CORE_DIR) not in sys.path:
    sys.path.append(str(TRADING_CORE_DIR))

from trading_core.db import DatabaseManager  # noqa: E402


IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_REPORT_DIR = ROOT_DIR / "logs" / "time_audit"
SPECIAL_SESSION_DATES = {
    date(2020, 11, 14),
    date(2021, 11, 4),
    date(2022, 10, 24),
    date(2023, 11, 12),
    date(2024, 11, 1),
}

TABLE_SET = {
    "market_ticks",
    "ohlcv_1m",
    "ohlcv_1min_from_ticks",
    "options_ohlc",
    "options_greeks_live",
}


@dataclass
class TableAudit:
    table: str
    total_rows: int
    date_mismatch_rows: int
    out_of_session_rows: int
    special_session_rows: int
    min_time: str | None
    max_time: str | None
    non_special_small_late_days: list[dict]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit DB timestamp consistency between UTC storage and IST market-day semantics."
    )
    parser.add_argument(
        "--provider",
        choices=["fyers", "upstox", "all"],
        default="all",
        help="Provider scope for broker schema tables.",
    )
    parser.add_argument(
        "--tables",
        default="market_ticks,ohlcv_1m,ohlcv_1min_from_ticks,options_ohlc,options_greeks_live",
        help="Comma-separated table names to audit within selected provider schema(s).",
    )
    parser.add_argument(
        "--start-date",
        help="Optional IST date lower bound YYYY-MM-DD.",
    )
    parser.add_argument(
        "--end-date",
        help="Optional IST date upper bound YYYY-MM-DD.",
    )
    parser.add_argument(
        "--report-dir",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory where JSON audit reports are written.",
    )
    return parser.parse_args()


def _parse_date(raw: str | None, label: str) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{label} must be YYYY-MM-DD") from exc


def _parse_tables(raw_tables: str) -> list[str]:
    parts = [part.strip() for part in raw_tables.split(",") if part.strip()]
    if not parts:
        raise ValueError("At least one table must be provided in --tables")
    invalid = [name for name in parts if name not in TABLE_SET]
    if invalid:
        raise ValueError(f"Unsupported table names in --tables: {', '.join(sorted(set(invalid)))}")
    ordered = []
    seen = set()
    for name in parts:
        if name not in seen:
            ordered.append(name)
            seen.add(name)
    return ordered


def _providers(provider_arg: str) -> list[str]:
    if provider_arg == "all":
        return ["fyers", "upstox"]
    return [provider_arg]


def _table_name(provider: str, table: str) -> str:
    return f"broker_{provider}.{table}"


def _format_dt(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


async def _audit_table(
    conn,
    provider: str,
    table: str,
    start_date: date | None,
    end_date: date | None,
) -> TableAudit:
    full_table = _table_name(provider, table)

    filters = []
    args: list[object] = []
    if start_date is not None:
        args.append(start_date)
        filters.append(f"(time AT TIME ZONE 'Asia/Kolkata')::date >= ${len(args)}")
    if end_date is not None:
        args.append(end_date)
        filters.append(f"(time AT TIME ZONE 'Asia/Kolkata')::date <= ${len(args)}")

    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

    summary_query = f"""
        SELECT
            COUNT(*)::bigint AS total_rows,
            COUNT(*) FILTER (
                WHERE time::date != (time AT TIME ZONE 'Asia/Kolkata')::date
            )::bigint AS date_mismatch_rows,
            COUNT(*) FILTER (
                WHERE (time AT TIME ZONE 'Asia/Kolkata')::time < TIME '09:15'
                   OR (time AT TIME ZONE 'Asia/Kolkata')::time > TIME '15:30'
            )::bigint AS out_of_session_rows,
            COUNT(*) FILTER (
                WHERE (time AT TIME ZONE 'Asia/Kolkata')::date = ANY($1::date[])
            )::bigint AS special_session_rows,
            MIN(time) AS min_time,
            MAX(time) AS max_time
        FROM {full_table}
        {where_sql}
    """

    summary_args = [sorted(SPECIAL_SESSION_DATES), *args]
    summary = await conn.fetchrow(summary_query, *summary_args)

    detail_query = f"""
        SELECT
            (time AT TIME ZONE 'Asia/Kolkata')::date AS ist_day,
            COUNT(*)::bigint AS rows,
            MIN((time AT TIME ZONE 'Asia/Kolkata')::time) AS min_ist_time,
            MAX((time AT TIME ZONE 'Asia/Kolkata')::time) AS max_ist_time
        FROM {full_table}
        WHERE (time AT TIME ZONE 'Asia/Kolkata')::time > TIME '15:30'
          AND EXTRACT(ISODOW FROM (time AT TIME ZONE 'Asia/Kolkata')) BETWEEN 1 AND 5
          AND (time AT TIME ZONE 'Asia/Kolkata')::date <> ALL($1::date[])
          {f"AND {' AND '.join(filters)}" if filters else ""}
        GROUP BY 1
        HAVING COUNT(*) <= 10
        ORDER BY ist_day DESC
        LIMIT 25
    """
    details = await conn.fetch(detail_query, *summary_args)

    return TableAudit(
        table=full_table,
        total_rows=int(summary["total_rows"] or 0),
        date_mismatch_rows=int(summary["date_mismatch_rows"] or 0),
        out_of_session_rows=int(summary["out_of_session_rows"] or 0),
        special_session_rows=int(summary["special_session_rows"] or 0),
        min_time=_format_dt(summary["min_time"]),
        max_time=_format_dt(summary["max_time"]),
        non_special_small_late_days=[
            {
                "ist_day": str(row["ist_day"]),
                "rows": int(row["rows"] or 0),
                "min_ist_time": str(row["min_ist_time"]),
                "max_ist_time": str(row["max_ist_time"]),
            }
            for row in details
        ],
    )


def _build_report_path(report_dir: str) -> Path:
    path = Path(report_dir)
    path.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    return path / f"timezone_audit_{stamp}.json"


async def main_async() -> int:
    args = parse_args()
    start_date = _parse_date(args.start_date, "--start-date")
    end_date = _parse_date(args.end_date, "--end-date")
    if start_date and end_date and start_date > end_date:
        raise ValueError("--start-date must be <= --end-date")

    tables = _parse_tables(args.tables)
    providers = _providers(args.provider)

    pool = await DatabaseManager.get_pool()
    try:
        audits: list[TableAudit] = []
        async with pool.acquire() as conn:
            db_timezone = await conn.fetchval("SHOW TIMEZONE")
            generated_at = await conn.fetchval("SELECT NOW()")

            for provider in providers:
                for table in tables:
                    audits.append(await _audit_table(conn, provider, table, start_date, end_date))
    finally:
        await DatabaseManager.close_pool()

    report = {
        "generated_at": _format_dt(generated_at),
        "timezone": str(db_timezone),
        "filters": {
            "provider": args.provider,
            "tables": tables,
            "start_date": str(start_date) if start_date else None,
            "end_date": str(end_date) if end_date else None,
        },
        "special_session_dates": [d.isoformat() for d in sorted(SPECIAL_SESSION_DATES)],
        "tables": [asdict(audit) for audit in audits],
    }

    report_path = _build_report_path(args.report_dir)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"[AUDIT] timezone={db_timezone} generated_at={_format_dt(generated_at)}")
    for audit in audits:
        print(
            f"[AUDIT] {audit.table}: total={audit.total_rows}, "
            f"date_mismatch={audit.date_mismatch_rows}, "
            f"out_of_session={audit.out_of_session_rows}, "
            f"special_session={audit.special_session_rows}, "
            f"small_late_days={len(audit.non_special_small_late_days)}"
        )
    print(f"[AUDIT] report_written={report_path}")
    return 0


def main() -> int:
    try:
        return asyncio.run(main_async())
    except Exception as exc:
        print(f"[AUDIT][ERROR] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
