from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from services.strategy_runtime.journal_links import build_event_view


def _load_symbol_map(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        return {}
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k).strip().upper(): str(v).strip() for k, v in data.items() if str(k).strip()}


def read_events(
    journal_path: Path,
    limit: int,
    symbol_filter: str,
    event_filter: str,
    symbol_map: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not journal_path.exists():
        return rows

    symbol_upper = symbol_filter.upper().strip()
    event_upper = event_filter.upper().strip()

    with journal_path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            symbol = str(entry.get("symbol", "")).upper()
            event = str(entry.get("event", "")).upper()

            if symbol_upper and symbol_upper not in symbol:
                continue
            if event_upper and event_upper != event:
                continue

            rows.append(build_event_view(entry, line_no, symbol_map=symbol_map))

    if limit <= 0:
        return []
    return rows[-limit:]


def write_markdown(path: Path, events: list[dict[str, Any]]) -> None:
    lines = [
        "# Astra Journal Event Links",
        "",
        "| Event Time (UTC) | Event | Symbol | Side | TF | Local Chart | TradingView |",
        "|---|---|---|---|---|---|---|",
    ]

    for row in events:
        local_link = row["links"]["local_chart_url"]
        tv_link = row["links"]["tradingview_url"]
        local_md = f"[Open]({local_link})"
        tv_md = f"[Open]({tv_link})" if tv_link else "unmapped"
        side = row.get("side") or "-"
        lines.append(
            f"| {row['event_ts']} | {row['event']} | {row['symbol']} | {side} | {row['timeframe']} | {local_md} | {tv_md} |"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_pine(path: Path, events: list[dict[str, Any]]) -> None:
    # Look for RUNTIME_HEADER to get indicators
    indicators = []
    for e in events:
        if e["event"] == "RUNTIME_HEADER":
            indicators = e.get("data", {}).get("indicators") or []
            break

    # Filter for trade-related events only
    trades = [e for e in events if e["event"] in {"ORDER_FILL", "FILL"}]
    if not trades:
        return

    # Extract timestamps, sides, and prices
    timestamps_ms = []
    sides = []
    prices = []
    for t in trades:
        try:
            from urllib.parse import parse_qs, urlparse

            tv_url = t["links"]["tradingview_url"]
            if tv_url:
                parsed = urlparse(tv_url)
                qs = parse_qs(parsed.query)
                ts_sec = qs.get("time", [None])[0]
                if ts_sec:
                    timestamps_ms.append(str(int(ts_sec) * 1000))
                    sides.append(1 if t["side"] == "BUY" else -1)
                    prices.append(str(t.get("price") or 0))
        except (OSError, ValueError, TypeError, KeyError):
            continue

    if not timestamps_ms:
        return

    ts_list = ", ".join(timestamps_ms)
    side_list = ", ".join(map(str, sides))
    price_list = ", ".join(prices)
    symbol = trades[0]["symbol"]

    # Build dynamic indicator code
    plot_code = []
    label_calc_code = []
    label_text_code = []

    for ind in indicators:
        # EMA
        m = re.fullmatch(r"ema_(\d+)", ind)
        if m:
            period = m.group(1)
            var_name = f"ema{period}"
            plot_code.append(f"{var_name} = ta.ema(close, {period})")
            plot_code.append(f'plot({var_name}, color=color.new(color.blue, 50), title="EMA {period}")')
            label_text_code.append(f' + "\\nEMA{period}: " + str.tostring({var_name}, "#.##")')
            continue
        
        # SMA
        m = re.fullmatch(r"sma_(\d+)", ind)
        if m:
            period = m.group(1)
            var_name = f"sma{period}"
            plot_code.append(f"{var_name} = ta.sma(close, {period})")
            plot_code.append(f'plot({var_name}, color=color.new(color.orange, 50), title="SMA {period}")')
            label_text_code.append(f' + "\\nSMA{period}: " + str.tostring({var_name}, "#.##")')
            continue

        # RSI
        m = re.fullmatch(r"rsi_(\d+)", ind)
        if m:
            period = m.group(1)
            var_name = f"rsi{period}"
            label_calc_code.append(f"{var_name} = ta.rsi(close, {period})")
            label_text_code.append(f' + "\\nRSI{period}: " + str.tostring({var_name}, "#.##")')
            continue
        
        # MACD
        if ind == "macd":
            label_calc_code.append("[macdLine, signalLine, histLine] = ta.macd(close, 12, 26, 9)")
            label_text_code.append(' + "\\nMACD: " + str.tostring(macdLine, "#.##") + " / " + str.tostring(signalLine, "#.##")')
            continue

    plot_section = "\n".join(plot_code)
    label_calc_section = "\n".join(label_calc_code)
    label_text_section = "\n          ".join(label_text_code)

    pine_script = f"""//@version=6
indicator("Astra Trade Markers: {symbol}", overlay=true, max_labels_count=500)

// --- Astra Auto-Generated Data ---
var int[] t_times = array.from({ts_list}) // timestamps in ms
var int[] t_sides = array.from({side_list})
var float[] t_prices = array.from({price_list})

// --- Dynamic Indicators ---
{plot_section}
{label_calc_section}

// Check current bar for trade events
for i = 0 to array.size(t_times) - 1
    int tx = array.get(t_times, i)
    if time <= tx and (na(time_close) or tx < time_close)
        float px = array.get(t_prices, i)
        int sx = array.get(t_sides, i)
        
        string txt = (sx == 1 ? "BUY" : "SELL") + (px > 0 ? "\\n" + str.tostring(px) : "")
        txt := txt {label_text_section}
        
        color col = sx == 1 ? color.green : color.red
        label.new(bar_index, sx == 1 ? low : high, txt, 
                  color=col, textcolor=color.white, 
                  style=sx == 1 ? label.style_label_up : label.style_label_down, 
                  size=size.small)
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pine_script, encoding="utf-8")


def _safe_table_name(raw: object, fallback: str) -> str:
    value = str(raw or "").strip()
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?", value):
        return value
    return fallback


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _extract_source_context(events: list[dict[str, Any]]) -> dict[str, str]:
    runtime_header = next((e for e in events if str(e.get("event", "")).upper() == "RUNTIME_HEADER"), None)
    data = runtime_header.get("data", {}) if isinstance(runtime_header, dict) else {}
    if not isinstance(data, dict):
        data = {}
    source = data.get("source") if isinstance(data.get("source"), dict) else {}

    index_table = _safe_table_name(
        source.get("index_source_table") or data.get("index_source_table"),
        "master_broker.ohlcv_1m",
    )
    options_table = _safe_table_name(
        source.get("options_source_table") or data.get("options_source_table"),
        "master_broker.options_ohlc_1m_fromupstox",
    )

    return {
        "source_mode": str(source.get("source_mode") or data.get("source_mode") or data.get("mode") or "unknown"),
        "provider": str(source.get("provider") or data.get("provider") or "unknown"),
        "source_db": str(source.get("source_db") or data.get("source_db") or "unknown"),
        "index_table": index_table,
        "options_table": options_table,
    }


def _collect_trade_audit_rows(events: list[dict[str, Any]]) -> list[tuple[str, str, str, float, str]]:
    rows: list[tuple[str, str, str, float, str]] = []
    for event in events:
        event_name = str(event.get("event") or "").upper()
        if event_name not in {"ORDER_FILL", "FILL"}:
            continue

        ts = str(event.get("event_ts") or "").strip()
        symbol = str(event.get("symbol") or "").strip()
        side = str(event.get("side") or "").upper().strip() or "UNKNOWN"
        price_raw = event.get("price")
        if not ts or not symbol or price_raw is None:
            continue

        try:
            price = float(price_raw)
        except (TypeError, ValueError):
            continue

        rows.append((ts, symbol, side, price, event_name))
    return rows


def _collect_entry_audit_rows(events: list[dict[str, Any]]) -> list[tuple[str, str, float, str]]:
    rows: list[tuple[str, str, float, str]] = []
    for event in events:
        event_name = str(event.get("event") or "").upper()
        if event_name != "ENTRY_PASSED":
            continue

        ts = str(event.get("event_ts") or "").strip()
        symbol = str(event.get("symbol") or "").strip()
        price_raw = event.get("price")
        if not ts or not symbol or price_raw is None:
            continue

        try:
            price = float(price_raw)
        except (TypeError, ValueError):
            continue

        rows.append((ts, symbol, price, event_name))
    return rows


def write_audit_sql(path: Path, events: list[dict[str, Any]], *, price_tolerance: float) -> None:
    source_ctx = _extract_source_context(events)
    trade_rows = _collect_trade_audit_rows(events)
    entry_rows = _collect_entry_audit_rows(events)

    lines: list[str] = [
        "-- Astra Journal Audit SQL",
        "-- Generated from journal_event_linker.py",
        f"-- source_mode: {source_ctx['source_mode']}",
        f"-- provider: {source_ctx['provider']}",
        f"-- source_db: {source_ctx['source_db']}",
        f"-- options_table: {source_ctx['options_table']}",
        f"-- index_table: {source_ctx['index_table']}",
        f"-- price_tolerance: {price_tolerance}",
        "",
    ]

    if trade_rows:
        trade_values = ",\n".join(
            f"    ({_sql_string(ts)}::timestamptz, {_sql_string(symbol)}, {_sql_string(side)}, {price}, {_sql_string(event_name)})"
            for ts, symbol, side, price, event_name in trade_rows
        )
        lines.extend(
            [
                "-- 1) Option fill audit (mismatch-focused)",
                "WITH journal_rows(event_ts, symbol, side, expected_price, event_name) AS (",
                "  VALUES",
                trade_values,
                "),",
                "option_compare AS (",
                "  SELECT",
                "    j.event_ts,",
                "    j.symbol,",
                "    j.side,",
                "    j.expected_price,",
                "    q.time AS db_time,",
                "    q.close AS db_price,",
                "    CASE",
                "      WHEN q.close IS NULL THEN 'MISSING_DB_ROW'",
                f"      WHEN ABS(q.close - j.expected_price) <= {price_tolerance} THEN 'MATCH'",
                "      ELSE 'PRICE_MISMATCH'",
                "    END AS status",
                "  FROM journal_rows j",
                "  LEFT JOIN LATERAL (",
                "    SELECT time, close",
                f"    FROM {source_ctx['options_table']}",
                "    WHERE symbol = j.symbol",
                "      AND time <= j.event_ts",
                "      AND close IS NOT NULL",
                "    ORDER BY time DESC",
                "    LIMIT 1",
                "  ) q ON TRUE",
                ")",
                "SELECT *",
                "FROM option_compare",
                "WHERE status <> 'MATCH'",
                "ORDER BY event_ts, symbol;",
                "",
                "-- 1b) Option fill audit summary",
                "WITH journal_rows(event_ts, symbol, side, expected_price, event_name) AS (",
                "  VALUES",
                trade_values,
                "),",
                "option_compare AS (",
                "  SELECT",
                "    CASE",
                "      WHEN q.close IS NULL THEN 'MISSING_DB_ROW'",
                f"      WHEN ABS(q.close - j.expected_price) <= {price_tolerance} THEN 'MATCH'",
                "      ELSE 'PRICE_MISMATCH'",
                "    END AS status",
                "  FROM journal_rows j",
                "  LEFT JOIN LATERAL (",
                "    SELECT time, close",
                f"    FROM {source_ctx['options_table']}",
                "    WHERE symbol = j.symbol",
                "      AND time <= j.event_ts",
                "      AND close IS NOT NULL",
                "    ORDER BY time DESC",
                "    LIMIT 1",
                "  ) q ON TRUE",
                ")",
                "SELECT status, COUNT(*) AS rows_count",
                "FROM option_compare",
                "GROUP BY status",
                "ORDER BY status;",
                "",
            ]
        )
    else:
        lines.extend(["-- No ORDER_FILL/FILL events found; option fill audit skipped.", ""])

    if entry_rows:
        entry_values = ",\n".join(
            f"    ({_sql_string(ts)}::timestamptz, {_sql_string(symbol)}, {price}, {_sql_string(event_name)})"
            for ts, symbol, price, event_name in entry_rows
        )
        lines.extend(
            [
                "-- 2) Entry spot audit (ENTRY_PASSED against reconstructed 5m bucket close)",
                "WITH journal_rows(event_ts, symbol, expected_price, event_name) AS (",
                "  VALUES",
                entry_values,
                "),",
                "index_compare AS (",
                "  SELECT",
                "    j.event_ts,",
                "    j.symbol,",
                "    j.expected_price,",
                "    q.time AS db_time,",
                "    q.master_close AS db_price,",
                "    CASE",
                "      WHEN q.master_close IS NULL THEN 'MISSING_DB_ROW'",
                f"      WHEN ABS(q.master_close - j.expected_price) <= {price_tolerance} THEN 'MATCH'",
                "      ELSE 'PRICE_MISMATCH'",
                "    END AS status",
                "  FROM journal_rows j",
                "  LEFT JOIN LATERAL (",
                "    SELECT",
                "      (date_trunc('hour', time) + ((EXTRACT(minute FROM time)::int / 5) * INTERVAL '5 minute')) AS time,",
                "      (array_agg(master_close ORDER BY time DESC))[1] AS master_close",
                f"    FROM {source_ctx['index_table']}",
                "    WHERE symbol = j.symbol",
                "      AND time >= j.event_ts",
                "      AND time < (j.event_ts + INTERVAL '5 minute')",
                "      AND master_close IS NOT NULL",
                "    GROUP BY 1",
                "    HAVING (date_trunc('hour', time) + ((EXTRACT(minute FROM time)::int / 5) * INTERVAL '5 minute')) = j.event_ts",
                "    LIMIT 1",
                "  ) q ON TRUE",
                ")",
                "SELECT *",
                "FROM index_compare",
                "WHERE status <> 'MATCH'",
                "ORDER BY event_ts, symbol;",
                "",
                "-- 2b) Entry spot audit (strict: compare against latest 1m row at or before event_ts)",
                "WITH journal_rows(event_ts, symbol, expected_price, event_name) AS (",
                "  VALUES",
                entry_values,
                "),",
                "index_compare_strict_1m AS (",
                "  SELECT",
                "    j.event_ts,",
                "    j.symbol,",
                "    j.expected_price,",
                "    q.time AS db_time,",
                "    q.master_close AS db_price,",
                "    CASE",
                "      WHEN q.master_close IS NULL THEN 'MISSING_DB_ROW'",
                f"      WHEN ABS(q.master_close - j.expected_price) <= {price_tolerance} THEN 'MATCH'",
                "      ELSE 'PRICE_MISMATCH'",
                "    END AS status",
                "  FROM journal_rows j",
                "  LEFT JOIN LATERAL (",
                "    SELECT time, master_close",
                f"    FROM {source_ctx['index_table']}",
                "    WHERE symbol = j.symbol",
                "      AND time <= j.event_ts",
                "      AND master_close IS NOT NULL",
                "    ORDER BY time DESC",
                "    LIMIT 1",
                "  ) q ON TRUE",
                ")",
                "SELECT *",
                "FROM index_compare_strict_1m",
                "WHERE status <> 'MATCH'",
                "ORDER BY event_ts, symbol;",
                "",
            ]
        )
    else:
        lines.extend(["-- No ENTRY_PASSED events found; index spot audit skipped.", ""])

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate chart links from Astra journal JSONL events.")
    parser.add_argument("--journal", required=True, help="Path to journal JSONL file")
    parser.add_argument("--output-md", required=True, help="Path for markdown output")
    parser.add_argument("--output-json", required=True, help="Path for JSON output")
    parser.add_argument("--output-sql", default="", help="Optional path for SQL audit script output")
    parser.add_argument("--limit", type=int, default=300, help="Maximum number of events")
    parser.add_argument("--symbol", default="", help="Optional symbol substring filter")
    parser.add_argument("--event", default="", help="Optional exact event filter")
    parser.add_argument("--symbol-map", default="", help="Optional custom symbol map JSON")
    parser.add_argument("--price-tolerance", type=float, default=0.05, help="Absolute price tolerance used in SQL audit")
    args = parser.parse_args()

    symbol_map = _load_symbol_map(args.symbol_map)
    events = read_events(
        journal_path=Path(args.journal),
        limit=args.limit,
        symbol_filter=args.symbol,
        event_filter=args.event,
        symbol_map=symbol_map,
    )

    md_path = Path(args.output_md)
    json_path = Path(args.output_json)
    sql_path = Path(args.output_sql) if args.output_sql else json_path.with_suffix(".audit.sql")
    pine_path = json_path.with_suffix(".pine")

    write_markdown(md_path, events)
    write_pine(pine_path, events)
    write_audit_sql(sql_path, events, price_tolerance=max(0.0, float(args.price_tolerance)))
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(events, indent=2), encoding="utf-8")

    print(f"Generated {len(events)} events")
    print(f"Markdown: {md_path}")
    print(f"JSON:     {json_path}")
    print(f"Pine:     {pine_path}")
    print(f"SQL:      {sql_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
