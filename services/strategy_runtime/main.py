from __future__ import annotations

import asyncio
import logging

from services.strategy_runtime.bootstrap import ensure_repo_paths

ensure_repo_paths()

from services.strategy_runtime.config import RuntimeSettings
from services.strategy_runtime.notifier import configure_file_logging
from services.strategy_runtime.runtime import create_runtime


def configure_logging(settings: RuntimeSettings) -> None:
    configure_file_logging(settings)
    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(settings.log_file, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
    )


async def main() -> None:
    settings = RuntimeSettings.from_env()
    configure_logging(settings)
    runtime = create_runtime(settings)
    await runtime.run()


if __name__ == "__main__":
    asyncio.run(main())