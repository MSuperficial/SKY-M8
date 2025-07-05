from datetime import datetime, timedelta
from typing import Sequence
from zoneinfo import ZoneInfo

import discord

from sky_m8 import AppUser

from ..helper import formats, tzutils


class TimezoneDisplay:
    def _fields(self, dt: datetime, base: datetime | None):
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

        if base is not None:
            diff_content = formats.tzdiff(base, dt)
            fields["Difference With Me"] = diff_content

        return fields

    def embed(self, user: AppUser, tz: ZoneInfo, base_tz: ZoneInfo | None = None):
        embed = discord.Embed(
            color=discord.Color.teal(),
        ).set_author(
            name=user.display_name,
            icon_url=user.display_avatar.url,
        )
        now = datetime.now(tz)
        base_dt = base_tz and now.astimezone(base_tz)
        fields = self._fields(now, base_dt)
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

    def compare_embed(
        self,
        users: Sequence[tuple[AppUser, ZoneInfo | None]],
        base_tz: ZoneInfo | None = None,
        name: str = "",
    ):
        embed = discord.Embed(
            color=discord.Color.teal(),
            title="Compare local times",
        ).set_footer(text=name)
        now = datetime.now(ZoneInfo("UTC"))

        def _key(u: tuple[AppUser, ZoneInfo | None]):
            if u[1] is None:
                return timedelta(days=1)
            k = u[1].utcoffset(now)
            return k if k is not None else timedelta(days=1)

        desc = ""
        base_dt = base_tz and now.astimezone(base_tz)
        # 按 UTC Offset 升序排序，未提供时区的排最后
        users = sorted(users, key=_key)
        for user, tzinfo in users:
            if tzinfo is None:
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
