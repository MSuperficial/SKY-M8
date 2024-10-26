import discord
from discord.ext import commands

from .utils import get_id_from_env

__all__ = ("SkyBot",)


class SkyBot(commands.Bot):
    def __init__(self, *args, initial_extensions: list[str], **kwargs):
        super().__init__(*args, **kwargs)
        self.initial_extensions = initial_extensions
        # 获取ID
        self.guild_id = get_id_from_env("GUILD_ID")
        self.bot_channel_id = get_id_from_env("BOT_CHANNEL_ID")
        self.bot_channel: discord.TextChannel = None

    async def setup_hook(self) -> None:
        # 加载初始扩展
        for extension in self.initial_extensions:
            extension = "sky_bot.cogs." + extension
            await self.load_extension(extension)

    async def on_ready(self):
        print(f"We have logged in as {self.user}")

    def is_mine(self, message: discord.Message):
        return message.author == self.user

    async def on_message(self, message: discord.Message):
        # 忽略自己的消息
        if self.is_mine(message):
            return
        # 处理命令
        await super().on_message(message)

    def get_bot_channel(self):
        if self.bot_channel is not None:
            return self.bot_channel
        # 如果服务器不存在，则返回None
        if (guild := self.get_guild(self.guild_id)) is None:
            return None
        # 根据id获取频道
        self.bot_channel = guild.get_channel(self.bot_channel_id)
        return self.bot_channel

    async def search_message_async(self, channel: discord.TextChannel, id: str):
        # 在频道记录里查找包含id的消息
        return await discord.utils.find(
            lambda m: self.is_mine(m) and m.content.startswith(id),
            channel.history(),
        )
