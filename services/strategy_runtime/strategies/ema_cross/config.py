from __future__ import annotations


def get_default_params() -> dict:
    # Strategy-local defaults; runtime env can still override generic params.
    return {
        "quantity": 1,
    }
