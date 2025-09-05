import asyncio
from datetime import datetime, timedelta
from typing import Any, cast

import discord
from discord import ui
from discord.ext import commands
from discord.utils import MISSING
from discord.utils import format_dt as timestamp

from sky_m8 import SkyM8

from ..base.live_update import LiveUpdateCog
from ..helper.times import sky_time_now
from .data.daily import (
    DailyEventData,
    EventGroup,
    fetch_all_event_data,
    fetch_displayed_event_groups,
    filter_events,
    get_daily_event_time,
)

__all__ = ("DailyClock",)


class DailyClock(
    LiveUpdateCog,
    live_key="dailyClock.webhooks",
    group_live_name="skyclock-live",
    live_display_name="Sky Clock",
    live_update_interval={"minutes": 1},
):
    def __init__(self, bot: SkyM8):
        super().__init__(bot)

    async def get_clock_message_data(self, *, when: datetime = MISSING) -> dict[str, Any]:
        when = when or sky_time_now()
        groups = await fetch_displayed_event_groups()
        data = await fetch_all_event_data()
        available_groups = filter_events(groups, data, when)
        view = SkyClockView(dt=when, groups=available_groups, data=data)
        return {"view": view}

    async def get_live_message_data(self, **kwargs) -> dict[str, Any]:
        return await self.get_clock_message_data(**kwargs)

    def check_need_update(self, data: dict[str, Any]):
        old = cast(SkyClockView | None, self.last_msg_data.get("view"))
        new = cast(SkyClockView, data.get("view"))
        return old is None or old._plain_content != new._plain_content

    @commands.command()
    async def skyclock(self, ctx: commands.Context, offset: int = 0):
        now = sky_time_now()
        date = now + timedelta(days=offset)
        msg_data = await self.get_clock_message_data(when=date)
        await ctx.send(**msg_data)

    async def get_ready_for_live(self):
        # 等待到下一个1分钟整
        now = sky_time_now()
        wait_second = 60 - now.second
        print(f"[{now}] Getting ready, wait {wait_second} seconds for next minute.")
        await asyncio.sleep(wait_second)


class SkyClockView(ui.LayoutView):
    def __init__(
        self,
        *,
        dt: datetime,
        groups: list[EventGroup],
        data: dict[str, DailyEventData],
    ):
        super().__init__(timeout=None)
        self.dt = dt
        self._plain_content = ""

        comps: list[ui.Item] = []
        for i, g in enumerate(groups):
            comps.extend(self._comp_group(g, data))
            if i < len(groups) - 1:
                comps.append(ui.Separator(spacing=discord.SeparatorSpacing.large))

        container = ui.Container(
            ui.TextDisplay("## Sky Clock"),
            ui.Separator(spacing=discord.SeparatorSpacing.large),
            *comps,
        )
        self.add_item(container)

    def _comp_group(self, group: EventGroup, data: dict[str, DailyEventData]):
        comps: list[ui.Item] = []
        if group["displayName"] and group["name"]:
            comps.append(ui.TextDisplay(f"### {group['name']}"))
            self._plain_content += group["name"] + "\n"
        for e in group["events"]:
            comps.append(self._comp_event(data[e]))
        return comps

    def _comp_event(self, event_data: DailyEventData) -> ui.Item:
        current_end, next_begin = get_daily_event_time(self.dt, event_data)
        # 事件名称
        text = f"**{event_data.name}**\n"
        # 当前事件结束时间
        if current_end is not None:
            text += f"-# 🔹 Current ends {timestamp(current_end, 'R')}\n"
        # 下次事件开始时间
        if next_begin is not None:
            text += f"-# 🔸 Next at {timestamp(next_begin, 't')}, {timestamp(next_begin, 'R')}"
        else:
            text += "-# 🔸 No more event for today"
        self._plain_content += text + "\n"
        comp = ui.TextDisplay(text)
        return comp


async def setup(bot: SkyM8):
    await bot.add_cog(DailyClock(bot))
