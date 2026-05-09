from __future__ import annotations


def get_default_params() -> dict:
    # Strategy-local defaults; runtime env can still override generic params.
    return {
        "lot_quantity": 1,
        "lot_size": 1,
        "capital_model": "non_compounding",
    }
