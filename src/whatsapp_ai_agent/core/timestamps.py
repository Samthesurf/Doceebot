from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def local_date_and_time(value: datetime, timezone_name: str) -> tuple[date, time]:
    local_value = ensure_aware_utc(value).astimezone(ZoneInfo(timezone_name))
    return local_value.date(), local_value.time().replace(microsecond=0)
