from __future__ import annotations

import asyncio
import argparse
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from services.strategy_runtime.bootstrap import ensure_repo_paths

ensure_repo_paths()

from services.strategy_runtime.config import RuntimeSettings
from services.strategy_runtime.notifier import configure_file_logging
from services.strategy_runtime.runtime import create_runtime
from services.strategy_runtime.time_utils import IST


class IstFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None) -> str:
        dt = datetime.fromtimestamp(record.created, timezone.utc).astimezone(IST)
        return dt.isoformat(timespec="milliseconds")


def _slugify_run_part(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", (value or "").strip()).strip("-")
    return (cleaned or fallback)[:48]


def _assign_run_scoped_log_file(settings: RuntimeSettings) -> None:
    log_path = Path(settings.log_file)
    run_id = datetime.now(IST).strftime("%Y%m%d_%H%M%S_%f")[:-3]
    run_suffix = "_".join(
        [
            _slugify_run_part(settings.strategy_name, "strategy"),
            _slugify_run_part(settings.provider, "provider"),
            _slugify_run_part(settings.symbol, "symbol"),
        ]
    )
    run_dir = log_path.parent / "runs" / f"{run_id}_{run_suffix}"
    settings.log_file = (run_dir / log_path.name).as_posix()


def configure_logging(settings: RuntimeSettings) -> None:
    _assign_run_scoped_log_file(settings)
    configure_file_logging(settings)
    formatter = IstFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(settings.log_file, encoding="utf-8"),
    ]
    for handler in handlers:
        handler.setFormatter(formatter)
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        handlers=handlers,
        force=True,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run strategy runtime")
    parser.add_argument("--config", required=True, help="Path to strategy runtime JSON config")
    args = parser.parse_args()

    settings = RuntimeSettings.from_json(args.config)
    configure_logging(settings)
    runtime = create_runtime(settings)
    await runtime.run()


if __name__ == "__main__":
    asyncio.run(main())