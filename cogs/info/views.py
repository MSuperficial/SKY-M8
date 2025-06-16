from datetime import datetime
from typing import Sequence, TypeAlias
from zoneinfo import ZoneInfo

import discord

from ..helper import formats, tzutils


class TimezoneDisplay:
    User: TypeAlias = discord.User | discord.Member

    def _fields(self, dt: datetime):
        fields = {}

        tz: ZoneInfo = dt.tzinfo  # type: ignore
        tz_content = f"{tz.key}"
        if c := tzutils.timezone_country.get(tz.key):
            tz_content += f", {c}"
        fields["Time Zone"] = tz_content

        utc_content = formats.utcoffset(dt)
        fields["UTC Offset"] = utc_content

        time_content = formats.dt_full(dt)
        fields["Local Time"] = time_content

        return fields

    def embed(self, user: User, tz: ZoneInfo):
        embed = discord.Embed(
            color=discord.Color.teal(),
        ).set_author(
            name=user.display_name,
            icon_url=user.display_avatar.url,
        )
        now = datetime.now(tz)
        fields = self._fields(now)
        for k in fields:
            embed.add_field(name=k, value=f"`{fields[k]}`", inline=False)
        return embed

    def _diff_fields(self, base: datetime, other: datetime):
        fields = self._fields(other)

        diff_content = formats.tzdiff(base, other)
        fields["Difference With Me"] = diff_content

        return fields

    def diff_embed(
        self,
        base: User,
        base_tz: ZoneInfo,
        other: User,
        other_tz: ZoneInfo,
    ):
        embed = discord.Embed(
            color=discord.Color.teal(),
        ).set_author(
            name=other.display_name,
            icon_url=other.display_avatar.url,
        )
        base_dt = datetime.now(base_tz)
        other_dt = base_dt.astimezone(other_tz)
        fields = self._diff_fields(base_dt, other_dt)
        for k in fields:
            embed.add_field(name=k, value=f"`{fields[k]}`", inline=False)
        return embed

    def _cmp_fields(self, curr: datetime, base: datetime | None = None):
        fields = {}

        time_content = formats.dt_short(curr)
        time_content += " " + formats.utcoffset(curr)
        if base:
            time_content += ", DIFF" + formats.tzdiff(base, curr)
        fields["Local Time"] = time_content

        tz: ZoneInfo = curr.tzinfo  # type: ignore
        tz_content = f"{tz.key}"
        if c := tzutils.timezone_country.get(tz.key):
            tz_content += f", {c}"
        fields["Time Zone"] = tz_content

        return fields

    def compare_embed(self, users: Sequence[tuple[User, ZoneInfo | None]]):
        base, base_tz = users[0]
        embed = discord.Embed(
            color=discord.Color.teal(),
        ).set_author(
            name=base.display_name,
            icon_url=base.display_avatar.url,
        )
        now = datetime.now(ZoneInfo("UTC"))
        base_dt = now.astimezone(base_tz)
        fields = self._cmp_fields(base_dt)
        desc = f"`{fields['Local Time']}`\n`{fields['Time Zone']}`"
        for user, tzinfo in users[1:]:
            if not tzinfo:
                desc += f"\n### {user.mention}\n*Time zone not provided!*"
                continue
            dt = now.astimezone(tzinfo)
            fields = self._cmp_fields(dt, base_dt)
            desc += (
                f"\n### {user.mention}\n"
                f"`{fields['Local Time']}`\n"
                f"`{fields['Time Zone']}`"
            )
        embed.description = desc
        return embed
