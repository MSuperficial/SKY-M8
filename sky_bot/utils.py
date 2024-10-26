import os
from datetime import datetime

import discord
import pytz

__all__ = (
    "SKY_TIMEZONE",
    "get_id_from_env",
    "sky_time_now",
    "msg_exist_async",
)

SKY_TIMEZONE = pytz.timezone("America/Los_Angeles")


def get_id_from_env(key):
    if (id_str := os.getenv(key)) is None:
        raise Exception("Missing environment variable " + key)
    return int(id_str)


def sky_time_now() -> datetime:
    return datetime.now(SKY_TIMEZONE)


def code_block(msg, lang=None):
    return f"```{lang}\nmsg\n```"


async def msg_exist_async(msg: discord.Message):
    try:
        await msg.fetch()
        return True
    except discord.NotFound:
        return False
