from typing import Any

from discord import Color, Embed

from cogs.emoji_manager import Emojis

__all__ = (
    "success",
    "fail",
)


def success(title: str, description: Any | None = None, *, color=Color.green()):
    return Embed(
        color=color,
        title=f"{Emojis('success', '✅')} {title}",
        description=description,
    )


def fail(title: str, description: Any | None = None, *, color=Color.red()):
    return Embed(
        color=color,
        title=f"{Emojis('fail', '❌')} {title}",
        description=description,
    )
