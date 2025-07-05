import re
from datetime import datetime
from typing import Callable, TypedDict, Union

import discord
from discord import Guild, Interaction, Member, User
from discord.utils import get

from sky_m8 import SkyM8
from utils.remote_config import remote_config

from .formats import ordinal, timestamp

__all__ = (
    "VarContext",
    "VarParser",
)


InteractionChannel = Union[
    discord.VoiceChannel,
    discord.StageChannel,
    discord.TextChannel,
    discord.ForumChannel,
    discord.CategoryChannel,
    discord.Thread,
    discord.DMChannel,
    discord.GroupChannel,
]


class VarContext:
    def __init__(
        self,
        *,
        bot: SkyM8,
        guild: Guild | None = None,
        channel: InteractionChannel | None = None,
        user: User | Member | None = None,
    ):
        self.bot = bot
        self.guild = guild
        self.channel = channel
        self.user = user

    @property
    def member(self):
        return self.user if isinstance(self.user, Member) else None

    @classmethod
    def from_interaction(
        cls, interaction: Interaction, *, user: User | Member | None = None
    ):
        return cls(
            bot=interaction.client,  # type: ignore
            guild=interaction.guild,
            channel=interaction.channel,
            user=user or interaction.user,
        )

    @classmethod
    def from_member_join(cls, bot: SkyM8, member: Member):
        return cls(
            bot=bot,
            guild=member.guild,
            channel=member.guild.system_channel,
            user=member,
        )


def _member_pos(member: Member):
    # 筛选掉bot用户
    members = [m for m in member.guild.members if not m.bot]
    # 按加入时间排序
    members = sorted(members, key=lambda m: m.joined_at or datetime.max)
    pos = members.index(member) + 1
    return pos


def _member_count(guild: Guild):
    # 筛选掉bot用户
    members = [m for m in guild.members if not m.bot]
    return len(members)


def _id(value: str):
    try:
        return int(value)
    except ValueError:
        return None


def _user(context: VarContext, match: re.Match[str]):
    if not (value := match["value"]):
        return None
    user = None
    if id := _id(value):
        user = context.bot.get_user(id)
    if not user and context.guild:
        user = context.guild.get_member_named(value)
    return user and user.mention


def _role(context: VarContext, match: re.Match[str]):
    if not context.guild:
        return None
    if not (value := match["value"]):
        return None
    role = None
    if id := _id(value):
        role = context.guild.get_role(id)
    if not role:
        role = get(context.guild.roles, name=value)
    return role and role.mention


def _channel(context: VarContext, match: re.Match[str]):
    if not (value := match["value"]):
        return None
    channel = None
    if id := _id(value):
        channel = context.bot.get_channel(id)
    if not channel and context.guild:
        channel = get(context.guild.channels, name=value)
    return channel and channel.mention  # type: ignore


class VarParser:
    _PARSER: dict[str, Callable[[VarContext, re.Match[str]], str | None]] = {
        "user.name":          lambda c, _: c.user and c.user.display_name,
        "user.avatar":        lambda c, _: c.user and c.user.display_avatar.url,
        "user.mention":       lambda c, _: c.user and c.user.mention,
        "member.position":    lambda c, _: c.member and str(_member_pos(c.member)),
        "member.ordinal":     lambda c, _: c.member and ordinal(_member_pos(c.member)),
        "member.joinedAt":    lambda c, r: c.member and timestamp(c.member.joined_at, r["style"]),  # type: ignore
        "server.name":        lambda c, _: c.guild and c.guild.name,
        "server.icon":        lambda c, _: c.guild and getattr(c.guild.icon, "url", None),
        "server.banner":      lambda c, _: c.guild and getattr(c.guild.banner, "url", None),
        "server.description": lambda c, _: c.guild and c.guild.description,
        "server.memberCount": lambda c, _: c.guild and str(_member_count(c.guild)),
        "randomImage":        lambda c, _: f"https://picsum.photos/seed/{datetime.now().timestamp()}/640/360",
        "now":                lambda c, r: timestamp(datetime.now(), r["style"]),
        "@": _user,
        "&": _role,
        "#": _channel,
    }  # fmt: skip

    @classmethod
    async def get_help(cls):
        data: _ParserCfg = await remote_config.get_json("variableParser")  # type: ignore
        if not data:
            return ""
        vars = data["variables"]
        vars = [f"-# - `{v['name']}` - {v['description']}" for v in vars]
        vars = "\n".join(vars)
        title = "## " + data["help"]["title"]
        help = "\n".join([title, data["help"]["content"], vars, data["help"]["ps"]])
        return help

    @classmethod
    def from_interaction(
        cls, interaction: Interaction, *, user: User | Member | None = None
    ):
        return cls(VarContext.from_interaction(interaction, user=user))

    @classmethod
    def from_member_join(cls, bot: SkyM8, member: Member):
        return cls(VarContext.from_member_join(bot, member))

    def __init__(self, context: VarContext):
        self.context = context

    def parse(self, text: str):
        def _parse(match: re.Match[str]):
            result = None
            key = match["key"]
            if key in self._PARSER:
                try:
                    result = self._PARSER[key](self.context, match)
                except Exception as ex:
                    print(f"Error when parsing {key}: {ex}")
            return result or match[0]

        pattern = r"\{(?P<key>@|&|#|[_\w\.]+)(?P<value>.*?)(?::(?P<style>\w))?\}"
        return re.sub(pattern, _parse, text)


class _ParserCfg(TypedDict):
    help: dict[str, str]
    variables: list[dict[str, str]]
