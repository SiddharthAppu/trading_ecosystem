from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from urllib import parse, request

from services.strategy_runtime.config import RuntimeSettings


logger = logging.getLogger("strategy_runtime.notifier")


@dataclass(slots=True)
class NotificationMessage:
    title: str
    body: str
    level: str = "info"


class BaseNotifier:
    async def send(self, message: NotificationMessage) -> None:
        raise NotImplementedError


class LogNotifier(BaseNotifier):
    async def send(self, message: NotificationMessage) -> None:
        log_method = getattr(logger, message.level.lower(), logger.info)
        log_method("%s: %s", message.title, message.body)


class TelegramNotifier(BaseNotifier):
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send(self, message: NotificationMessage) -> None:
        text = f"{message.title}\n{message.body}"
        payload = parse.urlencode({"chat_id": self.chat_id, "text": text}).encode("utf-8")
        endpoint = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        req = request.Request(endpoint, data=payload, method="POST")
        try:
            with request.urlopen(req, timeout=10) as response:
                response.read()
        except Exception as exc:
            logger.warning("Telegram notification failed: %s", exc)


class CompositeNotifier(BaseNotifier):
    def __init__(self, notifiers: list[BaseNotifier]):
        self.notifiers = notifiers

    @classmethod
    def from_settings(cls, settings: RuntimeSettings) -> "CompositeNotifier":
        notifiers: list[BaseNotifier] = [LogNotifier()]
        if settings.telegram_bot_token and settings.telegram_chat_id:
            notifiers.append(TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id))
        return cls(notifiers)

    async def send(self, message: NotificationMessage) -> None:
        for notifier in self.notifiers:
            await notifier.send(message)


def configure_file_logging(settings: RuntimeSettings) -> None:
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)