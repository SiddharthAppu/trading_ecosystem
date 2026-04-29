from __future__ import annotations

import os


def get_default_params() -> dict:
    return {
        # Quantity per trade (1 lot)
        "quantity": 1,
        # Upstox underlying symbol for NIFTY50 index
        "underlying_symbol": os.getenv("NIFTY_UNDERLYING_SYMBOL", "NSE_INDEX|Nifty 50"),
        # Option expiry to trade (ISO date "YYYY-MM-DD"). Set "" to auto-pick nearest weekly.
        "option_expiry": os.getenv("NIFTY_OPTION_EXPIRY", ""),
        # Number of ATM strikes in each direction to scan for the target premium
        "strike_scan_count": int(os.getenv("NIFTY_STRIKE_SCAN_COUNT", "10")),
        # Target option premium for entry selection (Rs)
        "target_premium": float(os.getenv("NIFTY_TARGET_PREMIUM", "200.0")),
        # Tolerance around target_premium: any strike within ±tolerance is eligible
        "premium_tolerance": float(os.getenv("NIFTY_PREMIUM_TOLERANCE", "50.0")),
        # Risk per trade as fraction of entry premium (e.g. 0.5 → risk = 50% of entry)
        "stop_loss_premium_pct": float(os.getenv("NIFTY_STOP_LOSS_PREMIUM_PCT", "0.50")),
        # Provider to call for live option quotes (must match STRATEGY_RUNTIME_PROVIDER)
        "provider": os.getenv("STRATEGY_RUNTIME_PROVIDER", "upstox"),
    }
