from datetime import datetime, time
from zoneinfo import ZoneInfo

__all__ = (
    "SKY_TIMEZONE",
    "sky_time_now",
    "sky_datetime",
    "sky_time",
    "format_utcoffset",
    "format_dt_full",
    "code_block",
)

SKY_TIMEZONE = ZoneInfo("America/Los_Angeles")


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


def format_utcoffset(dt: datetime):
    offset = dt.strftime("%z")
    if offset:
        offset = f"UTC{offset[:3]}:{offset[3:]}"
    return offset


def format_dt_full(dt: datetime):
    dt_str = dt.strftime("%Y/%m/%d %A %H:%M:%S")
    return dt_str


def code_block(msg, lang=None):
    return f"```{lang}\n{msg}\n```"
