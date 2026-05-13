from __future__ import annotations

import os


def get_default_params() -> dict:
    return {
        # Lot-based position sizing
        "lot_quantity": 1,
        "lot_size": 1,
        "capital_model": "non_compounding",
        # Upstox underlying symbol for NIFTY50 index
        "underlying_symbol": os.getenv("NIFTY_UNDERLYING_SYMBOL", "NSE_INDEX|Nifty 50"),
        # Option expiry to trade (ISO date "YYYY-MM-DD"). Set "" to auto-pick nearest weekly.
        "option_expiry": os.getenv("NIFTY_OPTION_EXPIRY", ""),
        # Number of ATM strikes in each direction to scan for the target premium
        "strike_scan_count": int(os.getenv("NIFTY_STRIKE_SCAN_COUNT", "10")),
        # Target option premium for entry selection (Rs)
        "target_premium": float(os.getenv("NIFTY_TARGET_PREMIUM", "200.0")),
        # Tolerance around target_premium: any strike within +-tolerance is eligible
        "premium_tolerance": float(os.getenv("NIFTY_PREMIUM_TOLERANCE", "50.0")),
        # Risk per trade as fraction of entry premium (e.g. 0.5 -> risk = 50% of entry)
        "stop_loss_premium_pct": float(os.getenv("NIFTY_STOP_LOSS_PREMIUM_PCT", "0.50")),
        # Force-close open positions at/after the configured IST time.
        "force_exit_1500_enabled": os.getenv("NIFTY_FORCE_EXIT_1500_ENABLED", "false"),
        "force_exit_time_ist": os.getenv("NIFTY_FORCE_EXIT_TIME_IST", "15:00"),
        # Debug instrumentation for force-exit evaluation.
        "force_exit_debug_enabled": os.getenv("NIFTY_FORCE_EXIT_DEBUG_ENABLED", "false"),
        "force_exit_debug_to_journal": os.getenv("NIFTY_FORCE_EXIT_DEBUG_TO_JOURNAL", "false"),
        # Provider to call for live option quotes (must match STRATEGY_RUNTIME_PROVIDER)
        "provider": os.getenv("STRATEGY_RUNTIME_PROVIDER", "upstox"),
        # Indicator periods
        # The LOGIC of each signal (EMA > SMA, MACD line > 0) is fixed in strategy.py.
        # These numbers tune HOW SENSITIVE those indicators are. They belong in env,
        # not in code, so they can be changed without touching strategy logic.
        "ema_period": int(os.getenv("NIFTY_EMA_PERIOD", "20")),
        "sma_period": int(os.getenv("NIFTY_SMA_PERIOD", "20")),
        "macd_fast": int(os.getenv("NIFTY_MACD_FAST", "12")),
        "macd_slow": int(os.getenv("NIFTY_MACD_SLOW", "26")),
        "macd_signal": int(os.getenv("NIFTY_MACD_SIGNAL", "9")),
    }
