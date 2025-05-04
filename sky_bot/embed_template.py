from discord import Color, Embed

from .remote_config import remote_config

__all__ = ("success", "fail")


async def success(title: str, *, color=Color.green(), description=None):
    _emoji_success = await remote_config.get_field("emojis", "success") or "✅"
    return Embed(
        color=color,
        title=_emoji_success + " " + title,
        description=description,
    )


async def fail(title: str, *, color=Color.red(), description=None):
    _emoji_fail = await remote_config.get_field("emojis", "fail") or "❌"
    return Embed(
        color=color,
        title=_emoji_fail + " " + title,
        description=description,
    )
