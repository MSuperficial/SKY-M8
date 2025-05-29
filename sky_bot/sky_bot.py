import discord
from discord.app_commands import AppCommandContext, AppInstallationType
from discord.ext import commands
from discord.utils import MISSING

from .cogs.cog_manager import CogManager

__all__ = ("SkyBot",)


class SkyBot(commands.Bot):
    def __init__(self, *args, initial_extensions: list[str], **kwargs):
        super().__init__(
            allowed_installs=AppInstallationType(guild=True, user=True),
            allowed_contexts=AppCommandContext(
                guild=True, dm_channel=True, private_channel=True
            ),
            *args,
            **kwargs,
        )
        self.initial_extensions = initial_extensions
        self._owner: discord.User = MISSING

    async def setup_hook(self) -> None:
        # 加载初始扩展
        await self.add_cog(CogManager(self))
        for extension in self.initial_extensions:
            extension = "sky_bot.cogs." + extension
            await self.load_extension(extension)

    async def on_ready(self):
        print(f"We have logged in as {self.user}")

    @property
    def owner(self):
        if not self._owner:
            self._owner = self.get_user(self.owner_id)  # type: ignore
        return self._owner

    def is_mine(self, message: discord.Message):
        return message.author == self.user

    async def on_message(self, message: discord.Message):
        # 忽略自己的消息
        if self.is_mine(message):
            return
        # 处理命令
        await super().on_message(message)
