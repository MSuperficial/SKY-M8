from datetime import datetime
from typing import Any, get_args
from zoneinfo import ZoneInfo

import discord
from discord import ButtonStyle, Interaction, app_commands, ui
from discord.ext import commands
from discord.utils import TimestampStyle, format_dt

from sky_bot import SkyBot

from ..base.views import DateModal, TimeModal, TimeZoneModal
from ..helper import formats, tzutils
from ..helper.embeds import fail
from ..helper.tzutils import (
    TimezoneFinder,
    format_hint,
    tz_autocomplete,
)
from ..info.profile import UserProfile

__all__ = ("TimestampMaker",)


class TimestampMaker(commands.Cog):
    def __init__(self, bot: SkyBot) -> None:
        self.bot = bot

    @app_commands.command(name="timestamp", description="Get formated discord timestamp, by default in your time zone.")  # fmt: skip
    @app_commands.describe(
        timezone="Use the specified time zone, can be a country where only one time zone is used.",
        others="Use the user's time zone if provided.",
    )
    @app_commands.autocomplete(timezone=tz_autocomplete)
    async def timestamp(
        self,
        interaction: Interaction,
        timezone: str | None = None,
        others: discord.User | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        # 使用时区的优先级 timezone > others > UserProfile
        tzinfo = None
        if timezone:
            # 尝试精确匹配时区
            if match := TimezoneFinder.exact_match(timezone):
                tzinfo = ZoneInfo(match[0])
            else:
                # 时区无效则提示用户可能的匹配并返回
                matches = TimezoneFinder.best_matches(timezone, limit=5)
                hint = format_hint(matches)
                embed = await fail(
                    "Invalid time zone",
                    description=f"Cannot find a time zone matching `{timezone}`.",
                )
                await interaction.followup.send(
                    content=hint,
                    embed=embed,
                )
                return
        elif others:
            # 获取指定用户的时区
            private, tz = await UserProfile.fields(others.id, "private", "timezone")  # type: ignore
            if not private and tz:
                tzinfo = ZoneInfo(tz)
            else:
                await interaction.followup.send(
                    embed=await fail(
                        "No time zone",
                        description=f"User {others.mention} does not provide time zone.",
                    )
                )
                return
        else:
            # 获取当前用户的时区
            tz: str = await UserProfile.fields(interaction.user.id, "timezone")  # type: ignore
            if tz:
                tzinfo = ZoneInfo(tz)
            else:
                cmd = await self.bot.tree.find_mention_for(UserProfile.profile_timezone)
                await interaction.followup.send(
                    embed=await fail(
                        "No time zone",
                        description=(
                            "You haven't set your time zone!\n"
                            f"Use {cmd} to save your default time zone, or specify an option."
                        ),
                    )
                )
                return
        now = datetime.now(tzinfo)
        view = TimestampView(datetime=now)
        msg_data = view.create_message()
        await interaction.followup.send(
            **msg_data,
            view=view,
        )


class TimestampView(ui.View):
    def __init__(self, *, datetime: datetime):
        super().__init__(timeout=300)
        self.dt = datetime

    def create_message(self) -> dict[str, Any]:
        tz: ZoneInfo = self.dt.tzinfo  # type: ignore
        country = tzutils.timezone_country.get(tz.key)
        selected = (
            "## Selected Date and Time\n"
            f"`{formats.dt_full(self.dt)}`\n"
            f"`{tz.key} {formats.utcoffset(self.dt)}{f' {country}' if country else ''}`"
        )
        tips = (
            "### How to copy\n"
            "- PC: Triple click the timestamp and press `Ctrl/Cmd+C`\n"
            "- Mobile: Simply tap on the timestamp"
        )
        styles = get_args(TimestampStyle)
        timestamps = [format_dt(self.dt, s) for s in styles]
        timestamps = [f"### `{t}`\n> {t}" for t in timestamps]
        content = "\n".join([selected, tips] + timestamps)
        return {
            "content": content,
        }

    async def update_message(self, interaction: Interaction):
        msg_data = self.create_message()
        await interaction.edit_original_response(**msg_data)

    @ui.button(label="Date", emoji="📅", style=ButtonStyle.primary)
    async def set_date(self, interaction: Interaction, button: ui.Button):
        modal = DateModal(dt=self.dt)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.valid:
            self.dt = self.dt.replace(year=modal.year, month=modal.month, day=modal.day)
            await self.update_message(interaction)

    @ui.button(label="Time", emoji="🕒", style=ButtonStyle.primary)
    async def set_time(self, interaction: Interaction, button: ui.Button):
        modal = TimeModal(dt=self.dt)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.valid:
            self.dt = self.dt.replace(hour=modal.hour, minute=modal.minute, second=modal.second)  # fmt: skip
            await self.update_message(interaction)

    @ui.button(label="Time Zone", emoji="🗺️", style=ButtonStyle.primary)
    async def set_timezone(self, interaction: Interaction, button: ui.Button):
        modal = TimeZoneModal(dt=self.dt)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.valid:
            # 不同于astimezone，replace只替换时区，不修改时间
            self.dt = self.dt.replace(tzinfo=modal.timezone)
            await self.update_message(interaction)

    @ui.button(label="Set to current", style=ButtonStyle.primary)
    async def set_to_current(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer()
        self.dt = datetime.now(self.dt.tzinfo)
        await self.update_message(interaction)
