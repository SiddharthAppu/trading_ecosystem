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
        "| Event Time (UTC) | Event | Symbol | TF | Local Chart | TradingView |",
        "|---|---|---|---|---|---|",
    ]

    for row in events:
        local_link = row["links"]["local_chart_url"]
        tv_link = row["links"]["tradingview_url"]
        local_md = f"[Open]({local_link})"
        tv_md = f"[Open]({tv_link})" if tv_link else "unmapped"
        lines.append(
            f"| {row['event_ts']} | {row['event']} | {row['symbol']} | {row['timeframe']} | {local_md} | {tv_md} |"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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

    write_markdown(md_path, events)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(events, indent=2), encoding="utf-8")

    print(f"Generated {len(events)} events")
    print(f"Markdown: {md_path}")
    print(f"JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
