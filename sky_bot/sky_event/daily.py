import json
from datetime import datetime, timedelta
from typing import NamedTuple

from ..remote_config import remote_config

__all__ = (
    "DailyEventData",
    "fetch_events",
    "fetch_event_data",
    "get_daily_event_time",
)


_EVENTS_KEY = "dailyClock.events"

_default_events = [
    "geyser",
    "peaks_shard",
    "aurora",
    "grandma",
    "turtle",
    "daily_reset",
]


class DailyEventData(NamedTuple):
    id: str
    name: str
    offset: int
    duration: int
    period: int


_daily_event_data = {
    "geyser": DailyEventData(
        id="geyser",
        name="⛲ Geyser",
        offset=5,
        duration=10,
        period=120,
    ),
    "peaks_shard": DailyEventData(
        id="peaks_shard",
        name="🏔️ Peaks Shard",
        offset=8,
        duration=22,
        period=30,
    ),
    "aurora": DailyEventData(
        id="aurora",
        name="🎶 Aurora Concert",
        offset=10,
        duration=48,
        period=240,
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
    "daily_reset": DailyEventData(
        id="daily_reset",
        name="⏱️ Daily reset",
        offset=0,
        duration=0,
        period=24 * 60,
    ),
}


async def fetch_events():
    events: list[str] = _default_events
    value = await remote_config.get_field(_EVENTS_KEY, "displayed_events")
    if value:
        events = json.loads(value)
    return events


async def fetch_event_data():
    data = _daily_event_data.copy()
    overrides: dict[str, dict] = {}
    value = await remote_config.get_field(_EVENTS_KEY, "event_data_overrides")
    if value:
        overrides = json.loads(value)
    for k, v in overrides.items():
        if k in data:
            data[k] = data[k]._replace(**v)
        else:
            data[k] = DailyEventData(**v)
    return data


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
