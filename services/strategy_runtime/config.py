from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


class RuntimeConfigError(ValueError):
    """Raised when required runtime configuration is missing or invalid."""


ALLOWED_FEED_SOURCES = {"broker", "replay_ws", "collector_sse"}


def _normalize_feed_source(raw_value: str | None) -> str:
    value = (raw_value or "broker").strip().lower()
    if value in ALLOWED_FEED_SOURCES:
        return value
    raise RuntimeConfigError(
        f"Invalid STRATEGY_RUNTIME_FEED_SOURCE: {raw_value}. "
        f"Expected one of: {', '.join(sorted(ALLOWED_FEED_SOURCES))}"
    )


def _load_global_env() -> None:
    """Load central config/.env so shared secrets do not need per-strategy duplication."""
    config_dir = os.getenv("TRADING_CONFIG_DIR", os.path.join(os.getcwd(), "config"))
    env_file = os.path.join(config_dir, ".env")
    if os.path.exists(env_file):
        load_dotenv(env_file, override=False)


_load_global_env()


def _parse_csv(raw_value: object, default: list[str]) -> list[str]:
    if raw_value is None:
        return default
    if isinstance(raw_value, list):
        values = [str(item).strip() for item in raw_value if str(item).strip()]
        return values or default
    if isinstance(raw_value, str):
        value = raw_value.strip()
        if not value:
            return default
        return [item.strip() for item in value.split(",") if item.strip()]
    return default


def _parse_indicator_input_mode(raw_value: str | None) -> str:
    value = (raw_value or "bars_1m").strip().lower()
    if value in {"bars_1m", "ticks"}:
        return value
    return "bars_1m"


def _parse_positive_int(raw_value: object, name: str) -> int:
    try:
        value = int(raw_value)  # type: ignore[arg-type]
    except ValueError as exc:
        raise RuntimeConfigError(f"Invalid integer for {name}: {raw_value}") from exc
    except TypeError as exc:
        raise RuntimeConfigError(f"Invalid integer for {name}: {raw_value}") from exc
    if value <= 0:
        raise RuntimeConfigError(f"{name} must be greater than 0")
    return value


def _parse_int(raw_value: object, default: int, name: str) -> int:
    if raw_value is None:
        return default
    if isinstance(raw_value, str) and not raw_value.strip():
        return default
    try:
        return int(raw_value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise RuntimeConfigError(f"Invalid integer for {name}: {raw_value}") from exc


def _parse_float(raw_value: object, default: float, name: str) -> float:
    if raw_value is None:
        return default
    if isinstance(raw_value, str) and not raw_value.strip():
        return default
    try:
        return float(raw_value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise RuntimeConfigError(f"Invalid number for {name}: {raw_value}") from exc


def _parse_bool(raw_value: object, default: bool) -> bool:
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, (int, float)):
        return bool(raw_value)
    value = str(raw_value).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_source_data_kind(raw_value: str) -> str:
    value = raw_value.strip().lower()
    if value in {"bars", "ticks"}:
        return value
    raise RuntimeConfigError(
        f"Invalid source data kind: {raw_value}. Expected one of: bars, ticks"
    )


@dataclass(slots=True)
class RuntimeSettings:
    feed_source: str = "broker"
    provider: str = "upstox"
    trading_provider: str = "" # Defaults to 'provider' if empty
    symbol: str = "NSE_INDEX|Nifty 50"
    timeframe: str = "1m"
    polling_interval_seconds: int = 20
    lookback_bars: int = 120
    strategy_name: str = "ema_cross"
    strategy_class_path: str = ""
    lot_quantity: int = 1
    lot_size: int = 1
    initial_capital: float = 100000.0
    max_position_lots: int = 1
    capital_model: str = "non_compounding"
    max_notional_per_trade: float = 250000.0
    stop_loss_pct: float = 0.01
    trailing_stop_pct: float = 0.015
    indicators: list[str] = field(default_factory=lambda: ["ema_20", "sma_20", "rsi_14", "macd"])
    indicator_input_mode: str = "bars_1m"
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    log_level: str = "INFO"
    log_file: str = "logs/strategy_runtime/runtime.log"
    autostart: bool = True
    replay_ws_url: str = "ws://localhost:8765"
    replay_data_type: str = "ohlcv_1m"
    replay_speed: float = 5.0
    replay_start_time: str = ""
    replay_end_time: str = ""
    collector_base_url: str = "http://localhost:8080"
    collector_events_path: str = "/recorder/events"
    collector_provider: str = ""
    collector_connect_timeout_seconds: int = 10
    collector_reconnect_seconds: int = 3
    collector_stale_timeout_seconds: int = 45
    collector_fallback_policy: str = "collector_only"
    source_table: str = ""
    source_data_kind: str = ""
    options_source_table: str = ""
    db_chunking_trading_days: int = 0
    max_rows_per_chunk: int = 0

    def validate_source_config(self) -> None:
        if self.feed_source not in ALLOWED_FEED_SOURCES:
            raise RuntimeConfigError(
                f"Invalid feed_source: {self.feed_source}. Expected one of: {', '.join(sorted(ALLOWED_FEED_SOURCES))}"
            )

        if self.feed_source == "collector_sse":
            if not self.collector_base_url:
                raise RuntimeConfigError("Missing required config: STRATEGY_RUNTIME_COLLECTOR_BASE_URL")
            if not self.collector_events_path:
                raise RuntimeConfigError("Missing required config: STRATEGY_RUNTIME_COLLECTOR_EVENTS_PATH")
            if self.collector_connect_timeout_seconds <= 0:
                raise RuntimeConfigError("STRATEGY_RUNTIME_COLLECTOR_CONNECT_TIMEOUT_SECONDS must be greater than 0")
            if self.collector_reconnect_seconds <= 0:
                raise RuntimeConfigError("STRATEGY_RUNTIME_COLLECTOR_RECONNECT_SECONDS must be greater than 0")
            if self.collector_stale_timeout_seconds <= 0:
                raise RuntimeConfigError("STRATEGY_RUNTIME_COLLECTOR_STALE_TIMEOUT_SECONDS must be greater than 0")
            if self.collector_fallback_policy not in {"collector_only", "fallback_to_broker"}:
                raise RuntimeConfigError(
                    "Invalid STRATEGY_RUNTIME_COLLECTOR_FALLBACK_POLICY. "
                    "Expected one of: collector_only, fallback_to_broker"
                )

        if self.feed_source != "replay_ws":
            return
        if not self.source_table:
            raise RuntimeConfigError("Missing required config: STRATEGY_RUNTIME_SOURCE_TABLE")
        if not self.source_data_kind:
            raise RuntimeConfigError("Missing required config: STRATEGY_RUNTIME_SOURCE_DATA_KIND")
        if self.source_data_kind not in {"bars", "ticks"}:
            raise RuntimeConfigError(
                f"Invalid STRATEGY_RUNTIME_SOURCE_DATA_KIND: {self.source_data_kind}. Expected bars or ticks"
            )
        if self.db_chunking_trading_days <= 0:
            raise RuntimeConfigError("STRATEGY_RUNTIME_DB_CHUNKING_TRADING_DAYS must be greater than 0")
        if self.max_rows_per_chunk <= 0:
            raise RuntimeConfigError("STRATEGY_RUNTIME_MAX_ROWS_PER_CHUNK must be greater than 0")
        if not self.options_source_table:
            raise RuntimeConfigError("Missing required config: STRATEGY_RUNTIME_OPTIONS_SOURCE_TABLE")

    @classmethod
    def from_json(cls, path: str) -> "RuntimeSettings":
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
        except FileNotFoundError as exc:
            raise RuntimeConfigError(f"Strategy runtime config not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeConfigError(f"Invalid JSON in runtime config {path}: {exc}") from exc

        if not isinstance(payload, dict):
            raise RuntimeConfigError("Runtime config root must be a JSON object")

        runtime = payload.get("runtime", {})
        strategy = payload.get("strategy", {})
        risk = payload.get("risk", {})
        replay = payload.get("replay", {})
        collector = payload.get("collector", {})
        telegram = payload.get("telegram", {})
        strategy_params = payload.get("strategy_params", {})

        for section_name, section in (
            ("runtime", runtime),
            ("strategy", strategy),
            ("risk", risk),
            ("replay", replay),
            ("collector", collector),
            ("telegram", telegram),
            ("strategy_params", strategy_params),
        ):
            if not isinstance(section, dict):
                raise RuntimeConfigError(f"Section '{section_name}' must be a JSON object")

        for key, value in strategy_params.items():
            os.environ[str(key)] = "" if value is None else str(value)

        capital_model = str(risk.get("capital_model", "non_compounding")).strip().lower()
        if capital_model not in {"non_compounding", "compounding"}:
            capital_model = "non_compounding"

        settings = cls(
            feed_source=_normalize_feed_source(str(runtime.get("feed_source", "broker"))),
            provider=str(runtime.get("provider", "upstox")).strip().lower(),
            trading_provider=str(runtime.get("trading_provider", "")).strip().lower(),
            symbol=str(runtime.get("symbol", "NSE_INDEX|Nifty 50")).strip(),
            timeframe=str(runtime.get("timeframe", "1m")).strip().lower(),
            polling_interval_seconds=_parse_int(
                runtime.get("poll_seconds"),
                20,
                "runtime.poll_seconds",
            ),
            lookback_bars=_parse_int(runtime.get("lookback_bars"), 120, "runtime.lookback_bars"),
            strategy_name=str(strategy.get("name", "ema_cross")).strip().lower(),
            strategy_class_path=str(strategy.get("class_path", "")).strip(),
            lot_quantity=_parse_int(risk.get("lot_quantity"), 1, "risk.lot_quantity"),
            lot_size=_parse_int(risk.get("lot_size"), 1, "risk.lot_size"),
            initial_capital=_parse_float(risk.get("initial_capital"), 100000.0, "risk.initial_capital"),
            max_position_lots=_parse_int(risk.get("max_position_lots"), 1, "risk.max_position_lots"),
            capital_model=capital_model,
            max_notional_per_trade=_parse_float(
                risk.get("max_notional_per_trade"),
                250000.0,
                "risk.max_notional_per_trade",
            ),
            stop_loss_pct=_parse_float(risk.get("stop_loss_pct"), 0.01, "risk.stop_loss_pct"),
            trailing_stop_pct=_parse_float(
                risk.get("trailing_stop_pct"),
                0.015,
                "risk.trailing_stop_pct",
            ),
            indicators=_parse_csv(strategy.get("indicators"), ["ema_20", "sma_20", "rsi_14", "macd"]),
            indicator_input_mode=_parse_indicator_input_mode(
                str(strategy.get("indicator_input_mode", "bars_1m"))
            ),
            telegram_enabled=_parse_bool(telegram.get("enabled"), False),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            log_level=str(runtime.get("log_level", "INFO")).strip().upper(),
            log_file=str(runtime.get("log_file", "logs/strategy_runtime/runtime.log")).strip(),
            autostart=_parse_bool(runtime.get("autostart"), True),
            replay_ws_url=str(replay.get("ws_url", "ws://localhost:8765")).strip(),
            replay_data_type=str(replay.get("data_type", "ohlcv_1m")).strip(),
            replay_speed=_parse_float(replay.get("speed"), 5.0, "replay.speed"),
            replay_start_time=str(replay.get("start_time", "")).strip(),
            replay_end_time=str(replay.get("end_time", "")).strip(),
            collector_base_url=str(collector.get("base_url", "http://localhost:8080")).strip(),
            collector_events_path=str(collector.get("events_path", "/recorder/events")).strip(),
            collector_provider=str(collector.get("provider", "")).strip().lower(),
            collector_connect_timeout_seconds=_parse_int(
                collector.get("connect_timeout_seconds"),
                10,
                "collector.connect_timeout_seconds",
            ),
            collector_reconnect_seconds=_parse_int(
                collector.get("reconnect_seconds"),
                3,
                "collector.reconnect_seconds",
            ),
            collector_stale_timeout_seconds=_parse_int(
                collector.get("stale_timeout_seconds"),
                45,
                "collector.stale_timeout_seconds",
            ),
            collector_fallback_policy=str(collector.get("fallback_policy", "collector_only")).strip().lower(),
            source_table=str(replay.get("source_table", "")).strip(),
            source_data_kind=str(replay.get("source_data_kind", "")).strip().lower(),
            options_source_table=str(replay.get("options_source_table", "")).strip(),
            db_chunking_trading_days=(
                _parse_positive_int(replay.get("db_chunking_trading_days"), "replay.db_chunking_trading_days")
                if str(runtime.get("feed_source", "broker")).strip().lower() == "replay_ws"
                else _parse_int(replay.get("db_chunking_trading_days"), 1, "replay.db_chunking_trading_days")
            ),
            max_rows_per_chunk=(
                _parse_positive_int(replay.get("max_rows_per_chunk"), "replay.max_rows_per_chunk")
                if str(runtime.get("feed_source", "broker")).strip().lower() == "replay_ws"
                else _parse_int(replay.get("max_rows_per_chunk"), 1, "replay.max_rows_per_chunk")
            ),
        )
        settings.source_data_kind = (
            _normalize_source_data_kind(settings.source_data_kind)
            if settings.source_data_kind
            else settings.source_data_kind
        )
        settings.validate_source_config()
        return settings