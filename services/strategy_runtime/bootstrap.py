from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_paths() -> None:
    root_dir = Path(__file__).resolve().parents[2]
    trading_core_dir = root_dir / "packages" / "trading_core"

    for candidate in (root_dir, trading_core_dir):
        candidate_text = str(candidate)
        if candidate_text not in sys.path:
            sys.path.insert(0, candidate_text)