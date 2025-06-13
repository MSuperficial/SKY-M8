import pytz
from discord import Interaction
from discord.app_commands import Choice
from thefuzz import process
from thefuzz.utils import full_process

__all__ = (
    "country_timezones",
    "timezone_country",
    "TimezoneFinder",
    "format_hint",
    "tz_autocomplete",
)

country_timezones: dict[str, list[str]] = {}
for k, v in pytz.country_timezones.items():
    name = pytz.country_names[k]
    country_timezones[name] = v
timezone_country: dict[str, str] = {}
for k, v in country_timezones.items():
    for x in v:
        timezone_country[x] = k


class TimezoneFinder:
    # 结合时区名和地区名
    _choices = pytz.common_timezones_set.union(country_timezones.keys())

    @classmethod
    def best_matches(cls, query: str, *, limit: int):
        matches: list[tuple[str, int]] = []
        query = full_process(query, force_ascii=True)
        if query:
            matches = process.extractBests(
                query,
                cls._choices,
                processor=None,
                score_cutoff=70,
                limit=limit,
            )
        results: list[tuple[str, str | None]] = []
        for m in [m[0] for m in matches]:
            if m in country_timezones:
                results.extend((tz, m) for tz in country_timezones[m])
            else:
                results.append((m, timezone_country.get(m)))
        # fromkeys 移除重复项同时保留顺序
        results = list(dict.fromkeys(results))[:limit]
        return results


def format_hint(matches: list[tuple[str, str | None]]):
    def fmt(m):
        if m[1]:
            return f"- `{m[0]}` in `{m[1]}`"
        else:
            return f"- `{m[0]}`"

    hint = ""
    if matches:
        hint = "\n".join(["Did you mean:"] + [fmt(m) for m in matches])
    return hint


async def tz_autocomplete(interaction: Interaction, value: str):
    matches = TimezoneFinder.best_matches(value, limit=10)
    choices = [
        Choice(
            name=f"{tz} -- {c}" if c else tz,
            value=tz,
        )
        for tz, c in matches
    ]
    return choices
