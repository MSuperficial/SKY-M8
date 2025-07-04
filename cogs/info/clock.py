from typing import Any
from zoneinfo import ZoneInfo

import discord
from discord import Interaction, app_commands, ui
from discord.ext import commands

from sky_bot import AppUser, SkyBot

from ..base.views import AutoDisableView
from ..helper.embeds import fail
from .display import TimezoneDisplay
from .profile import UserProfile


class Clock(commands.Cog):
    group_clock = app_commands.Group(
        name="clock",
        description="View and compare user's time.",
    )

    def __init__(self, bot: SkyBot):
        self.bot = bot
        # 手动添加菜单命令，dpy库不支持自动绑定
        self.cmd_menu_view = app_commands.ContextMenu(
            name="View Clock",
            callback=self.menu_view,
        )
        self.bot.tree.add_command(self.cmd_menu_view)

    async def cog_unload(self):
        # 卸载时移除菜单命令
        self.bot.tree.remove_command(
            self.cmd_menu_view.name,
            type=self.cmd_menu_view.type,
        )

    async def _view_someones_clock(self, interaction: Interaction, who: discord.User):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user
        guild_id = interaction.guild_id or 0
        hidden, tz = await UserProfile.fields(
            who.id,
            *["hidden", "timezone"],
            guild_id=guild_id,
        )
        # 两种情况下无效：查看对象是别人但其资料设置为hidden，或时区信息没有设置
        if (who != user and hidden) or not tz:
            desc = f"User {who.mention} does not provide time zone."
            if who == user:
                # 如果是用户自己的时区没设置，提醒通过指定的命令添加
                cmd = await self.bot.tree.find_mention_for(UserProfile.profile_timezone)
                desc += f"\nUse {cmd} to save your default time zone."
            await interaction.followup.send(embed=fail("No time zone", desc))
            return
        tzinfo = ZoneInfo(tz)
        display = TimezoneDisplay()
        # 只有在查看对象是别人，且用户自己设置了时区时，才显示时差信息
        user_tzinfo = None
        if who != user:
            user_tz: str | None = await UserProfile.fields(
                user.id,
                "timezone",
                guild_id=guild_id,
            )
            user_tzinfo = ZoneInfo(user_tz) if user_tz else None
        embed = display.embed(who, tzinfo, user_tzinfo)
        await interaction.followup.send(embed=embed)

    @group_clock.command(name="view", description="View someone's local time.")
    @app_commands.describe(
        who="Whose time you want to view.",
    )
    async def clock_view(self, interaction: Interaction, who: discord.User):
        await self._view_someones_clock(interaction, who)

    # context menu
    async def menu_view(self, interaction: Interaction, who: discord.User):
        await self._view_someones_clock(interaction, who)

    @group_clock.command(name="compare", description="Compare multiple user's local times.")  # fmt: skip
    @app_commands.describe(
        user1="The user to compare with.",
        user2="The user to compare with.",
        user3="The user to compare with.",
        user4="The user to compare with.",
        show_message="Show message to everyone, this will hide DIFF info and your time zone (if hidden), by default False.",
    )
    async def clock_compare(
        self,
        interaction: Interaction,
        user1: discord.User,
        user2: discord.User,
        user3: discord.User | None = None,
        user4: discord.User | None = None,
        show_message: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)
        # 筛选掉None、Bot用户和重复用户
        users = [u for u in [user1, user2, user3, user4] if u]
        users = [u for u in users if not u.bot]
        users = list(dict.fromkeys(users))
        if len(users) < 2:
            await interaction.followup.send(
                embed=fail("At least two users (not bot) needed"),
            )
            return
        # 当前用户的时区作为基准
        base = interaction.user
        guild_id = interaction.guild_id or 0
        view = ClockCompareView(guild_id, users, base, show_message)
        msg_data = await view.create_message()
        if show_message:
            # 公开情况下，使用channel.send发送消息，但仍隐藏UI组件
            clock_msg = await interaction.channel.send(**msg_data)  # type: ignore
            response_msg = await interaction.followup.send(view=view)
        else:
            clock_msg = response_msg = await interaction.followup.send(
                **msg_data,
                view=view,
            )
        view.clock_msg = clock_msg
        view.response_msg = response_msg


class ClockCompareView(AutoDisableView):
    def __init__(
        self,
        guild_id: int,
        users: list[AppUser],
        base: AppUser,
        show: bool,
    ):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.users = users
        self.base = base
        self.show = show
        self.select_users.default_values = users
        self.clock_msg: discord.Message

    async def create_message(self) -> dict[str, Any]:
        hidden, tz = await UserProfile.fields(
            self.base.id,
            *["hidden", "timezone"],
            guild_id=self.guild_id,
        )
        base_tz = ZoneInfo(tz) if tz else None
        hide_base = self.show and hidden
        infos = []
        for u in self.users:
            if u == self.base:
                infos.append((u, None if hide_base else base_tz))
                continue
            hidden, tz = await UserProfile.fields(
                u.id,
                *["hidden", "timezone"],
                guild_id=self.guild_id,
            )
            infos.append((u, ZoneInfo(tz) if not hidden and tz else None))
        display = TimezoneDisplay()
        embed = display.compare_embed(infos, None if self.show else base_tz)
        return {"embed": embed}

    @ui.select(
        cls=ui.UserSelect,
        placeholder="Select users to compare with...",
        min_values=2,
        max_values=25,
    )
    async def select_users(self, interaction: Interaction, select: ui.UserSelect):
        await interaction.response.defer()
        # 筛选掉Bot用户
        users = [u for u in select.values if not u.bot]
        if len(users) < 2:
            await interaction.followup.send(
                embed=fail("At least two users (not bot) needed"),
                ephemeral=True,
            )
            return
        self.users = users
        msg_data = await self.create_message()
        await self.clock_msg.edit(**msg_data)
