from datetime import datetime, time
from zoneinfo import ZoneInfo

__all__ = (
    "SKY_TIMEZONE",
    "utcnow",
    "sky_time_now",
    "sky_datetime",
    "sky_time",
)

SKY_TIMEZONE = ZoneInfo("America/Los_Angeles")


def utcnow():
    return datetime.now(ZoneInfo("UTC"))


def sky_time_now() -> datetime:
    return datetime.now(SKY_TIMEZONE)


def sky_datetime(
    year, month, day, hour=0, minute=0, second=0, microsecond=0
) -> datetime:
    return datetime(
        year, month, day, hour, minute, second, microsecond, tzinfo=SKY_TIMEZONE
    )


def sky_time(hour=0, minute=0, second=0, microsecond=0) -> time:
    return time(hour, minute, second, microsecond, tzinfo=SKY_TIMEZONE)
