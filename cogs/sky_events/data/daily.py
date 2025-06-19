import json
from datetime import datetime, timedelta
from typing import NamedTuple

from cogs.emoji_manager import Emojis
from utils.remote_config import remote_config

from .shard import get_shard_info

__all__ = (
    "DailyEventData",
    "fetch_displayed_events",
    "fetch_all_event_data",
    "filter_events",
    "get_daily_event_time",
)


_EVENTS_KEY = "dailyClock.events"

_default_events = [
    "geyser",
    "peakshard",
    "grandma",
    "turtle",
    "aurora",
    "firework",
    "dailyreset",
]


class DailyEventData(NamedTuple):
    id: str
    name: str
    offset: int
    duration: int
    period: int
    days_of_month: list[int] | None = None


_daily_event_data = {
    "geyser": DailyEventData(
        id="geyser",
        name="⛲ Geyser",
        offset=5,
        duration=10,
        period=120,
    ),
    "peakshard": DailyEventData(
        id="peakshard",
        name="🏔️ Peaks Shard",
        offset=8,
        duration=22,
        period=30,
    ),
    "grandma": DailyEventData(
        id="grandma",
        name="🍞 Grandma",
        offset=35,
        duration=10,
        period=120,
    ),
    "turtle": DailyEventData(
        id="turtle",
        name="🐢 Turtle",
        offset=50,
        duration=10,
        period=120,
    ),
    "aurora": DailyEventData(
        id="aurora",
        name=f"{Emojis('season_aurora', '🎶')} Aurora Concert",
        offset=10,
        duration=48,
        period=240,
    ),
    "firework": DailyEventData(
        id="firework",
        name="🎆 Aviary Firework",
        offset=10,
        duration=10,
        period=240,
        days_of_month=[1],
    ),
    "dailyreset": DailyEventData(
        id="dailyreset",
        name="⏱️ Daily Reset",
        offset=0,
        duration=0,
        period=24 * 60,
    ),
}


async def fetch_displayed_events():
    events: list[str] = _default_events
    value = await remote_config.get_field(_EVENTS_KEY, "displayedEvents")
    if value:
        events = json.loads(value)
    return events


async def fetch_all_event_data():
    data = _daily_event_data.copy()
    overrides: dict[str, dict] = {}
    value = await remote_config.get_field(_EVENTS_KEY, "eventDataOverrides")
    if value:
        overrides = json.loads(value)
    for k, v in overrides.items():
        if k in data:
            data[k] = data[k]._replace(**v)
        else:
            data[k] = DailyEventData(**v)
    return data


def filter_events(event_data: list[DailyEventData], date: datetime):
    def available(e: DailyEventData):
        # 判断是否在设定的日期内
        if e.days_of_month is not None and date.day not in e.days_of_month:
            return False
        # 如果今天没有Peaks Shard或其不提供烛火，则无需显示其信息
        if e.id == "peakshard":
            shard_info = get_shard_info(date)
            if not (shard_info.has_shard and shard_info.extra_shard):
                return False
        return True

    events = [e for e in event_data if available(e)]
    return events


def get_daily_event_time(now: datetime, event_data: DailyEventData):
    # 计算自今天开始经过的分钟数
    now_time = now.replace(second=0, microsecond=0)
    minutes_passed = now_time.hour * 60 + now_time.minute
    # 计算自上次事件开始经过的分钟数
    minutes_from_last = (minutes_passed - event_data.offset) % event_data.period
    # 如果当前事件正在进行，计算当前时间结束的时间
    current_end_time = None
    if minutes_from_last < event_data.duration:
        current_end_time = now_time + timedelta(
            minutes=event_data.duration - minutes_from_last
        )
    # 计算下次事件开始的时间
    next_begin_time = now_time + timedelta(
        minutes=event_data.period - minutes_from_last
    )
    return current_end_time, next_begin_time
