from contextlib import suppress
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

import discord
from discord import Interaction, app_commands, ui
from discord.app_commands import Choice
from discord.ext import commands

from sky_bot import AppUser, SkyBot
from utils.remote_config import remote_config

from ..base.views import AutoDisableView, ShortTextModal
from ..helper.embeds import fail, success
from .display import TimezoneDisplay
from .profile import UserProfile


class ClockGroup(NamedTuple):
    name: str
    ids: list[int]


class ClockGroupTransformer(app_commands.Transformer):
    async def transform(self, interaction: Interaction, value: str):
        group = await Clock._get_group(interaction.user, value)
        return group

    async def autocomplete(self, interaction: Interaction, value: str):  # type: ignore
        choices: list[Choice[str]] = []
        names = await Clock._list_group(interaction.user)
        if not names:
            return choices
        choices = [Choice(name=n, value=n) for n in names if value.lower() in n.lower()]
        return choices


class Clock(commands.Cog):
    _GP_KEY = "clockGroup"
    group_clock = app_commands.Group(
        name="clock",
        description="View and compare user's time.",
    )
    group_clock_group = app_commands.Group(
        name="group",
        description="View and manage clock groups.",
        parent=group_clock,
    )

    @classmethod
    async def _save_group(cls, user: AppUser, name: str, ids: list[int]):
        guild_id = user.guild.id if isinstance(user, discord.Member) else 0
        val = [str(i) for i in ids]
        await remote_config.set_json(cls._GP_KEY, user.id, guild_id, name, value=val)

    @classmethod
    async def _get_group(cls, user: AppUser, name: str):
        guild_id = user.guild.id if isinstance(user, discord.Member) else 0
        val: list[str] | None = await remote_config.get_json(cls._GP_KEY, user.id, guild_id, name)  # type: ignore # fmt: skip
        if not val:
            return name
        ids = [int(v) for v in val]
        return ClockGroup(name, ids)

    @classmethod
    async def _list_group(cls, user: AppUser):
        guild_id = user.guild.id if isinstance(user, discord.Member) else 0
        names = await remote_config.get_json_keys(cls._GP_KEY, user.id, guild_id)
        return names

    @classmethod
    async def _delete_group(cls, user: AppUser, name: str):
        guild_id = user.guild.id if isinstance(user, discord.Member) else 0
        return await remote_config.delete_json(cls._GP_KEY, user.id, guild_id, name)

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

    @group_clock_group.command(name="view", description="View clock group.")  # fmt: skip
    @app_commands.describe(
        group="Name of your clock group.",
        show_message="Show message to everyone, this will hide DIFF info and your time zone (if hidden), by default False.",
    )
    async def clock_group_view(
        self,
        interaction: Interaction,
        group: app_commands.Transform[ClockGroup | str, ClockGroupTransformer],
        show_message: bool = False,
    ):
        if not isinstance(group, ClockGroup):
            await interaction.response.send_message(
                embed=fail("Not exist", f"No clock group named `{group}`"),
                ephemeral=True,
            )
            return
        guild_id = interaction.guild_id or 0
        users: list[AppUser] = []
        invalid: list[int] = []
        for i in group.ids:
            u = self.bot.get_user(i)
            if u is None:
                with suppress(discord.NotFound):
                    u = await self.bot.fetch_user(i)
            if u:
                users.append(u)
            else:
                invalid.append(i)
        show = show_message and len(invalid) == 0
        await interaction.response.send_message(
            "The bot is thinking...",
            ephemeral=not show,
        )
        embeds = []
        if len(users) > 0:
            view = ClockCompareView(
                guild_id,
                users,
                interaction.user,
                show_message,
                group.name,
            )
            view.stop()
            msg_data = await view.create_message()
            embeds.append(msg_data["embed"])
        if len(invalid) > 0:
            invalid_embed = fail(
                "Invalid users",
                "\n".join([f"- `{i}`" for i in invalid]),
            )
            embeds.append(invalid_embed)
        await interaction.edit_original_response(content=None, embeds=embeds)

    @group_clock_group.command(name="delete", description="Delete a clock group.")
    @app_commands.describe()
    async def clock_group_delete(
        self,
        interaction: Interaction,
        group: app_commands.Transform[ClockGroup | str, ClockGroupTransformer],
    ):
        if not isinstance(group, ClockGroup):
            await interaction.response.send_message(
                embed=fail("Not exist", f"No clock group named `{group}`"),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self._delete_group(interaction.user, group.name)
            await interaction.followup.send(embed=success("Clock group deleted"))
        except Exception as ex:
            await interaction.followup.send(embed=fail("Error while deleting", ex))


class ClockCompareView(AutoDisableView):
    def __init__(
        self,
        guild_id: int,
        users: list[AppUser],
        base: AppUser,
        show: bool,
        name: str = "",
    ):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.users = users
        self.base = base
        self.show = show
        self.name = name
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
        embed = display.compare_embed(infos, None if self.show else base_tz, self.name)
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

    @ui.button(label="Save as group...")
    async def save_group(self, interaction: Interaction, button):
        modal = ShortTextModal(title="Clock Group", label="Group Name")
        await interaction.response.send_modal(modal)
        await modal.wait()
        name = modal.text.value
        ids = [u.id for u in self.users]
        try:
            await Clock._save_group(interaction.user, name, ids)
            await interaction.followup.send(
                embed=success("Clock group saved"),
                ephemeral=True,
            )
        except Exception as ex:
            await interaction.followup.send(
                embed=fail("Error while saving", ex),
                ephemeral=True,
            )
