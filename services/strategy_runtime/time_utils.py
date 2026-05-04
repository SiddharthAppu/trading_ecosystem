from __future__ import annotations

from datetime import datetime, timedelta, timezone


IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(IST)


def to_ist(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(IST)


def isoformat_ist(value: datetime | None) -> str | None:
    if value is None:
        return None
    return to_ist(value).isoformat()


def parse_iso_to_ist(value: str | None) -> str:
    if not value:
        return now_ist().isoformat()
    normalized = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return now_ist().isoformat()
    return to_ist(dt).isoformat()
