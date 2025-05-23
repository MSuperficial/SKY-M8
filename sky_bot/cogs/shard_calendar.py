import json
import os
import re
from datetime import datetime, timedelta
from typing import Literal

import discord
from discord import ButtonStyle, Interaction, app_commands, ui
from discord.ext import commands, tasks
from discord.utils import MISSING
from discord.utils import format_dt as timestamp

from ..embed_template import fail, success
from ..remote_config import remote_config
from ..sky_bot import SkyBot
from ..sky_event.shard import (
    MemoryType,
    ShardExtra,
    ShardInfo,
    ShardType,
    get_shard_info,
)
from ..utils import code_block, msg_exist_async, sky_datetime, sky_time, sky_time_now
from ._helper import DateTransformer, date_autocomplete
from .daily_clock import DailyClock

__all__ = ("ShardCalendar",)


_CONFIG_PATH_ = "extern_config/shard.json"
_shard_config = {}


def _reload_shard_config():
    # 加载外部配置
    global _shard_config
    if os.path.exists(_CONFIG_PATH_):
        with open(_CONFIG_PATH_, encoding="utf-8") as f:
            _shard_config = json.load(f)
    else:
        _shard_config = {}


def _config(key):
    # 获取配置项
    val = _shard_config.get(key, {})
    if _shard_config == {} and key == "translations":
        val = _default_translation
    return val


def shard_extra_key(date: datetime):
    return f"shard.extra.{date:%Y%m%d}"


class ShardCalendar(commands.Cog):
    _CALENDAR_MSG_ID = "-# ˢʰᵃʳᵈᴱᵛᵉⁿᵗ"
    group_shard = app_commands.Group(
        name="shard",
        description="A group of commands to view and config shards information.",
    )

    def __init__(self, bot: SkyBot):
        self.bot = bot
        self.calendar_message: discord.Message = MISSING
        # 设置更新时间
        self.set_update_time()
        self.update_calendar_msg.start()
        self.refresh_calendar_state.start()

    async def cog_unload(self):
        self.update_calendar_msg.cancel()

    def set_update_time(self):
        # 设置在今天所有碎片的降落和结束时间更新
        now = sky_time_now()
        info = get_shard_info(now)
        times = [t.timetz() for st in info.occurrences for t in st[1:]]
        self.update_calendar_msg.change_interval(time=times)

    @app_commands.command(description="View shards info of today.")
    @app_commands.describe(
        private="Only you can see the message, by default True.",
    )
    async def shards(self, interaction: Interaction, private: bool = True):
        await interaction.response.defer(ephemeral=private, thinking=True)
        date = sky_time_now()
        builder = ShardEmbedBuilder(self.bot)
        embeds = await builder.build_embed(date)
        view = ShardNavView(date)
        await interaction.followup.send(embeds=embeds, view=view, ephemeral=private)

    @group_shard.command(name="date", description="View shards info of specific date.")
    @app_commands.describe(
        date="Date to view in Year/Month/Day format.",
        private="Only you can see the message, by default True.",
    )
    @app_commands.autocomplete(date=date_autocomplete)
    async def shard_date(
        self,
        interaction: Interaction,
        date: app_commands.Transform[datetime, DateTransformer],
        private: bool = True,
    ):
        await interaction.response.defer(ephemeral=private, thinking=True)
        # 日期格式错误
        if not date:
            await interaction.followup.send(
                embed=await fail("Date format error"),
                ephemeral=private,
            )
            return
        builder = ShardEmbedBuilder(self.bot)
        embeds = await builder.build_embed(date)
        view = ShardNavView(date)
        await interaction.followup.send(embeds=embeds, view=view, ephemeral=private)

    @group_shard.command(
        name="offset", description="View shards info relative to today."
    )
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
        await interaction.response.defer(ephemeral=private, thinking=True)
        now = sky_time_now()
        date = now + timedelta(days=days)
        builder = ShardEmbedBuilder(self.bot)
        embeds = await builder.build_embed(date)
        view = ShardNavView(date)
        await interaction.followup.send(embeds=embeds, view=view, ephemeral=private)

    @group_shard.command(
        name="record", description="Record shards info of a specific date."
    )
    @app_commands.describe(
        memory="Shard memory of the day.",
        author="Change your name for credit, optional.",
        date="Date to record in Year/Month/Day format, by default today.",
    )
    @app_commands.autocomplete(date=date_autocomplete)
    async def shard_record(
        self,
        interaction: Interaction,
        memory: MemoryType,
        author: str = "",
        date: str = "",
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        tsfm = DateTransformer()
        date_ = await tsfm.transform(interaction, date)
        # 日期格式错误
        if not date_:
            await interaction.followup.send(
                embed=await fail("Date format error"),
                ephemeral=True,
            )
            return
        info = get_shard_info(date_)
        if not info.has_shard:
            # 当日没有碎石事件
            await interaction.followup.send(
                embed=await fail("It's a no shard day"),
                ephemeral=True,
            )
            return
        elif info.type == ShardType.Black:
            # 黑石事件没有回忆场景
            await interaction.followup.send(
                embed=await fail("Black shard doesn't have shard memory"),
                ephemeral=True,
            )
            return
        try:
            await remote_config.set_obj(
                shard_extra_key(date_),
                ShardExtra(
                    has_memory=True,
                    memory_type=memory,
                    memory_user=interaction.user.id,
                    memory_by=author.strip(),
                    memory_timestamp=interaction.created_at.timestamp(),
                ),
            )
            # 成功记录
            await interaction.followup.send(
                embed=await success("Successfully recorded"),
                ephemeral=True,
            )
        except Exception as e:
            # 其他错误
            await interaction.followup.send(
                embed=await fail("Error while recording", description=str(e)),
                ephemeral=True,
            )
            return
        await self.update_calendar_msg()

    @tasks.loop()
    async def update_calendar_msg(self):
        # 生成事件信息
        now = sky_time_now()
        builder = ShardEmbedBuilder(self.bot)
        embeds = await builder.build_embed(now)
        # 实时消息不显示跳转今天按钮，且设置为持久化
        view = ShardNavView(now, show_today=False, persistent=True)
        # 如果已记录消息，则直接更新
        message = self.calendar_message
        if message and await msg_exist_async(message):
            await message.edit(content=self._CALENDAR_MSG_ID, embeds=embeds, view=view)
            print(f"[{sky_time_now()}] Success editing calendar message.")
            return
        # 查找频道和消息
        channel: discord.TextChannel = self.bot.get_bot_channel()  # type: ignore
        message = await self.bot.search_message_async(channel, self._CALENDAR_MSG_ID)
        # 如果消息不存在，则发送新消息；否则编辑现有消息
        if message is None:
            message = await channel.send(
                content=self._CALENDAR_MSG_ID, embeds=embeds, view=view
            )
            print(f"[{sky_time_now()}] Success sending calendar message.")
        else:
            await message.edit(content=self._CALENDAR_MSG_ID, embeds=embeds, view=view)
            print(f"[{sky_time_now()}] Success editing calendar message.")
        # 记录消息，下次可以直接使用
        self.calendar_message = message

    @update_calendar_msg.before_loop
    async def setup_update_calendar_msg(self):
        # 设置更新时间
        self.set_update_time()
        # 等待客户端就绪
        await self.bot.wait_until_ready()
        # 先更新一次
        await self.update_calendar_msg()

    @update_calendar_msg.error
    async def calendar_error(self, error):
        task_name = self.update_calendar_msg.coro.__name__
        error_msg = (
            f"Error during task `{task_name}`: `{type(error).__name__}`\n"
            f"{code_block(error)}"
        )
        print(error_msg)
        await self.bot.owner.send(error_msg)

    @tasks.loop(time=sky_time(0, 0))
    async def refresh_calendar_state(self):
        # 每天刚开始时刷新一次碎片消息
        await self.update_calendar_msg()
        # 然后修改碎片消息的更新时间
        self.set_update_time()
        print(f"[{sky_time_now()}] Calendar state updated.")


class ShardEmbedBuilder:
    def __init__(self, bot: SkyBot):
        self.bot = bot
        _reload_shard_config()

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
        emojis = _config("emojis")
        type_emoji = emojis.get(info.type.name)
        if type_emoji:
            field = type_emoji + " " + field
        # 奖励类型及数量
        reward_unit = emojis.get(info.reward_type.name, info.reward_type.name)
        field += f" [{info.reward_number}{reward_unit}]"
        return field

    def _map_field(self, info: ShardInfo):
        trans = _config("translations")
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

    def _coming_field(self, info: ShardInfo, days):
        # 接下来几天的碎片类型
        emojis = _config("emojis")

        def _symbol(when: datetime):
            _info = get_shard_info(when)
            if _info.has_shard:
                symbol = emojis.get(_info.type.name) or (
                    "⚫" if _info.type == ShardType.Black else "🔴"
                )
            else:
                symbol = "☀️"
            if when.weekday() == 0:
                symbol = "|| " + symbol
            return symbol

        days_symbol = [_symbol(info.date + timedelta(days=i + 1)) for i in range(days)]
        field = " ".join(days_symbol)
        return field

    def _extra_msg(self, info: ShardInfo):
        # 额外碎片信息
        if not info.extra_shard:
            # 不存在额外碎片就返回空字符串
            return ""
        msg = "- ☄️ **Extra shard day! See Daily Clock.**"
        # 链接到日常事件时刻消息以提供细节
        daily_cog: DailyClock = self.bot.get_cog(DailyClock.__name__)  # type: ignore
        if clock_msg := daily_cog.clock_message:
            msg = msg.replace("Daily Clock", f"[Daily Clock](<{clock_msg.jump_url}>)")
        return msg

    async def build_embed(self, date: datetime, now=None):
        embeds: list[discord.Embed] = []
        info = get_shard_info(date)
        emojis = _config("emojis")
        graph = _config("infographics")
        if info.has_shard:
            basic_embed = (
                discord.Embed(
                    color=self._embed_color(info),
                    description=f"-# Shard Calendar - {self._date_field(info)}\n## {self._type_field(info)}",
                )
                .add_field(
                    name=emojis.get("Map", "📍") + " " + "__Map__",
                    value=self._map_field(info),
                    inline=True,
                )
                .add_field(
                    name=emojis.get("Timeline", "⏳") + " " + "__Timeline__",
                    value=self._timeline_field(info, now),
                    inline=False,
                )
                .add_field(
                    name=emojis.get("Next", "⤵️") + " " + "__Coming days__",
                    value=self._coming_field(info, _config("coming_days")),
                    inline=False,
                )
                .set_image(url=graph.get(".".join([info.realm, info.map])))
            )
            embeds.append(basic_embed)
            extra_key = shard_extra_key(date)
            await self._add_memory_info(embeds, info, extra_key)
        else:
            basic_embed = (
                discord.Embed(
                    color=discord.Color.from_str("#DAA520"),
                    description=f"-# Shard Calendar - {timestamp(info.date, 'D')}\n## ☀️ No Shard Day",
                )
                .add_field(
                    name=emojis.get("Next", "⤵️") + " " + "__Coming days__",
                    value=self._coming_field(info, _config("coming_days")),
                )
                .set_image(url=graph.get("noshard"))
            )
            embeds.append(basic_embed)
        return embeds

    async def _add_memory_info(self, embeds: list[discord.Embed], info: ShardInfo, key):
        emojis = _config("emojis")
        graph = _config("infographics")
        basic_embed = embeds[0]
        if info.type == ShardType.Red:
            # 显示Shard Memory信息
            extra = await remote_config.get_obj(ShardExtra, key)
            memory_available = extra and extra.has_memory
            memory_name = (
                extra.memory_type.name if memory_available else "*Unknown yet*"
            )
            basic_embed.insert_field_at(
                1,
                name=emojis.get("Memory", "💠") + " " + "__Memory__",
                value=memory_name,
                inline=True,
            )
            # 显示Shard Memory图片
            if memory_available:
                memory_embed = discord.Embed(
                    color=self._embed_color(info),
                    title=f"{emojis.get('Crystal', '💠')} Shard Memory [{memory_name}]",
                ).set_image(url=graph.get(f"memory.{extra.memory_type.value}"))
                # 展示提交者信息
                author = self.bot.get_user(extra.memory_user)
                if author:
                    memory_embed.set_footer(
                        text=f"Submitted by {extra.memory_by.strip() or author.display_name}",
                        icon_url=author.display_avatar.url,
                    )
                    memory_embed.timestamp = datetime.fromtimestamp(
                        extra.memory_timestamp
                    )
                embeds.append(memory_embed)


class ShardNavView(ui.View):
    def __init__(
        self, date: datetime, *, show_today: bool = True, persistent: bool = False
    ):
        # persistent 除了影响UI是否持久化，还会影响按钮交互的回复方式
        super().__init__(timeout=None if persistent else 900)
        _reload_shard_config()
        emojis = _config("emojis")
        now = sky_time_now()

        def add_button(dt, label):
            info = get_shard_info(now if dt == "today" else dt)
            # 如果是今天的按钮，且当前显示日期也为今天，则禁用
            is_today = dt == "today" and now.date() == date.date()
            if info.has_shard:
                emoji = emojis.get(info.type.name)
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
        builder = ShardEmbedBuilder(interaction.client)  # type: ignore
        embeds = await builder.build_embed(date)
        view = ShardNavView(date)
        # 如果是持久化的按钮，则新发送一条消息，否则编辑原消息
        # 目前持久化的按钮在实时更新的消息中使用，其消息由task负责更新，因此不应该在这里编辑
        if self.persistent:
            await interaction.followup.send(embeds=embeds, view=view, ephemeral=True)
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
