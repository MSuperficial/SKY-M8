from typing import Any
from zoneinfo import ZoneInfo

import discord
from discord import Interaction, app_commands, ui
from discord.ext import commands

from sky_bot import SkyBot

from ..helper.embeds import fail
from .profile import Profile
from .views import TimezoneDisplay


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
        private, tz = await Profile.user_fields(who.id, "private", "timezone")  # type: ignore
        # 两种情况下无效：查看对象是别人但其资料设置为private，或时区信息没有设置
        if (who != user and private) or not tz:
            desc = f"User {who.mention} does not provide time zone."
            if who == user:
                # 如果是用户自己的时区没设置，提醒通过指定的命令添加
                cmd = await self.bot.tree.find_mention_for(Profile.profile_timezone)  # type: ignore
                desc += f"\nUse {cmd} to save your default time zone."
            await interaction.followup.send(
                embed=await fail("No time zone", description=desc)
            )
            return
        tzinfo = ZoneInfo(tz)
        user_tz: str | None = await Profile.user_fields(user.id, "timezone")  # type: ignore
        display = TimezoneDisplay()
        # 只有在查看对象是别人，且用户自己设置了时区时，才显示时差信息
        if who != user and user_tz:
            embed = display.diff_embed(user, ZoneInfo(user_tz), who, tzinfo)
        else:
            embed = display.embed(who, tzinfo)
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

    @group_clock.command(name="compare", description="Compare a list of user's local times.")  # fmt: skip
    @app_commands.describe(
        first="The base user time zone to compute time difference with others.",
        public="Show the message to everyone, by default only you can see.",
    )
    async def clock_compare(
        self,
        interaction: Interaction,
        first: discord.User,
        second: discord.User,
        third: discord.User | None = None,
        fourth: discord.User | None = None,
        public: bool | None = False,
    ):
        await interaction.response.defer(ephemeral=True)
        # 筛选掉None、Bot用户和重复用户
        users: list[discord.User] = [u for u in [first, second, third, fourth] if u]
        users = [u for u in users if not u.bot]
        users = list(dict.fromkeys(users))
        if len(users) < 2:
            await interaction.followup.send(
                embed=await fail("At least two users (not bots) needed"),
            )
            return
        # 第一个用户的时区作为基准，必须不为空
        base = users[0]
        pri, tz = await Profile.user_fields(base.id, "private", "timezone")  # type: ignore
        if (base != interaction.user and pri) or not tz:
            await interaction.followup.send(
                embed=await fail(
                    "No time zone",
                    description=f"User {users[0].mention} does not provide time zone",
                ),
            )
            return
        view = ClockCompareView(base, ZoneInfo(tz), users[1:])
        msg_data = await view.create_message()
        if public:
            # 公开情况下，使用channel.send发送消息，但仍隐藏选择框
            msg = await interaction.channel.send(**msg_data)  # type: ignore
            await interaction.followup.send(view=view)
        else:
            msg = await interaction.followup.send(**msg_data, view=view)
        view.message = msg


class ClockCompareView(ui.View):
    def __init__(
        self,
        base: discord.User,
        base_tz: ZoneInfo,
        extras: list[discord.User],
    ):
        super().__init__(timeout=180)
        self.base = base
        self.base_tz = base_tz
        self.extras = extras
        self.select_users.default_values = extras
        self.message: discord.Message

    async def create_message(self) -> dict[str, Any]:
        infos = []
        for u in self.extras:
            pri, tz = await Profile.user_fields(u.id, "private", "timezone")  # type: ignore
            infos.append((u, ZoneInfo(tz) if not pri and tz else None))
        infos.insert(0, (self.base, self.base_tz))
        display = TimezoneDisplay()
        embed = display.compare_embed(infos)
        return {"embed": embed}

    @ui.select(
        cls=ui.UserSelect,
        placeholder="Select extra users to compare with...",
        min_values=1,
        max_values=25,
    )
    async def select_users(self, interaction: Interaction, select: ui.UserSelect):
        await interaction.response.defer()
        # 筛选掉基准用户和Bot用户
        users = [u for u in select.values if u != self.base and not u.bot]
        if len(users) < 1:
            await interaction.followup.send(
                embed=await fail("At least one extra users (not bots) needed"),
                ephemeral=True,
            )
            return
        self.extras = users
        msg_data = await self.create_message()
        await self.message.edit(**msg_data)
