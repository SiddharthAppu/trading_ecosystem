from __future__ import annotations

import argparse
import json
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
    except Exception:
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
            from urllib.parse import urlparse, parse_qs
            tv_url = t["links"]["tradingview_url"]
            if tv_url:
                parsed = urlparse(tv_url)
                qs = parse_qs(parsed.query)
                ts_sec = qs.get("time", [None])[0]
                if ts_sec:
                    # TradingView 'time' param is seconds, Pine Script 'time' is millis
                    timestamps_ms.append(str(int(ts_sec) * 1000))
                    sides.append(1 if t["side"] == "BUY" else -1)
                    prices.append(str(t.get("price") or 0))
        except Exception:
            continue

    if not timestamps_ms:
        return

    ts_list = ", ".join(timestamps_ms)
    side_list = ", ".join(map(str, sides))
    price_list = ", ".join(prices)
    symbol = trades[0]["symbol"]

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
            from urllib.parse import urlparse, parse_qs
            tv_url = t["links"]["tradingview_url"]
            if tv_url:
                parsed = urlparse(tv_url)
                qs = parse_qs(parsed.query)
                ts_sec = qs.get("time", [None])[0]
                if ts_sec:
                    timestamps_ms.append(str(int(ts_sec) * 1000))
                    sides.append(1 if t["side"] == "BUY" else -1)
                    prices.append(str(t.get("price") or 0))
        except Exception:
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

    import re
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pine_script, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate chart links from Astra journal JSONL events.")
    parser.add_argument("--journal", required=True, help="Path to journal JSONL file")
    parser.add_argument("--output-md", required=True, help="Path for markdown output")
    parser.add_argument("--output-json", required=True, help="Path for JSON output")
    parser.add_argument("--limit", type=int, default=300, help="Maximum number of events")
    parser.add_argument("--symbol", default="", help="Optional symbol substring filter")
    parser.add_argument("--event", default="", help="Optional exact event filter")
    parser.add_argument("--symbol-map", default="", help="Optional custom symbol map JSON")
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
    pine_path = json_path.with_suffix(".pine")

    write_markdown(md_path, events)
    write_pine(pine_path, events)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(events, indent=2), encoding="utf-8")

    print(f"Generated {len(events)} events")
    print(f"Markdown: {md_path}")
    print(f"JSON:     {json_path}")
    print(f"Pine:     {pine_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
