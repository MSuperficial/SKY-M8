import re
from datetime import datetime
from typing import Any, cast

import discord
from discord import Interaction, app_commands, ui

from sky_m8 import SkyM8

from ..base.live_update import LiveUpdateCog
from ..helper.formats import timestamp
from ..helper.times import SKY_TIMEZONE, sky_time, sky_time_now
from .data.shard import get_shard_info
from .shard_calendar import ShardCalendar, get_shard_config
from .sky_clock import SkyClock


class DailyGuides(
    LiveUpdateCog,
    live_key="dailyGuides.webhooks",
    group_live_name="dailyguides-live",
    live_display_name="Daily Guides",
    live_update_interval={"time": sky_time(0, 0, 0)},
):
    def __init__(self, bot: SkyM8):
        super().__init__(bot)

    def get_guides_message_data(self, date: datetime | None = None) -> dict[str, Any]:
        date = date or sky_time_now()
        view = DailyGuidesView(date)
        return {"view": view}

    async def get_live_message_data(self, **kwargs) -> dict[str, Any]:
        return self.get_guides_message_data(**kwargs)

    @app_commands.command(name="dailyguides", description="View various guides today in Sky.")
    async def daily_guides(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        msg_data = self.get_guides_message_data()
        await interaction.followup.send(**msg_data)


class DailyGuidesView(ui.LayoutView):
    def __init__(self, date: datetime):
        super().__init__(timeout=None)
        date = date.astimezone(SKY_TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0)
        self.date = date

        container = ui.Container(
            ui.TextDisplay(f"**Daily Guides** - {timestamp(date, 'D')}"),
            ui.Separator(spacing=discord.SeparatorSpacing.large),
            *self._comp_shard(),
            ui.Separator(),
            *self._comp_clock(),
        )
        self.add_item(container)

    def _comp_shard(self) -> list[ui.Item]:
        info = get_shard_info(self.date)
        config = get_shard_config()
        comps = []
        if info.has_shard:
            # 碎石类型
            type_emoji = config["emojis"][info.type.name]
            reward_unit = config["emojis"][info.reward_type.name]
            text_type = (
                f"### {type_emoji} {info.type.name} Shard [{info.reward_number}{reward_unit}]"
            )
            # 时间线
            text_timeline = "\n".join(
                [
                    f"▸ {timestamp(lt, 't')} - {timestamp(et, 't')}"
                    for st, lt, et in info.occurrences
                ]
            )
            # 地图图片
            map_url = config["infographics"].get(".".join([info.realm, info.map]))
            if map_url:
                comps.append(
                    ui.Section(
                        ui.TextDisplay(text_type),
                        ui.TextDisplay(text_timeline),
                        accessory=ui.Thumbnail(map_url),
                    )
                )
            else:
                comps.append(ui.TextDisplay(text_type))
                comps.append(ui.TextDisplay(text_timeline))
        else:
            comps.append(ui.TextDisplay("### ☀️ No Shard Day"))
        comps.append(ui.ActionRow(ViewShardButton(self.date)))  # type: ignore
        return comps

    def _comp_clock(self) -> list[ui.Item]:
        return [
            ui.TextDisplay("### 🕒 Sky Clock"),
            ui.ActionRow(ViewClockButton()),  # type: ignore
        ]


class ViewShardButton(ui.DynamicItem[ui.Button], template=r"guides-view-shard:(?P<date>[0-9]{8})"):
    def __init__(self, date: datetime):
        super().__init__(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="View Detail",
                custom_id=f"guides-view-shard:{date:%Y%m%d}",
            )
        )
        self.date = date

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        date = datetime.strptime(match["date"], "%Y%m%d")
        date = date.replace(tzinfo=SKY_TIMEZONE)
        return cls(date)

    async def callback(self, interaction: Interaction[SkyM8]):  # type: ignore
        await interaction.response.defer()
        bot = interaction.client
        cog = cast(ShardCalendar, bot.cogs[ShardCalendar.__cog_name__])
        msg_data = await cog.get_shard_message_data(date=self.date, persistent=False)
        await interaction.followup.send(**msg_data, ephemeral=True)


class ViewClockButton(ui.DynamicItem[ui.Button], template=r"guides-view-clock"):
    def __init__(self):
        super().__init__(
            ui.Button(
                style=discord.ButtonStyle.secondary,
                label="View Detail",
                custom_id="guides-view-clock",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls()

    async def callback(self, interaction: Interaction[SkyM8]):  # type: ignore
        await interaction.response.defer()
        bot = interaction.client
        cog = cast(SkyClock, bot.cogs[SkyClock.__cog_name__])
        msg_data = await cog.get_clock_message_data()
        await interaction.followup.send(**msg_data, ephemeral=True)


async def setup(bot: SkyM8):
    bot.add_dynamic_items(ViewShardButton, ViewClockButton)
    await bot.add_cog(DailyGuides(bot))
