import asyncio
import typing
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks
from discord.utils import format_dt as timestamp

from ..sky_bot import SkyBot
from ..sky_event import DailyEvent, daily_event_datas, get_daily_event_time
from ..sky_event.shard import get_shard_info
from ..utils import code_block, msg_exist_async, sky_time_now

__all__ = ("DailyClock",)


class DailyClock(commands.Cog):
    _CLOCK_MSG_ID = "-# ᴰᵃᶦˡʸᴱᵛᵉⁿᵗˢ"

    def __init__(self, bot: SkyBot):
        self.bot = bot
        self.clock_message: discord.Message = None
        self.last_msg_hash = hash(None)
        self.update_clock_msg.start()

    async def cog_unload(self):
        self.update_clock_msg.cancel()

    def get_daily_event_msg(self, when: datetime, daily_id: DailyEvent):
        name = daily_event_datas[daily_id].name
        current_end, next_begin = get_daily_event_time(when, daily_id)
        # 事件名称
        msg = f"### {name}\n"
        # 当前事件结束时间
        if current_end is not None:
            msg += f"-# 🔹 Current ends {timestamp(current_end, 'R')}.\n"
        # 下次事件开始时间
        msg += (
            f"-# 🔸 Next at {timestamp(next_begin, 't')}, {timestamp(next_begin, 'R')}."
        )
        return msg

    def get_all_daily_event_msg(self, when: datetime, header=True, footer=True):
        dailies = list(DailyEvent)
        shard_info = get_shard_info(when)
        # 如果今天Peaks Shard不提供烛火，则无需显示其信息
        if not (shard_info.has_shard and shard_info.extra_shard):
            dailies.remove(DailyEvent.PEAKS_SHARD)  # 移除该事件
        msgs = [self.get_daily_event_msg(when, e) for e in dailies]
        dailies_msg = "\n".join(msgs)
        if header:
            dailies_msg = "# Sky Daily Clock\n" + dailies_msg
        if footer:
            dailies_msg = (
                dailies_msg
                + "\n\n-# *See [Sky Clock](<https://sky-clock.netlify.app>) by [Chris Stead](<https://github.com/cmstead>) for more.*"
            )
        return dailies_msg

    @commands.command()
    async def daily(self, ctx: commands.Context, offset: typing.Optional[int] = 0):
        now = sky_time_now()
        date = now + timedelta(days=offset)
        msg = self.get_all_daily_event_msg(date)
        await ctx.send(msg)

    # 事件信息每分钟检查一次更新
    @tasks.loop(minutes=1)
    async def update_clock_msg(self):
        # 生成事件信息
        now = sky_time_now()
        daily_event_msg = self.get_all_daily_event_msg(now)
        daily_event_msg = self._CLOCK_MSG_ID + "\n" + daily_event_msg
        # 如果消息内容和上一次更新相同则跳过
        msg_hash = hash(daily_event_msg)
        if msg_hash == self.last_msg_hash:
            return
        # 如果已记录消息，则直接更新
        message = self.clock_message
        if message and await msg_exist_async(message):
            await message.edit(content=daily_event_msg)
            self.last_msg_hash = msg_hash
            print(f"[{sky_time_now()}] Success editting clock message.")
            return
        # 查找频道和消息
        channel = self.bot.get_bot_channel()
        message = await self.bot.search_message_async(channel, self._CLOCK_MSG_ID)
        # 如果消息不存在，则发送新消息；否则编辑现有消息
        if message is None:
            message = await channel.send(daily_event_msg)
            print(f"[{sky_time_now()}] Success sending clock message.")
        else:
            await message.edit(content=daily_event_msg)
            print(f"[{sky_time_now()}] Success editing clock message.")
        # 记录消息，下次可以直接使用
        self.clock_message = message
        self.last_msg_hash = msg_hash

    @update_clock_msg.before_loop
    async def wait_on_minute(self):
        # 等待客户端就绪
        await self.bot.wait_until_ready()
        # 先更新一次
        await self.update_clock_msg()
        # 等待到下一个1分钟整
        now = sky_time_now()
        wait_second = 60 - now.second
        print(f"[{now}] Getting ready, wait {wait_second} seconds for next minute.")
        await asyncio.sleep(wait_second)

    @update_clock_msg.error
    async def clock_error(self, error):
        task_name = self.update_clock_msg.coro.__name__
        error_msg = (
            f"Error during task `{task_name}`: `{type(error).__name__}`\n"
            f"{code_block(error)}"
        )
        print(error_msg)
        await self.bot.owner.send(error_msg)


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyClock(bot))
