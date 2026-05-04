from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

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


def configure_logging(settings: RuntimeSettings) -> None:
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
    settings = RuntimeSettings.from_env()
    configure_logging(settings)
    runtime = create_runtime(settings)
    await runtime.run()


if __name__ == "__main__":
    asyncio.run(main())