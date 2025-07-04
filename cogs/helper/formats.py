from datetime import datetime
from typing import get_args

from discord.utils import TimestampStyle, format_dt

__all__ = (
    "ordinal",
    "timestamp",
    "utcoffset",
    "dt_full",
    "code_block",
)


def ordinal(number: int):
    suffix = "th"
    num_abs = abs(number)
    dig_1 = num_abs % 10
    dig_2 = num_abs // 10 % 10
    if dig_1 in [1, 2, 3] and dig_2 != 1:
        suffix = ["st", "nd", "rd"][dig_1 - 1]
    return str(number) + suffix


def timestamp(dt: datetime, style: str | None):
    style = style or "f"
    if style == "u":
        return str(int(dt.timestamp()))
    elif style in get_args(TimestampStyle):
        return format_dt(dt, style)  # type: ignore
    else:
        return None


def utcoffset(dt: datetime):
    offset = dt.strftime("%z")
    if offset:
        offset = f"UTC{offset[:3]}:{offset[3:]}"
    return offset


def tzdiff(base: datetime, other: datetime):
    this_utc = base.utcoffset()
    that_utc = other.utcoffset()
    delta = that_utc - this_utc  # type: ignore
    minutes = int(delta.total_seconds() / 60)
    sign = "+" if minutes >= 0 else "-"
    hours, minutes = divmod(abs(minutes), 60)
    diff = f"{sign}{hours:0>2d}:{minutes:0>2d}"
    return diff


def dt_full(dt: datetime):
    dt_str = dt.strftime("%Y/%m/%d %H:%M:%S %A")
    return dt_str


def dt_short(dt: datetime):
    dt_str = dt.strftime("%m/%d %H:%M")
    return dt_str


def code_block(msg, lang=""):
    return f"```{lang}\n{msg}\n```"
