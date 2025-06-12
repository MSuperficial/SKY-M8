import calendar
import re
from datetime import datetime

import pytz
from discord import Interaction, app_commands
from discord.app_commands import Choice
from discord.ext import commands
from thefuzz import process
from thefuzz.utils import full_process

from ...utils import sky_datetime, sky_time_now

__all__ = (
    "MessageTransformer",
    "DateTransformer",
    "date_autocomplete",
    "match_timezones",
    "tz_autocomplete",
)


class MessageTransformer(app_commands.Transformer):
    async def transform(self, interaction: Interaction, value: str):
        converter = commands.MessageConverter()
        try:
            message = await converter.convert(
                await commands.Context.from_interaction(interaction), value
            )
            return message
        except commands.BadArgument:
            return None


class DateTransformer(app_commands.Transformer):
    async def transform(self, interaction: Interaction, value: str):
        if not value:
            return sky_time_now()
        try:
            date = datetime.strptime(value, "%Y/%m/%d")
            date = sky_datetime(date.year, date.month, date.day)
            return date
        except Exception:
            return None


async def date_autocomplete(interaction: Interaction, value: str):
    def is_int(s: str):
        try:
            _ = int(s)
            return True
        except ValueError:
            return False

    value = value.strip()
    results = []
    if not value:
        # 空字符串
        now = datetime.now()
        # 先从今年到2022，再从明年往后直到填满25个
        years = list(range(now.year, 2021, -1))
        years.extend([y + now.year + 1 for y in range(25 - len(years))])
        results = [str(y) + "/" for y in years]
    elif value.endswith("/") and is_int(value[:-1]):
        # year/
        months = list(range(1, 13))
        results = [value + str(m) + "/" for m in months]
    elif match := re.match(r"([0-9]+)/([0-9]{1,2})/$", value):
        # year/month/
        y, m = [int(g) for g in match.groups()]
        if 1 <= m and m <= 12:
            days = list(range(1, 10))
            results = [value + str(d) for d in days]
    elif match := re.match(r"([0-9]+)/([0-9]{1,2})/([1-3])$", value):
        # year/month/day
        y, m, d = [int(g) for g in match.groups()]
        if 1 <= m and m <= 12:
            day_range = calendar.monthrange(y, m)[1]
            days = range(1, day_range + 1)
            days = [d_ for d_ in days if d_ // 10 == d]
            results = [value[:-1] + str(d) for d in days]
    choices = [Choice(name=r, value=r) for r in results]
    return choices


def match_timezones(tz: str, *, limit: int) -> list[str]:
    matches: list[tuple[str, int]] = []
    if len(query := full_process(tz, force_ascii=True)) != 0:
        matches = process.extractBests(
            query,
            pytz.common_timezones,
            processor=None,
            score_cutoff=70,
            limit=limit,
        )
    return [m[0] for m in matches]

async def tz_autocomplete(interaction: Interaction, value: str):
    matches = match_timezones(value, limit=10)
    choices = [Choice(name=m, value=m) for m in matches]
    return choices
