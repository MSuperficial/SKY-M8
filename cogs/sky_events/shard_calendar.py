import calendar
import json
import re
from datetime import datetime, timedelta
from typing import Literal, TypedDict

import discord
from discord import ButtonStyle, Interaction, app_commands, ui
from discord.ext import commands, tasks
from discord.utils import MISSING
from discord.utils import format_dt as timestamp

from sky_bot import SkyBot
from utils.remote_config import remote_config

from ..base.live_update import LiveUpdateCog
from ..base.views import AutoDisableView
from ..emoji_manager import Emojis
from ..helper.converters import DayTransformer, MonthTransformer, YearTransformer
from ..helper.embeds import fail, success
from ..helper.times import sky_datetime, sky_time, sky_time_now
from .data.shard import (
    MemoryType,
    ShardExtra,
    ShardInfo,
    ShardType,
    get_shard_info,
)

__all__ = ("ShardCalendar",)


class _ShardCfg(TypedDict):
    coming_days: int
    emojis: dict[str, str | discord.Emoji]
    infographics: dict[str, str]
    translations: dict[str, str]


shard_cfg = _ShardCfg(
    coming_days=7,
    emojis={},
    infographics={},
    translations={},
)


class ShardCalendar(
    LiveUpdateCog,
    live_key="shardCalendar.webhooks",
    group_live_name="shard-live",
    live_display_name="Shard Calendar",
):
    _CONFIG_KEY = "shardCalendar.config"
    group_shard = app_commands.Group(
        name="shard",
        description="A group of commands to view and config shards information.",
    )

    @classmethod
    async def set_extra_info(cls, date: datetime, info: ShardExtra):
        field = f"{date:%Y/%m/%d}"
        await remote_config.set_field("shard.extra", field, info.to_dict())

    @classmethod
    async def get_extra_info(cls, date: datetime):
        field = f"{date:%Y/%m/%d}"
        value = await remote_config.get_field("shard.extra", field)
        if not value:
            return None
        info = ShardExtra.from_dict(json.loads(value))
        return info

    @classmethod
    async def get_config(cls):
        config: _ShardCfg = await remote_config.get_json(cls._CONFIG_KEY)  # type: ignore

        trans = _default_translation | config.get("translations", {})
        config["translations"] = trans

        emoji_mapping: dict[str, str] = config["emojis"]  # type: ignore
        emoji_override = {k: Emojis(v, v) for k, v in emoji_mapping.items()}
        emojis = Emojis.emojis | emoji_override
        config["emojis"] = emojis

        config.setdefault("coming_days", 7)

        return config

    def __init__(self, bot: SkyBot):
        super().__init__(bot)

    async def cog_load(self):
        # 加载配置
        global shard_cfg
        shard_cfg = await self.get_config()
        # 设置更新时间
        self.set_update_time()
        self.refresh_calendar_state.start()
        # 启动任务
        await super().cog_load()

    async def cog_unload(self):
        await super().cog_unload()
        self.refresh_calendar_state.cancel()

    def set_update_time(self):
        # 设置在今天所有碎片的降落和结束时间更新
        now = sky_time_now()
        info = get_shard_info(now)
        times = [t.timetz() for st in info.occurrences for t in st[1:]]
        self.update_live_msg.change_interval(time=times)

    async def get_live_message_data(
        self,
        *,
        date: datetime = MISSING,
        persistent: bool = True,
        **kwargs,
    ):
        date = date or sky_time_now()
        builder = ShardEmbedBuilder(self.bot, shard_cfg)
        info = get_shard_info(date)
        extra = await self.get_extra_info(date)
        embeds = builder.build_embed(info, extra)
        # 实时消息不显示跳转今天按钮，且设置为持久化
        view = ShardNavView(
            date,
            shard_cfg,
            show_today=not persistent,
            persistent=persistent,
        )
        return {
            "embeds": embeds,
            "view": view,
        }

    @commands.is_owner()
    @commands.group(name="shard", invoke_without_command=True)
    async def prefix_shard(self, ctx: commands.Context, *, arg: str):
        await ctx.send(f"No subcommand named `{arg}`")

    @prefix_shard.command(name="config-update")
    async def shard_config_update(self, ctx: commands.Context):
        global shard_cfg
        shard_cfg = await self.get_config()
        await ctx.message.add_reaction(Emojis("success", "✅"))

    @app_commands.command(description="View shards info of today.")
    @app_commands.describe(
        private="Only you can see the message, by default True.",
    )
    async def shards(self, interaction: Interaction, private: bool = True):
        await interaction.response.defer(ephemeral=private)
        msg_data = await self.get_live_message_data(persistent=False)
        msg = await interaction.followup.send(**msg_data)
        view: ShardNavView = msg_data["view"]
        view.response_msg = msg

    @group_shard.command(name="date", description="View shards info of specific date.")
    @app_commands.describe(
        day="The day of month (1~31).",
        month="The month (1~12), by default current month.",
        year="The year (1~9999), by default current year.",
        private="Only you can see the message, by default True.",
    )
    async def shard_date(
        self,
        interaction: Interaction,
        day: app_commands.Transform[int, DayTransformer],
        month: app_commands.Transform[int, MonthTransformer] | None = None,
        year: app_commands.Transform[int, YearTransformer] | None = None,
        private: bool = True,
    ):
        date = sky_time_now()
        month, year = month or date.month, year or date.year
        try:
            date = sky_datetime(year, month, day)
        except ValueError:
            # 日期格式错误
            day_range = calendar.monthrange(year, month)[1]
            await interaction.response.send_message(
                embed=fail(
                    "Out of range", f"Maximum `day` is `{day_range}` for the month."
                ),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=private)
        msg_data = await self.get_live_message_data(date=date, persistent=False)
        msg = await interaction.followup.send(**msg_data)
        view: ShardNavView = msg_data["view"]
        view.response_msg = msg

    @group_shard.command(name="offset", description="View shards info relative to today.")  # fmt: skip
    @app_commands.describe(
        days="How many days to offset, can be negative.",
        private="Only you can see the message, by default True.",
    )
    async def shard_offset(
        self,
        interaction: Interaction,
        days: int,
        private: bool = True,
    ):
        await interaction.response.defer(ephemeral=private)
        now = sky_time_now()
        date = now + timedelta(days=days)
        msg_data = await self.get_live_message_data(date=date, persistent=False)
        msg = await interaction.followup.send(**msg_data)
        view: ShardNavView = msg_data["view"]
        view.response_msg = msg

    @group_shard.command(name="record", description="Record shards info of a specific date.")  # fmt: skip
    @app_commands.describe(
        memory="Shard memory of the day.",
        day="The day of month (1~31), by default today.",
        month="The month (1~12), by default current month.",
        year="The year (1~9999), by default current year.",
        author="Change your name for credit, optional.",
    )
    async def shard_record(
        self,
        interaction: Interaction,
        memory: MemoryType,
        day: app_commands.Transform[int, DayTransformer] | None = None,
        month: app_commands.Transform[int, MonthTransformer] | None = None,
        year: app_commands.Transform[int, YearTransformer] | None = None,
        author: str = "",
    ):
        date = sky_time_now()
        day, month, year = day or date.day, month or date.month, year or date.year
        try:
            date = sky_datetime(year, month, day)
        except ValueError:
            # 日期格式错误
            day_range = calendar.monthrange(year, month)[1]
            await interaction.response.send_message(
                embed=fail(
                    "Out of range", f"Maximum `day` is `{day_range}` for the month."
                ),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        info = get_shard_info(date)
        if not info.has_shard:
            # 当日没有碎石事件
            await interaction.followup.send(embed=fail("It's a no shard day"))
            return
        elif info.type == ShardType.Black:
            # 黑石事件没有回忆场景
            await interaction.followup.send(embed=fail("Black shard has no memory"))
            return
        try:
            extra = ShardExtra(
                has_memory=True,
                memory_type=memory,
                memory_user=interaction.user.id,
                memory_by=author.strip(),
                memory_timestamp=interaction.created_at.timestamp(),
            )
            await self.set_extra_info(date, extra)
            # 成功记录
            await interaction.followup.send(embed=success("Successfully recorded"))
        except Exception as ex:
            # 其他错误
            await interaction.followup.send(embed=fail("Error while recording", ex))
            return
        # 记录回忆后更新所有live消息
        await self.update_live_msg()

    async def get_ready_for_live(self):
        # 设置更新时间
        self.set_update_time()

    @tasks.loop(time=sky_time(0, 0))
    async def refresh_calendar_state(self):
        # 每天刚开始时刷新一次碎片消息
        await self.update_live_msg()
        # 然后修改碎片消息的更新时间
        self.set_update_time()
        print(f"[{sky_time_now()}] Sky Calendar state updated.")


class ShardEmbedBuilder:
    def __init__(self, bot: SkyBot, config: _ShardCfg):
        self.bot = bot
        self.config = config
        self.emojis = config["emojis"]

    def _embed_color(self, info: ShardInfo):
        if info.type == ShardType.Black:
            return discord.Color.from_str("#6A5ACD")
        else:
            return discord.Color.from_str("#B22222")

    def _date_field(self, info: ShardInfo):
        # 日期信息
        field = timestamp(info.date, "D")
        return field

    def _type_field(self, info: ShardInfo):
        # 碎片类型信息
        field = f"{info.type.name} Shard"
        # 如果设置了emoji就添加
        if type_emoji := self.emojis.get(info.type.name):
            field = f"{type_emoji} {field}"
        # 奖励类型及数量
        reward_unit = self.emojis.get(info.reward_type.name, info.reward_type.name)
        field += f" [{info.reward_number}{reward_unit}]"
        return field

    def _map_field(self, info: ShardInfo):
        trans = self.config["translations"]
        field = trans[info.map] + ", " + trans[info.realm]
        return field

    def _timeline_field(self, info: ShardInfo, now=None):
        # 时间线信息
        def _occur(land, end):
            time_range = f"{timestamp(land, 'T')} - {timestamp(end, 'T')}"
            if now < land:
                field = f"-# ▸ {time_range}, lands {timestamp(land, 'R')}"  # 还未降落
            elif now < end:
                time_range = f"~~{timestamp(land, 'T')}~~ - {timestamp(end, 'T')}"
                field = f"-# ▸ {time_range}, ends {timestamp(end, 'R')}"  # 已经降落
            else:
                field = f"-# ▸ ~~{time_range}~~"  # 已经结束
            return field

        now = now or sky_time_now()
        # 取降落时间和结束时间为起止时间（忽略开始时间）
        occur_msgs = [_occur(land, end) for start, land, end in info.occurrences]
        field = "\n".join(occur_msgs)
        return field

    def _coming_field(self, info: ShardInfo, days: int):
        # 接下来几天的碎片类型
        def _symbol(when: datetime):
            _info = get_shard_info(when)
            if _info.has_shard:
                default = {ShardType.Black: "⚫", ShardType.Red: "🔴"}
                symbol = str(self.emojis.get(_info.type.name, default[_info.type]))
            else:
                symbol = "☀️"
            if when.weekday() == 0:
                symbol = "|| " + symbol
            return symbol

        days_symbol = [_symbol(info.date + timedelta(days=i + 1)) for i in range(days)]
        field = " ".join(days_symbol)
        return field

    def build_embed(self, info: ShardInfo, extra: ShardExtra | None, now=None):
        embeds: list[discord.Embed] = []
        graph = self.config["infographics"]
        if info.has_shard:
            basic_embed = (
                discord.Embed(
                    color=self._embed_color(info),
                    description=f"-# Shard Calendar - {self._date_field(info)}\n## {self._type_field(info)}",
                )
                .add_field(
                    name=f"{self.emojis.get('Map', '📍')} __Map__",
                    value=self._map_field(info),
                    inline=True,
                )
                .add_field(
                    name=f"{self.emojis.get('Timeline', '⏳')} __Timeline__",
                    value=self._timeline_field(info, now),
                    inline=False,
                )
                .add_field(
                    name=f"{self.emojis.get('Next', '⤵️')} __Coming days__",
                    value=self._coming_field(info, self.config["coming_days"]),
                    inline=False,
                )
                .set_image(url=graph.get(".".join([info.realm, info.map])))
            )
            embeds.append(basic_embed)
            self._add_memory_info(embeds, info, extra)
        else:
            basic_embed = (
                discord.Embed(
                    color=discord.Color.from_str("#DAA520"),
                    description=f"-# Shard Calendar - {timestamp(info.date, 'D')}\n## ☀️ No Shard Day",
                )
                .add_field(
                    name=f"{self.emojis.get('Next', '⤵️')} __Coming days__",
                    value=self._coming_field(info, self.config["coming_days"]),
                )
                .set_image(url=graph.get("noshard"))
            )
            embeds.append(basic_embed)
        return embeds

    def _add_memory_info(
        self,
        embeds: list[discord.Embed],
        info: ShardInfo,
        extra: ShardExtra | None,
    ):
        if info.type != ShardType.Red:
            return
        graph = self.config["infographics"]
        title = f"{self.emojis.get('Memory', '💠')} __Memory__"
        # 显示Shard Memory信息
        if not (extra and extra.has_memory):
            embeds[0].insert_field_at(1, name=title, value="*Unknown yet*", inline=True)
        else:
            memory = extra.memory_type
            embeds[0].insert_field_at(1, name=title, value=memory.name, inline=True)
            # 显示Shard Memory图片
            memory_embed = discord.Embed(
                color=self._embed_color(info),
                title=f"{self.emojis.get('Crystal', '💠')} Shard Memory [{memory.name}]",
            ).set_image(
                url=graph.get(f"memory.{memory.value}"),
            )
            # 展示提交者信息
            author = self.bot.get_user(extra.memory_user)
            if author:
                memory_embed.set_footer(
                    text=f"Submitted by {extra.memory_by.strip() or author.display_name}",
                    icon_url=author.display_avatar.url,
                )
                memory_embed.timestamp = datetime.fromtimestamp(extra.memory_timestamp)
            embeds.append(memory_embed)


class ShardNavView(AutoDisableView):
    def __init__(
        self,
        date: datetime,
        config: _ShardCfg,
        *,
        show_today: bool = True,
        persistent: bool = False,
    ):
        # persistent 除了影响UI是否持久化，还会影响按钮交互的回复方式
        super().__init__(timeout=None if persistent else 600)
        emojis = config["emojis"]
        now = sky_time_now()

        def add_button(dt, label):
            info = get_shard_info(now if dt == "today" else dt)
            # 如果是今天的按钮，且当前显示日期也为今天，则禁用
            is_today = dt == "today" and now.date() == date.date()
            if info.has_shard:
                default = {ShardType.Black: "⚫", ShardType.Red: "🔴"}
                emoji = str(emojis.get(info.type.name, default[info.type]))
            else:
                emoji = "☀️"
            self.add_item(
                ShardNavButton(
                    date=dt,
                    label=label,
                    emoji=emoji,
                    disabled=is_today,
                    persistent=persistent,
                )
            )

        # 分别添加前一天、跳转到今天、后一天的按钮
        add_button(date - timedelta(days=1), "◀")
        if show_today:
            add_button("today", "Today")
        add_button(date + timedelta(days=1), "▶")


class ShardNavButton(
    ui.DynamicItem[ui.Button],
    template=r"shard-nav:(?P<date>[0-9]{8}|today),(?P<persistent>[01])",
):
    def __init__(
        self,
        *,
        date: datetime | Literal["today"],
        label: str | None = None,
        emoji: str | None = None,
        disabled: bool = False,
        persistent: bool = False,
    ):
        date_str = f"{date:%Y%m%d}" if isinstance(date, datetime) else date
        super().__init__(
            ui.Button(
                style=ButtonStyle.primary if date == "today" else ButtonStyle.secondary,
                label=label,
                emoji=emoji,
                disabled=disabled,
                custom_id=f"shard-nav:{date_str},{int(persistent)}",
            ),
        )
        self.date = date
        self.persistent = persistent

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        date_str = match["date"]
        if date_str == "today":
            date = date_str
        else:
            date = datetime.strptime(date_str, "%Y%m%d")
            date = sky_datetime(date.year, date.month, date.day)
        return cls(date=date, persistent=bool(int(match["persistent"])))

    async def callback(self, interaction: Interaction):
        await interaction.response.defer()
        if isinstance(self.date, datetime):
            date = self.date
        else:
            date = sky_time_now()
        builder = ShardEmbedBuilder(interaction.client, shard_cfg)  # type: ignore
        info = get_shard_info(date)
        extra = await ShardCalendar.get_extra_info(date)
        embeds = builder.build_embed(info, extra)
        view = ShardNavView(date, shard_cfg)
        # 如果是持久化的按钮，则新发送一条消息，否则编辑原消息
        # 目前持久化的按钮在实时更新的消息中使用，其消息由task负责更新，因此不应该在这里编辑
        if self.persistent:
            msg = await interaction.followup.send(
                embeds=embeds,
                view=view,
                ephemeral=True,
            )
            view.response_msg = msg
        else:
            await interaction.edit_original_response(embeds=embeds, view=view)


_default_translation = {
    "prairie": "Daylight Prairie",
    "forest": "Hidden Forest",
    "valley": "Valley of Triumph",
    "wasteland": "Golden Wasteland",
    "vault": "Vault of Knowledge",
    "village": "Village Islands",
    "butterfly": "Butterfly Fields",
    "cave": "Prairie Cave",
    "bird": "Bird Nest",
    "sanctuary": "Sanctuary Islands",
    "boneyard": "Boneyard",
    "brook": "Forest Brook",
    "end": "Forest End",
    "treehouse": "Assembly Treehouse",
    "granny": "Elevated Clearing",
    "rink": "Ice Rink",
    "dreams": "Village of Dreams",
    "hermit": "Hermit Valley",
    "battlefield": "Battlefield",
    "temple": "Broken Temple",
    "graveyard": "Graveyard",
    "crab": "Crab Fields",
    "ark": "Forgotten Ark",
    "starlight": "Starlight Desert",
    "jellyfish": "Jellyfish Cove",
}


async def setup(bot: SkyBot):
    bot.add_dynamic_items(ShardNavButton)
    await bot.add_cog(ShardCalendar(bot))
