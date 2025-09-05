import calendar
import json
import re
from datetime import datetime, timedelta
from typing import Any, Literal, TypedDict, cast

import discord
from discord import ButtonStyle, Interaction, app_commands, ui
from discord.ext import commands, tasks
from discord.utils import MISSING
from discord.utils import format_dt as timestamp

from sky_m8 import SkyM8
from utils.remote_config import remote_config

from ..base.live_update import LiveUpdateCog
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

_default_shard_cfg = _ShardCfg(
    coming_days=7,
    emojis={
        "Black": "⚫",
        "Red": "🔴",
        "Wax": "Wax",
        "AC": "AC",
        "Map": "📍",
        "Timeline": "⏳",
        "Next": "⤵️",
        "Memory": "💠",
        "Crystal": "💠",
    },
    infographics={},
    translations={
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
    },
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

        trans = _default_shard_cfg["translations"] | config.get("translations", {})
        config["translations"] = trans

        emoji_mapping = config.get("emojis", {})
        emoji_override = {k: Emojis(str(v), str(v)) for k, v in emoji_mapping.items()}
        emojis = Emojis.emojis | _default_shard_cfg["emojis"] | emoji_override
        config["emojis"] = emojis

        config.setdefault("coming_days", _default_shard_cfg["coming_days"])
        config.setdefault("infographics", _default_shard_cfg["infographics"])

        return config

    def __init__(self, bot: SkyM8):
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
        # 设置在今天所有碎石的降落和结束时间更新
        now = sky_time_now()
        info = get_shard_info(now)
        times = [t.timetz() for st in info.occurrences for t in st[1:]]
        self.update_live_msg.change_interval(time=times)

    async def get_shard_message_data(
        self,
        *,
        date: datetime = MISSING,
        persistent: bool = True,
    ) -> dict[str, Any]:
        date = date or sky_time_now()
        info = get_shard_info(date)
        extra = await self.get_extra_info(date)
        # 实时消息不显示跳转今天按钮，且设置为持久化
        view = ShardView(
            info,
            extra,
            shard_cfg,
            self.bot,
            show_today=not persistent,
            persistent=persistent,
        )
        return {"view": view}

    async def get_live_message_data(self, **kwargs) -> dict[str, Any]:
        return await self.get_shard_message_data(**kwargs)

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
        msg_data = await self.get_shard_message_data(persistent=False)
        await interaction.followup.send(**msg_data)

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
                embed=fail("Out of range", f"Maximum `day` is `{day_range}` for the month."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=private)
        msg_data = await self.get_shard_message_data(date=date, persistent=False)
        await interaction.followup.send(**msg_data)

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
        msg_data = await self.get_shard_message_data(date=date, persistent=False)
        await interaction.followup.send(**msg_data)

    @group_shard.command(name="record", description="Record shards info of a specific date.")  # fmt: skip
    @app_commands.describe(
        memory="Shard memory of the day.",
        day="The day of month (1~31), by default today.",
        month="The month (1~12), by default current month.",
        year="The year (1~9999), by default current year.",
        author="Use this name for credit, optional.",
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
        date = now = sky_time_now()
        day, month, year = day or date.day, month or date.month, year or date.year
        try:
            date = sky_datetime(year, month, day)
        except ValueError:
            # 日期格式错误
            day_range = calendar.monthrange(year, month)[1]
            await interaction.response.send_message(
                embed=fail("Out of range", f"Maximum `day` is `{day_range}` for the month."),
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
        # 如果记录的是今天的回忆，则更新所有live消息
        if date.date() == now.date():
            await self.update_live_msg()

    async def get_ready_for_live(self):
        # 设置更新时间
        self.set_update_time()

    @tasks.loop(time=sky_time(0, 0))
    async def refresh_calendar_state(self):
        # 每天刚开始时刷新一次碎石消息
        await self.update_live_msg()
        # 然后修改碎石消息的更新时间
        self.set_update_time()
        print(f"[{sky_time_now()}] Sky Calendar state updated.")


class ShardView(ui.LayoutView):
    def __init__(
        self,
        info: ShardInfo,
        extra: ShardExtra | None,
        config: _ShardCfg,
        bot: SkyM8,
        *,
        show_today: bool = True,
        persistent: bool = False,
    ) -> None:
        # persistent 除了影响UI是否持久化，还会影响按钮交互的回复方式
        super().__init__(timeout=None if persistent else 840)
        self.info = info
        self.extra = extra
        self.show_today = show_today
        self.persistent = persistent
        self.created_at = sky_time_now()

        container = ui.Container(accent_color=self._color())
        # 标题+跳转到今天的按钮
        if show_today:
            container.add_item(
                ui.Section(
                    ui.TextDisplay(f"-# Shard Calendar - {self._date_field()}"),
                    accessory=self._create_nav_button("today", "Today", config),  # type: ignore
                )
            )
        else:
            container.add_item(ui.TextDisplay(f"-# Shard Calendar - {self._date_field()}"))
        # 碎石事件类型
        container.add_item(ui.TextDisplay(f"## {self._type_field(config)}"))
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large))
        if info.has_shard:
            # 地图+碎石回忆场景，组合起来节省空间
            self._add_map_and_memory_info(container, config)
            # 时间线
            container.add_item(ui.TextDisplay(self._timeline_field(config)))
        # 接下来几天的碎石类型
        container.add_item(ui.TextDisplay(self._coming_field(config)))
        # 地图图片指引
        map_url = config["infographics"].get(
            ".".join([info.realm, info.map]) if info.has_shard else "noshard"
        )
        if map_url:
            container.add_item(ui.MediaGallery(discord.MediaGalleryItem(map_url)))
        # 记录回忆的用户
        self._add_memory_author(container, bot)
        container.add_item(ui.Separator())
        # 导航按钮
        container.add_item(
            ui.ActionRow(
                self._create_nav_button(info.date - timedelta(days=1), "◀", config),  # type: ignore
                self._create_nav_button(info.date + timedelta(days=1), "▶", config),  # type: ignore
            )
        )
        self.add_item(container)

    def _color(self):
        # 边框颜色
        if not self.info.has_shard:
            return discord.Color.from_str("#DAA520")
        elif self.info.type == ShardType.Black:
            return discord.Color.from_str("#6A5ACD")
        else:
            return discord.Color.from_str("#B22222")

    def _date_field(self):
        # 日期信息
        field = timestamp(self.info.date, "D")
        return field

    def _type_field(self, config: _ShardCfg):
        if not self.info.has_shard:
            return "☀️ No Shard Day"
        emojis = config["emojis"]
        # 碎石类型信息
        type_emoji = emojis[self.info.type.name]
        field = f"{type_emoji} {self.info.type.name} Shard"
        # 奖励类型及数量
        reward_unit = emojis[self.info.reward_type.name]
        field += f" [{self.info.reward_number}{reward_unit}]"
        return field

    def _map_field(self, config: _ShardCfg):
        trans = config["translations"]
        emojis = config["emojis"]
        map = trans[self.info.map] + ", " + trans[self.info.realm]
        field = f"**{emojis['Map']} __Map__**\n{emojis['blank']} {map}"
        return field

    def _timeline_field(self, config: _ShardCfg, now=None):
        # 时间线信息
        emojis = config["emojis"]
        pad = emojis["blank"]

        def _occur(land, end):
            lt, et = timestamp(land, "t"), timestamp(end, "t")
            if now < land:
                field = f"-# {pad} {lt} - {et}, lands {timestamp(land, 'R')}"  # 还未降落
            elif now < end:
                field = f"-# {pad} ~~{lt}~~ - {et}, ends {timestamp(end, 'R')}"  # 已经降落
            else:
                field = f"-# {pad} ~~{lt} - {et}~~"  # 已经结束
            return field

        now = now or sky_time_now()
        # 取降落时间和结束时间为起止时间（忽略开始时间）
        occur_msgs = [_occur(land, end) for start, land, end in self.info.occurrences]
        timelines = "\n".join(occur_msgs)
        field = f"**{emojis['Timeline']} __Timeline__**\n{timelines}"
        return field

    def _coming_field(self, config: _ShardCfg):
        # 接下来几天的碎石类型
        emojis = config["emojis"]

        def _symbol(when: datetime):
            _info = get_shard_info(when)
            if _info.has_shard:
                symbol = str(emojis[_info.type.name])
            else:
                symbol = "☀️"
            if when.weekday() == 0:
                symbol = "|| " + symbol
            return symbol

        days = config["coming_days"]
        days_symbol = [_symbol(self.info.date + timedelta(days=i + 1)) for i in range(days)]
        coming = " ".join(days_symbol)
        field = f"**{emojis['Next']} __Coming Days__**\n{emojis['blank']} {coming}"
        return field

    def _add_map_and_memory_info(self, container: ui.Container, config: _ShardCfg):
        text_map = ui.TextDisplay(self._map_field(config))
        container.add_item(text_map)
        if self.info.type == ShardType.Black:
            return
        emojis = config["emojis"]
        title = f"**{emojis['Memory']} __Memory__**"
        if not (self.extra and self.extra.has_memory):
            container.remove_item(text_map)
            container.add_item(
                ui.Section(
                    text_map,
                    ui.TextDisplay(f"{title}\n{emojis['blank']} *Unknown yet*"),
                    accessory=self._create_record_button(self.info.date),  # type: ignore
                )
            )
        else:
            memory = self.extra.memory_type
            memory_url = config["infographics"].get(f"memory.{memory.value}")
            if not memory_url:
                container.add_item(ui.TextDisplay(f"{title}\n{emojis['blank']} {memory.name}"))
            else:
                container.remove_item(text_map)
                container.add_item(
                    ui.Section(
                        text_map,
                        ui.TextDisplay(f"{title}\n{emojis['blank']} {memory.name}"),
                        accessory=ui.Thumbnail(memory_url),
                    )
                )

    def _add_memory_author(self, container: ui.Container, bot: SkyM8):
        if self.extra and self.extra.has_memory:
            author = bot.get_user(self.extra.memory_user)
            if author:
                container.add_item(
                    ui.TextDisplay(
                        f"-# Memory submitted by {self.extra.memory_by.strip() or author.display_name}"
                    )
                )

    def _create_nav_button(self, dt, label, config: _ShardCfg):
        emojis = config["emojis"]
        now = self.created_at
        info = get_shard_info(now if dt == "today" else dt)
        # 当显示日期是今天时，禁用跳转到今天的按钮
        is_today = dt == "today" and self.info.date.date() == now.date()
        if info.has_shard:
            emoji = str(emojis[info.type.name])
        else:
            emoji = "☀️"
        return ShardNavButton(
            date=dt,
            label=label,
            emoji=emoji,
            disabled=is_today,
            send_new=self.persistent,
        )

    def _create_record_button(self, dt: datetime):
        return ShardRecordButton(date=dt, persistent=self.persistent)


class ShardNavButton(
    ui.DynamicItem[ui.Button],
    template=r"shard-nav:(?P<date>[0-9]{8}|today),(?P<send_new>[01])",
):
    def __init__(
        self,
        *,
        date: datetime | Literal["today"],
        label: str | None = None,
        emoji: str | None = None,
        disabled: bool = False,
        send_new: bool = False,
    ):
        date_str = f"{date:%Y%m%d}" if isinstance(date, datetime) else date
        super().__init__(
            ui.Button(
                style=ButtonStyle.primary if date == "today" else ButtonStyle.secondary,
                label=label,
                emoji=emoji,
                disabled=disabled,
                custom_id=f"shard-nav:{date_str},{int(send_new)}",
            ),
        )
        self.date = date
        self.send_new = send_new

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        date_str = match["date"]
        if date_str == "today":
            date = date_str
        else:
            date = datetime.strptime(date_str, "%Y%m%d")
            date = sky_datetime(date.year, date.month, date.day)
        return cls(date=date, send_new=bool(int(match["send_new"])))

    async def callback(self, interaction: Interaction[SkyM8]):  # type: ignore
        await interaction.response.defer()
        if isinstance(self.date, datetime):
            date = self.date
        else:
            date = sky_time_now()
        bot = interaction.client
        cog = cast(ShardCalendar, bot.cogs[ShardCalendar.__cog_name__])
        msg_data = await cog.get_shard_message_data(date=date, persistent=False)
        # 如果是持久化的按钮，则新发送一条消息，否则编辑原消息
        # 目前持久化的按钮在实时更新的消息中使用，其消息由task负责更新，因此不应该在这里编辑
        if self.send_new:
            await interaction.followup.send(**msg_data, ephemeral=True)
        else:
            await interaction.edit_original_response(**msg_data)


class ShardRecordButton(
    ui.DynamicItem[ui.Button],
    template=r"shard-record:(?P<date>[0-9]{8}|today),(?P<persistent>[01])",
):
    def __init__(self, *, date: datetime, persistent: bool):
        super().__init__(
            ui.Button(
                style=ButtonStyle.secondary,
                label="Record",
                emoji="📥",
                custom_id=f"shard-record:{date:%Y%m%d},{int(persistent)}",
            ),
        )
        self.date = date
        self.persistent = persistent

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        date_str = match["date"]
        date = datetime.strptime(date_str, "%Y%m%d")
        date = sky_datetime(date.year, date.month, date.day)
        return cls(date=date, persistent=bool(int(match["persistent"])))

    async def callback(self, interaction: Interaction[SkyM8]):  # type: ignore
        modal = ShardRecordModal(self.date)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.recorded:
            return
        bot = interaction.client
        cog = cast(ShardCalendar, bot.cogs[ShardCalendar.__cog_name__])
        msg_data = await cog.get_shard_message_data(date=self.date, persistent=self.persistent)
        # 更新当前消息
        await interaction.edit_original_response(**msg_data)
        # 如果记录的是今天的回忆，则同时更新所有live消息
        if self.date.date() == sky_time_now().date():
            await cog.update_live_msg()


class ShardRecordModal(ui.Modal, title="Record Shard Info"):
    label_memory = ui.Label(
        text="Memory Scene",
        description="The memory scene you can enter after completing red shard",
        component=ui.Select(
            options=[discord.SelectOption(label=m.name, value=m.name) for m in MemoryType]
        ),
    )
    label_author = ui.Label(
        text="Author (Optional)",
        description="Use this name for credit",
        component=ui.TextInput(required=False),
    )

    def __init__(self, date: datetime):
        super().__init__()
        self.select_memory = cast(ui.Select, self.label_memory.component)
        self.text_author = cast(ui.TextInput, self.label_author.component)

        self.date = date
        self.recorded = False

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer()
        memory = MemoryType[self.select_memory.values[0]]
        author = self.text_author.value
        try:
            extra = ShardExtra(
                has_memory=True,
                memory_type=memory,
                memory_user=interaction.user.id,
                memory_by=author.strip(),
                memory_timestamp=interaction.created_at.timestamp(),
            )
            await ShardCalendar.set_extra_info(self.date, extra)
            self.recorded = True
        except Exception as ex:
            await interaction.followup.send(embed=fail("Error while recording", ex))


async def setup(bot: SkyM8):
    bot.add_dynamic_items(ShardNavButton)
    await bot.add_cog(ShardCalendar(bot))
