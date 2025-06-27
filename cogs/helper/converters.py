import calendar
import re
from datetime import datetime

from discord import AppCommandOptionType, Interaction, app_commands
from discord.app_commands import Choice
from discord.ext import commands

from .times import sky_datetime, sky_time_now, utcnow

__all__ = (
    "MessageTransformer",
    "DateTransformer",
    "date_autocomplete",
    "YearTransformer",
    "MonthTransformer",
    "DayTransformer",
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


class YearTransformer(app_commands.Transformer):
    @property
    def type(self):
        return AppCommandOptionType.integer

    @property
    def min_value(self):
        return 1

    @property
    def max_value(self):
        return 9999

    async def transform(self, interaction, value: int):
        return value

    async def autocomplete(self, interaction, value: str):  # type: ignore
        choices: list[Choice[int]] = []
        if value:
            return choices
        y = utcnow().year
        years = list(range(y - 2, y + 11))
        choices = [Choice(name=str(y), value=y) for y in years]
        return choices


class MonthTransformer(app_commands.Transformer):
    @property
    def type(self):
        return AppCommandOptionType.integer

    @property
    def min_value(self):
        return 1

    @property
    def max_value(self):
        return 12

    @property
    def choices(self):  # type: ignore
        return [Choice(name=str(m), value=m) for m in range(1, 13)]

    async def transform(self, interaction, value: int):
        return value


class DayTransformer(app_commands.Transformer):
    @property
    def type(self):
        return AppCommandOptionType.integer

    @property
    def min_value(self):
        return 1

    @property
    def max_value(self):
        return 31

    async def transform(self, interaction, value: int):
        return value

    async def autocomplete(self, interaction: Interaction, value: str):  # type: ignore
        now = utcnow()
        y = interaction.namespace.year or now.year
        m = interaction.namespace.month or now.month
        day_range = calendar.monthrange(y, m)[1]
        if not value:
            start = now.day - 2
            start = max(1, min(start, day_range - 6))
            days = range(start, start + 7)
        else:
            try:
                v = int(value)
                days = range(1, day_range + 1)
                days = [d for d in days if str(d).startswith(str(v))]
            except ValueError:
                days = []
        choices = [Choice(name=str(d), value=d) for d in days]
        return choices
