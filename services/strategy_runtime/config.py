from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


class RuntimeConfigError(ValueError):
    """Raised when required runtime configuration is missing or invalid."""


def _load_global_env() -> None:
    """Load central config/.env so shared secrets do not need per-strategy duplication."""
    config_dir = os.getenv("TRADING_CONFIG_DIR", os.path.join(os.getcwd(), "config"))
    env_file = os.path.join(config_dir, ".env")
    if os.path.exists(env_file):
        load_dotenv(env_file, override=False)


_load_global_env()


def _parse_csv(raw_value: str, default: list[str]) -> list[str]:
    if not raw_value:
        return default
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _parse_indicator_input_mode(raw_value: str | None) -> str:
    value = (raw_value or "bars_1m").strip().lower()
    if value in {"bars_1m", "ticks"}:
        return value
    return "bars_1m"


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeConfigError(f"Missing required config: {name}")
    return value


def _parse_positive_int(name: str) -> int:
    raw_value = _require_env(name)
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeConfigError(f"Invalid integer for {name}: {raw_value}") from exc
    if value <= 0:
        raise RuntimeConfigError(f"{name} must be greater than 0")
    return value


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
    source_table: str = ""
    source_data_kind: str = ""
    options_source_table: str = ""
    db_chunking_trading_days: int = 0
    max_rows_per_chunk: int = 0

    def validate_source_config(self) -> None:
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
    def from_env(cls) -> "RuntimeSettings":
        capital_model = os.getenv("STRATEGY_RUNTIME_CAPITAL_MODEL", "non_compounding").strip().lower()
        if capital_model not in {"non_compounding", "compounding"}:
            capital_model = "non_compounding"

        settings = cls(
            feed_source=os.getenv("STRATEGY_RUNTIME_FEED_SOURCE", "broker").strip().lower(),
            provider=os.getenv("STRATEGY_RUNTIME_PROVIDER", "upstox").strip().lower(),
            trading_provider=os.getenv("STRATEGY_RUNTIME_TRADING_PROVIDER", "").strip().lower(),
            symbol=os.getenv("STRATEGY_RUNTIME_SYMBOL", "NSE_INDEX|Nifty 50").strip(),
            timeframe=os.getenv("STRATEGY_RUNTIME_TIMEFRAME", "1m").strip().lower(),
            polling_interval_seconds=int(os.getenv("STRATEGY_RUNTIME_POLL_SECONDS", "20")),
            lookback_bars=int(os.getenv("STRATEGY_RUNTIME_LOOKBACK_BARS", "120")),
            strategy_name=os.getenv("STRATEGY_RUNTIME_STRATEGY", "ema_cross").strip().lower(),
            strategy_class_path=os.getenv("STRATEGY_RUNTIME_STRATEGY_CLASS", "").strip(),
            lot_quantity=int(os.getenv("STRATEGY_RUNTIME_LOT_QUANTITY", "1")),
            lot_size=int(os.getenv("STRATEGY_RUNTIME_LOT_SIZE", "1")),
            initial_capital=float(os.getenv("STRATEGY_RUNTIME_INITIAL_CAPITAL", "100000")),
            max_position_lots=int(os.getenv("STRATEGY_RUNTIME_MAX_POSITION_LOTS", "1")),
            capital_model=capital_model,
            max_notional_per_trade=float(os.getenv("STRATEGY_RUNTIME_MAX_NOTIONAL", "250000")),
            stop_loss_pct=float(os.getenv("STRATEGY_RUNTIME_STOP_LOSS_PCT", "0.01")),
            trailing_stop_pct=float(os.getenv("STRATEGY_RUNTIME_TRAILING_STOP_PCT", "0.015")),
            indicators=_parse_csv(
                os.getenv("STRATEGY_RUNTIME_INDICATORS", "ema_20,sma_20,rsi_14,macd"),
                ["ema_20", "sma_20", "rsi_14", "macd"],
            ),
            indicator_input_mode=_parse_indicator_input_mode(
                os.getenv("STRATEGY_RUNTIME_INDICATOR_INPUT_MODE", "bars_1m")
            ),
            telegram_enabled=os.getenv("TELEGRAM_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"},
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            log_level=os.getenv("STRATEGY_RUNTIME_LOG_LEVEL", "INFO").strip().upper(),
            log_file=os.getenv("STRATEGY_RUNTIME_LOG_FILE", "logs/strategy_runtime/runtime.log").strip(),
            autostart=os.getenv("STRATEGY_RUNTIME_AUTOSTART", "true").strip().lower() in {"1", "true", "yes", "on"},
            replay_ws_url=os.getenv("STRATEGY_RUNTIME_REPLAY_WS_URL", "ws://localhost:8765").strip(),
            replay_data_type=os.getenv("STRATEGY_RUNTIME_REPLAY_DATA_TYPE", "ohlcv_1m").strip(),
            replay_speed=float(os.getenv("STRATEGY_RUNTIME_REPLAY_SPEED", "5.0")),
            replay_start_time=os.getenv("STRATEGY_RUNTIME_REPLAY_START_TIME", "").strip(),
            replay_end_time=os.getenv("STRATEGY_RUNTIME_REPLAY_END_TIME", "").strip(),
            source_table=os.getenv("STRATEGY_RUNTIME_SOURCE_TABLE", "").strip(),
            source_data_kind=os.getenv("STRATEGY_RUNTIME_SOURCE_DATA_KIND", "").strip().lower(),
            options_source_table=os.getenv("STRATEGY_RUNTIME_OPTIONS_SOURCE_TABLE", "").strip(),
            db_chunking_trading_days=(
                _parse_positive_int("STRATEGY_RUNTIME_DB_CHUNKING_TRADING_DAYS")
                if os.getenv("STRATEGY_RUNTIME_FEED_SOURCE", "broker").strip().lower() == "replay_ws"
                else int(os.getenv("STRATEGY_RUNTIME_DB_CHUNKING_TRADING_DAYS", "1") or "1")
            ),
            max_rows_per_chunk=(
                _parse_positive_int("STRATEGY_RUNTIME_MAX_ROWS_PER_CHUNK")
                if os.getenv("STRATEGY_RUNTIME_FEED_SOURCE", "broker").strip().lower() == "replay_ws"
                else int(os.getenv("STRATEGY_RUNTIME_MAX_ROWS_PER_CHUNK", "1") or "1")
            ),
        )
        settings.source_data_kind = (
            _normalize_source_data_kind(settings.source_data_kind)
            if settings.source_data_kind
            else settings.source_data_kind
        )
        settings.validate_source_config()
        return settings