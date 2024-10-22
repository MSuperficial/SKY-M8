import asyncio

import discord
from discord.ext import commands, tasks

from .sky_event import get_all_daily_event_msg, respond_daily_event
from .utils import get_id_from_env, sky_time_now

__all__ = ("SkyBot",)


class SkyBot(commands.Bot):
    _DAILY_EVENT_MSG_ID = "-# ᴰᵃᶦˡʸᴱᵛᵉⁿᵗˢ"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 获取ID
        self.guild_id = get_id_from_env("GUILD_ID")
        self.bot_channel_id = get_id_from_env("BOT_CHANNEL_ID")
        self.bot_channel: discord.TextChannel = None
        self.daily_info_message: discord.Message = None

    async def setup_hook(self) -> None:
        # 开始定时更新事件信息
        self.update_daily_time_msg.start()

    async def on_ready(self):
        print(f"We have logged in as {self.user}")

    def is_mine(self, message: discord.Message):
        return message.author == self.user

    async def on_message(self, message: discord.Message):
        # 忽略自己的消息
        if self.is_mine(message):
            return
        # 回应消息
        match message.content:
            case "!event":
                await respond_daily_event(message)
        await super().on_message(message)

    def get_bot_channel(self):
        # 如果服务器不存在，则返回None
        if (guild := self.get_guild(self.guild_id)) is None:
            return None
        # 根据id获取频道
        self.bot_channel = guild.get_channel(self.bot_channel_id)
        return self.bot_channel

    async def search_message(self, channel: discord.TextChannel, id: str):
        # 在频道记录里查找包含id的消息
        return await discord.utils.find(
            lambda m: self.is_mine(m) and m.content.startswith(id),
            channel.history(),
        )

    # 事件信息每5分钟更新一次
    @tasks.loop(minutes=5)
    async def update_daily_time_msg(self):
        try:
            print(f"[{sky_time_now()}] Start updating daily time message.")
            # 生成事件信息
            now = sky_time_now()
            daily_time_msg = (
                self._DAILY_EVENT_MSG_ID + "\n" + get_all_daily_event_msg(now)
            )
            print(f"[{sky_time_now()}] Got daily time info.")
            # 如果已记录消息，则直接更新
            message = self.daily_info_message
            if message is not None:
                try:
                    await message.edit(content=daily_time_msg)
                    print(f"[{sky_time_now()}] Success editting daily time message.")
                    return
                except discord.NotFound:
                    print(f"[{sky_time_now()}] Daily time message not found.")
            # 查找频道和消息
            channel = self.bot_channel or self.get_bot_channel()
            print(f"[{sky_time_now()}] Found channel.")
            message = await self.search_message(channel, self._DAILY_EVENT_MSG_ID)
            print(
                f"[{sky_time_now()}] {'Failed' if message is None else 'Succeed'} to search message."
            )
            # 如果消息不存在，则发送新消息；否则编辑现有消息
            if message is None:
                message = await channel.send(daily_time_msg)
                print(f"[{sky_time_now()}] Success sending daily time message.")
            else:
                await message.edit(content=daily_time_msg)
                print(f"[{sky_time_now()}] Success editing daily time message.")
            # 记录消息，下次可以直接使用
            self.daily_info_message = message
        except Exception as e:
            print(f"[{sky_time_now()}] Exception while updating daily time message:")
            print(type(e))
            print(e)
            raise e

    @update_daily_time_msg.before_loop
    async def wait_on_minute(self):
        # 等待客户端就绪
        await self.wait_until_ready()
        # 先更新一次
        await self.update_daily_time_msg()
        # 等待到下一个5分钟整
        now = sky_time_now()
        second = now.minute * 60 + now.second
        wait_second = (5 * 60) - second % (5 * 60)
        print(f"[{now}] Getting ready, wait {wait_second} seconds for next 5 minutes.")
        await asyncio.sleep(wait_second)
