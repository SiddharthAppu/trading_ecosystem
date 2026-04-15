from __future__ import annotations

import os
from dataclasses import dataclass, field


def _parse_csv(raw_value: str, default: list[str]) -> list[str]:
    if not raw_value:
        return default
    return [item.strip() for item in raw_value.split(",") if item.strip()]


@dataclass(slots=True)
class RuntimeSettings:
    feed_source: str = "broker"
    provider: str = "upstox"
    symbol: str = "NSE_INDEX|Nifty 50"
    timeframe: str = "1m"
    polling_interval_seconds: int = 20
    lookback_bars: int = 120
    strategy_name: str = "ema_cross"
    strategy_class_path: str = ""
    quantity: int = 1
    initial_capital: float = 100000.0
    max_position_quantity: int = 1
    max_notional_per_trade: float = 250000.0
    stop_loss_pct: float = 0.01
    trailing_stop_pct: float = 0.015
    indicators: list[str] = field(default_factory=lambda: ["ema_20", "sma_20", "rsi_14", "macd"])
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

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        return cls(
            feed_source=os.getenv("STRATEGY_RUNTIME_FEED_SOURCE", "broker").strip().lower(),
            provider=os.getenv("STRATEGY_RUNTIME_PROVIDER", "upstox").strip().lower(),
            symbol=os.getenv("STRATEGY_RUNTIME_SYMBOL", "NSE_INDEX|Nifty 50").strip(),
            timeframe=os.getenv("STRATEGY_RUNTIME_TIMEFRAME", "1m").strip().lower(),
            polling_interval_seconds=int(os.getenv("STRATEGY_RUNTIME_POLL_SECONDS", "20")),
            lookback_bars=int(os.getenv("STRATEGY_RUNTIME_LOOKBACK_BARS", "120")),
            strategy_name=os.getenv("STRATEGY_RUNTIME_STRATEGY", "ema_cross").strip().lower(),
            strategy_class_path=os.getenv("STRATEGY_RUNTIME_STRATEGY_CLASS", "").strip(),
            quantity=int(os.getenv("STRATEGY_RUNTIME_QUANTITY", "1")),
            initial_capital=float(os.getenv("STRATEGY_RUNTIME_INITIAL_CAPITAL", "100000")),
            max_position_quantity=int(os.getenv("STRATEGY_RUNTIME_MAX_POSITION_QTY", "1")),
            max_notional_per_trade=float(os.getenv("STRATEGY_RUNTIME_MAX_NOTIONAL", "250000")),
            stop_loss_pct=float(os.getenv("STRATEGY_RUNTIME_STOP_LOSS_PCT", "0.01")),
            trailing_stop_pct=float(os.getenv("STRATEGY_RUNTIME_TRAILING_STOP_PCT", "0.015")),
            indicators=_parse_csv(
                os.getenv("STRATEGY_RUNTIME_INDICATORS", "ema_20,sma_20,rsi_14,macd"),
                ["ema_20", "sma_20", "rsi_14", "macd"],
            ),
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
        )