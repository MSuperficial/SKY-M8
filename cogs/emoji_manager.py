from types import MappingProxyType
from typing import overload

from discord import Emoji
from discord.ext import commands

from sky_m8 import SkyM8
from utils.remote_config import remote_config


class EmojiManager(commands.Cog):
    _EMOJI_KEY = "emojis"

    def __init__(self, bot: SkyM8):
        self.bot = bot

    async def cog_load(self):
        await self.update_emojis()

    async def update_emojis(self):
        emojis = self.bot.app_emojis
        emoji_mapping = await remote_config.get_dict(self._EMOJI_KEY)
        emoji_override = {k: emojis.get(v, v) for k, v in emoji_mapping.items()}
        emojis = emojis | emoji_override
        Emojis._update(emojis)
        return emojis

    @commands.is_owner()
    @commands.group(name="emoji", invoke_without_command=True)
    async def group_emoji(self, ctx: commands.Context, *, arg: str):
        await ctx.send(f"No subcommand named `{arg}`")

    @group_emoji.command(name="update")
    async def emoji_update(self, ctx: commands.Context):
        await self.bot.fetch_application_emojis()
        await self.update_emojis()
        await ctx.message.add_reaction(Emojis("success", "✅"))


class EmojiFinder:
    def __init__(self, emojis: dict[str, str | Emoji]):
        self.emojis = MappingProxyType(emojis)

    def _update(self, emojis: dict[str, str | Emoji]):
        self.emojis = MappingProxyType(emojis)

    @overload
    def __call__(self, name: str, default: None = None) -> str | Emoji | None: ...
    @overload
    def __call__(self, name: str, default: str | Emoji) -> str | Emoji: ...

    def __call__(self, name: str, default=None):
        return self.get(name, default)

    @overload
    def get(self, name: str, default: None = None) -> str | Emoji | None: ...
    @overload
    def get(self, name: str, default: str | Emoji) -> str | Emoji: ...

    def get(self, name: str, default=None):
        return self.emojis.get(name, default)

    @overload
    def format(self, name: str, default: None = None) -> str | None: ...
    @overload
    def format(self, name: str, default: str | Emoji) -> str: ...

    def format(self, name: str, default=None):
        emoji = self.emojis.get(name, default)
        value = emoji and str(emoji)
        return value


Emojis = EmojiFinder({})


async def setup(bot: SkyM8):
    await bot.add_cog(EmojiManager(bot))
