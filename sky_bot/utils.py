import os
from datetime import datetime, time

import discord
from zoneinfo import ZoneInfo

__all__ = (
    "SKY_TIMEZONE",
    "get_id_from_env",
    "sky_time_now",
    "msg_exist_async",
)

SKY_TIMEZONE = ZoneInfo("America/Los_Angeles")


def get_id_from_env(key):
    if (id_str := os.getenv(key)) is None:
        raise Exception("Missing environment variable " + key)
    return int(id_str)


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


def code_block(msg, lang=None):
    return f"```{lang}\n{msg}\n```"


async def msg_exist_async(msg: discord.Message):
    try:
        await msg.fetch()
        return True
    except discord.NotFound:
        return False
