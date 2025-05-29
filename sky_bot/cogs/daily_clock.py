import asyncio
from datetime import datetime, timedelta
from typing import Any

from discord.ext import commands
from discord.utils import format_dt as timestamp

from ..sky_bot import SkyBot
from ..sky_event.daily import DailyEvent, daily_event_datas, get_daily_event_time
from ..sky_event.shard import get_shard_info
from ..utils import sky_time_now
from .base.live_update import LiveUpdateCog

__all__ = ("DailyClock",)


class DailyClock(
    LiveUpdateCog,
    live_key="dailyClock.webhooks",
    group_live_name="clock-live",
    live_display_name="Sky Clock",
    live_update_interval={"minutes": 1},
):
    def __init__(self, bot: SkyBot):
        super().__init__(bot)

    def get_daily_event_msg(self, when: datetime, daily_id: DailyEvent):
        name = daily_event_datas[daily_id].name
        current_end, next_begin = get_daily_event_time(when, daily_id)
        # 事件名称
        msg = f"### {name}\n"
        # 当前事件结束时间
        if current_end is not None:
            msg += f"-# 🔹 Current ends {timestamp(current_end, 'R')}.\n"
        # 下次事件开始时间
        msg += f"-# 🔸 Next at {timestamp(next_begin, 't')}, {timestamp(next_begin, 'R')}."  # fmt: skip
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
            dailies_msg += "\n\n-# *See [Sky Clock](<https://sky-clock.netlify.app>) by [Chris Stead](<https://github.com/cmstead>) for more.*"  # fmt: skip
        return dailies_msg

    @commands.command()
    async def clock(self, ctx: commands.Context, offset: int = 0):
        now = sky_time_now()
        date = now + timedelta(days=offset)
        msg = self.get_all_daily_event_msg(date)
        await ctx.send(msg)

    async def get_live_message_data(self, **kwargs) -> dict[str, Any]:
        now = sky_time_now()
        content = self.get_all_daily_event_msg(now)
        return {"content": content}

    def check_need_update(self, data: dict[str, Any]):
        old = self.last_msg_data.get("content")
        new = data.get("content")
        return old != new

    async def get_ready_for_live(self):
        # 等待到下一个1分钟整
        now = sky_time_now()
        wait_second = 60 - now.second
        print(f"[{now}] Getting ready, wait {wait_second} seconds for next minute.")
        await asyncio.sleep(wait_second)


async def setup(bot: SkyBot):
    await bot.add_cog(DailyClock(bot))
