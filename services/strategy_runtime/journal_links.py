from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger("strategy_runtime.journal_links")

_DEFAULT_TV_SYMBOL_MAP_PATH = "config/strategies/tradingview_symbol_map.json"
_MONTHS = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}


def _load_symbol_map() -> dict[str, str]:
    path = Path(os.getenv("STRATEGY_RUNTIME_TV_SYMBOL_MAP_FILE", _DEFAULT_TV_SYMBOL_MAP_PATH))
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load TradingView symbol map from %s: %s", path, exc)
        return {}

    if not isinstance(data, dict):
        logger.warning("TradingView symbol map at %s must be an object", path)
        return {}

    return {str(k).strip().upper(): str(v).strip() for k, v in data.items() if str(k).strip()}


def timeframe_to_tradingview_interval(timeframe: str) -> str:
    normalized = (timeframe or "").strip().lower()
    mapping = {
        "1m": "1",
        "3m": "3",
        "5m": "5",
        "10m": "10",
        "15m": "15",
        "30m": "30",
        "45m": "45",
        "60m": "60",
        "1h": "60",
        "2h": "120",
        "4h": "240",
        "1d": "D",
        "1w": "W",
    }
    return mapping.get(normalized, "5")


def _iso_utc(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    normalized = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.now(timezone.utc).isoformat()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _clean_symbol(raw_symbol: str) -> str:
    symbol = (raw_symbol or "").strip()
    if "|" in symbol:
        symbol = symbol.split("|", 1)[1].strip()
    symbol = symbol.replace(" ", "")
    return symbol


def _build_option_symbol(compact: str) -> str | None:
    compact_upper = compact.upper()

    direct = re.fullmatch(r"(NIFTY|BANKNIFTY|FINNIFTY)\d{2}[A-Z]{3}\d{4,6}(CE|PE)", compact_upper)
    if direct:
        return f"NFO:{compact_upper}"

    verbose = re.fullmatch(
        r"(NIFTY|BANKNIFTY|FINNIFTY)(\d{1,2})([A-Z]{3})(\d{2,4})(\d{4,6})(CE|PE)",
        compact_upper,
    )
    if not verbose:
        return None

    root, day_raw, month_raw, year_raw, strike, right = verbose.groups()
    month_num = _MONTHS.get(month_raw)
    if month_num is None:
        return None

    year = year_raw[-2:]
    day = day_raw.zfill(2)
    return f"NFO:{root}{year}{month_num}{day}{strike}{right}"


def normalize_symbol_for_tradingview(raw_symbol: str, symbol_map: dict[str, str] | None = None) -> str | None:
    cleaned = _clean_symbol(raw_symbol)
    if not cleaned:
        return None

    upper = cleaned.upper()
    mapping = symbol_map or {}

    if upper in mapping:
        return mapping[upper]

    if upper in {"NIFTY", "NIFTY50", "NIFTY 50", "NIFTYINDEX"}:
        return "NSE:NIFTY"
    if upper in {"BANKNIFTY", "NIFTYBANK"}:
        return "NSE:BANKNIFTY"
    if upper in {"FINNIFTY", "NIFTYFINSERVICE"}:
        return "NSE:FINNIFTY"

    option_symbol = _build_option_symbol(upper)
    if option_symbol:
        return option_symbol

    # Final fallback for equity/index-like symbols.
    return f"NSE:{upper}"


def _extract_side(data: dict[str, Any]) -> str:
    side = str(data.get("side", "")).upper()
    if side in {"BUY", "SELL"}:
        return side
    action = str(data.get("action", "")).upper()
    if action in {"BUY", "SELL"}:
        return action
    return ""


def _event_key(entry: dict[str, Any], line_no: int) -> str:
    event_type = str(entry.get("event", "")).upper() or "UNKNOWN"
    symbol = str(entry.get("symbol", "")).upper() or "UNKNOWN"
    ts = str(entry.get("event_ts") or entry.get("ts") or "")
    return f"{event_type}:{symbol}:{ts}:{line_no}"


def build_event_view(
    entry: dict[str, Any],
    line_no: int,
    chart_base_path: str = "/chart",
    symbol_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    data = entry.get("data") or {}
    if not isinstance(data, dict):
        data = {}

    event_ts = _iso_utc(str(entry.get("event_ts") or data.get("filled_at") or entry.get("ts") or ""))
    timeframe = str(entry.get("timeframe") or "5m")
    symbol_raw = str(entry.get("symbol") or "")
    tv_symbol = normalize_symbol_for_tradingview(symbol_raw, symbol_map=symbol_map)
    tv_interval = timeframe_to_tradingview_interval(timeframe)

    params = {
        "symbol": symbol_raw,
        "timeframe": timeframe,
        "eventTs": event_ts,
        "eventType": str(entry.get("event") or ""),
    }

    side = _extract_side(data)
    if side:
        params["side"] = side

    if tv_symbol:
        params["tvSymbol"] = tv_symbol

    tradingview_url = None
    if tv_symbol:
        tradingview_url = f"https://www.tradingview.com/chart/?{urlencode({'symbol': tv_symbol, 'interval': tv_interval})}"
        params["tvUrl"] = tradingview_url

    local_chart_url = f"{chart_base_path}?{urlencode(params)}"

    return {
        "id": _event_key(entry, line_no),
        "line_no": line_no,
        "ts": str(entry.get("ts") or ""),
        "event_ts": event_ts,
        "event": str(entry.get("event") or ""),
        "strategy": str(entry.get("strategy") or ""),
        "timeframe": timeframe,
        "symbol": symbol_raw,
        "basket_id": str(entry.get("basket_id") or ""),
        "side": side,
        "data": data,
        "links": {
            "local_chart_url": local_chart_url,
            "tradingview_url": tradingview_url,
            "tradingview_symbol": tv_symbol,
            "tradingview_interval": tv_interval,
        },
    }


def read_journal_events(
    journal_path: str,
    *,
    limit: int = 200,
    symbol: str | None = None,
    event: str | None = None,
) -> list[dict[str, Any]]:
    path = Path(journal_path)
    if not path.exists():
        return []

    symbol_filter = (symbol or "").strip().upper()
    event_filter = (event or "").strip().upper()
    symbol_map = _load_symbol_map()

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            raw_symbol = str(entry.get("symbol", "")).upper()
            raw_event = str(entry.get("event", "")).upper()

            if symbol_filter and symbol_filter not in raw_symbol:
                continue
            if event_filter and event_filter != raw_event:
                continue

            rows.append(build_event_view(entry, line_no, symbol_map=symbol_map))

    if limit <= 0:
        return []
    return rows[-limit:]
