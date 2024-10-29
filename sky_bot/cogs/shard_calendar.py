import json
import os
import typing
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks
from discord.utils import format_dt as timestamp

from ..sky_bot import SkyBot
from ..sky_event.shard import ShardInfo, ShardType, get_shard_info
from ..utils import msg_exist_async, sky_time, sky_time_now
from .daily_clock import DailyClock

__all__ = ("ShardCalendar",)


class ShardCalendar(commands.Cog):
    _CONFIG_PATH_ = "extern_config/shard.json"
    _CALENDAR_MSG_ID = "-# ˢʰᵃʳᵈᴱᵛᵉⁿᵗ"

    def __init__(self, bot: SkyBot):
        self.bot = bot
        # 加载外部配置
        self.config = {}
        if os.path.exists(self._CONFIG_PATH_):
            with open(self._CONFIG_PATH_, encoding="utf-8") as f:
                self.config = json.load(f)
        self.calendar_message: discord.Message = None
        # 设置更新时间
        self.set_update_time()
        self.update_calendar_msg.start()
        self.refresh_calendar_state.start()

    async def cog_unload(self):
        self.update_calendar_msg.cancel()

    def _config(self, key):
        # 获取配置项
        val = self.config.get(key, {})
        if self.config == {} and key == "translations":
            val = _default_translation
        return val

    def _date_msg(self, info: ShardInfo):
        # 日期信息
        msg = f"- **__Date__:** {timestamp(info.date, 'D')}"
        return msg

    def _type_msg(self, info: ShardInfo):
        # 碎片类型信息
        msg = f"{info.type.name} Shard"
        # 如果设置了emoji就添加
        emojis = self._config("emojis")
        type_emoji = emojis.get(info.type.name)
        if type_emoji:
            msg = type_emoji + " " + msg
        # 奖励类型及数量
        reward_unit = emojis.get(info.reward_type.name, info.reward_type.name)
        msg += f" ({info.reward_number} {reward_unit})"
        msg = "- **__Type__:** " + msg
        return msg

    def _map_msg(self, info: ShardInfo):
        # 碎片位置信息
        msg = "- **__Map__:** "
        trans = self._config("translations")
        graph = self._config("infographics")
        msg += trans[info.realm] + " || "
        # 给地图名称添加图片链接
        if link := graph.get(".".join([info.realm, info.map])):
            msg += f"[{trans[info.map]}]({link})"
        else:
            msg += trans[info.map]
        return msg

    def _timeline_msg(self, info: ShardInfo, now=None):
        # 时间线信息
        def _occur(land, end):
            time_range = f"{timestamp(land, 'T')} - {timestamp(end, 'T')}"
            if now < land:
                msg = f"-# 🔸 {time_range}, lands {timestamp(land, 'R')}"  # 还未降落
            elif now < end:
                msg = f"-# 🔹 {time_range}, ends {timestamp(end, 'R')}"  # 已经降落
            else:
                msg = f"-# ▪️ ~~{time_range}~~"  # 已经结束
            return msg

        now = now or sky_time_now()
        msg = "- **__Timeline__:**\n"
        # 取降落时间和结束时间为起止时间（忽略开始时间）
        occur_msgs = [_occur(land, end) for start, land, end in info.occurrences]
        msg += "\n".join(occur_msgs)
        return msg

    def _coming_msg(self, info: ShardInfo, days):
        # 接下来几天的碎片类型
        emojis = self._config("emojis")

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

        msg = "- **__The coming days__:**\n"
        days_symbol = [_symbol(info.date + timedelta(days=i + 1)) for i in range(days)]
        msg += " ".join(days_symbol)
        return msg

    def _extra_msg(self, info: ShardInfo):
        # 额外碎片信息
        if not info.extra_shard:
            # 不存在额外碎片就返回空字符串
            return ""
        msg = "- ☄️ **Extra shard day! See Daily Clock.**"
        # 链接到日常事件时刻消息以提供细节
        daily_cog: DailyClock = self.bot.get_cog(DailyClock.__name__)
        if clock_msg := daily_cog.clock_message:
            msg = msg.replace("Daily Clock", f"[Daily Clock](<{clock_msg.jump_url}>)")
        return msg

    def get_shard_event_msg(self, when: datetime, now=None, header=True, footer=True):
        info = get_shard_info(when)
        if info.has_shard:
            # 添加完整碎石事件信息
            msg = "\n".join(
                [
                    m
                    for m in [
                        self._date_msg(info),
                        self._type_msg(info),
                        self._map_msg(info),
                        self._timeline_msg(info, now),
                        self._extra_msg(info),
                        self._coming_msg(info, self._config("coming_days")),
                    ]
                    if m != ""
                ]
            )
        else:
            # 没有碎石事件，只添加后续几天信息
            msg = "## ☀️ **It's a no shard day!**\n"
            msg += self._coming_msg(info, self._config("coming_days"))
        if header:
            msg = "# 🌋 Shard Calendar\n" + msg
        if footer:
            msg = (
                msg
                + "\n\n-# *See [Sky Shards](<https://sky-shards.pages.dev/>) by [Plutoy](<https://github.com/PlutoyDev>) for more.*"
            )
        return msg

    def set_update_time(self):
        # 设置在今天所有碎片的降落和结束时间更新
        now = sky_time_now()
        info = get_shard_info(now)
        times = [t.timetz() for st in info.occurrences for t in st[1:]]
        self.update_calendar_msg.change_interval(time=times)

    @commands.command()
    async def shard(self, ctx: commands.Context, offset: typing.Optional[int] = 0):
        now = sky_time_now()
        when = now + timedelta(days=offset)
        msg = self.get_shard_event_msg(when)
        await ctx.send(msg)

    @tasks.loop()
    async def update_calendar_msg(self):
        # 生成事件信息
        now = sky_time_now()
        shard_event_msg = self.get_shard_event_msg(now)
        shard_event_msg = self._CALENDAR_MSG_ID + "\n" + shard_event_msg
        # 如果已记录消息，则直接更新
        message = self.calendar_message
        if message and await msg_exist_async(message):
            await message.edit(content=shard_event_msg)
            print(f"[{sky_time_now()}] Success editting calendar message.")
            return
        # 查找频道和消息
        channel = self.bot.get_bot_channel()
        message = await self.bot.search_message_async(channel, self._CALENDAR_MSG_ID)
        # 如果消息不存在，则发送新消息；否则编辑现有消息
        if message is None:
            message = await channel.send(shard_event_msg)
            print(f"[{sky_time_now()}] Success sending calendar message.")
        else:
            await message.edit(content=shard_event_msg)
            print(f"[{sky_time_now()}] Success editing calendar message.")
        # 记录消息，下次可以直接使用
        self.calendar_message = message

    @update_calendar_msg.before_loop
    async def setup_update_calendar_msg(self):
        # 等待客户端就绪
        await self.bot.wait_until_ready()
        # 先更新一次
        await self.update_calendar_msg()

    @tasks.loop(time=sky_time(0, 0))
    async def refresh_calendar_state(self):
        # 每天刚开始时刷新一次碎片消息
        self.update_calendar_msg()
        # 然后修改碎片消息的更新时间
        self.set_update_time()
        print(f"[{sky_time_now()}] Calendar state updated.")


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


async def setup(bot: commands.Bot):
    await bot.add_cog(ShardCalendar(bot))
