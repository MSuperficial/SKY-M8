from datetime import datetime, timedelta
from enum import Enum
from typing import NamedTuple

__all__ = (
    "DailyEvent",
    "daily_event_datas",
    "get_daily_event_time",
)


class DailyEvent(Enum):
    GEYSER = 10
    PEAKS_SHARD = 20
    GRANDMA = 30
    TURTLE = 40
    DAILY_RESET = 50


class DailyEventData(NamedTuple):
    id: DailyEvent
    name: str
    offset: int
    period: int
    duration: int


daily_event_ids = {
    "geyser": DailyEvent.GEYSER,
    "peaksshard": DailyEvent.PEAKS_SHARD,
    "granny": DailyEvent.GRANDMA,
    "grandma": DailyEvent.GRANDMA,
    "turtle": DailyEvent.TURTLE,
    "daily": DailyEvent.DAILY_RESET,
}

daily_event_datas = {
    DailyEvent.GEYSER: DailyEventData(
        id=DailyEvent.GEYSER,
        name="⛲ Geyser",
        offset=5,
        period=120,
        duration=10,
    ),
    DailyEvent.PEAKS_SHARD: DailyEventData(
        id=DailyEvent.PEAKS_SHARD,
        name="🏔️ Peaks Shard",
        offset=8,
        period=30,
        duration=22,
    ),
    DailyEvent.GRANDMA: DailyEventData(
        id=DailyEvent.GRANDMA,
        name="🍞 Grandma",
        offset=35,
        period=120,
        duration=10,
    ),
    DailyEvent.TURTLE: DailyEventData(
        id=DailyEvent.TURTLE,
        name="🐢 Turtle",
        offset=50,
        period=120,
        duration=10,
    ),
    DailyEvent.DAILY_RESET: DailyEventData(
        id=DailyEvent.DAILY_RESET,
        name="⏱️ Daily reset",
        offset=0,
        period=24 * 60,
        duration=0,
    ),
}


def get_daily_event_time(
    now: datetime, daily: DailyEvent
) -> tuple[datetime | None, datetime]:
    daily_data = daily_event_datas[daily]
    # 计算自今天开始经过的分钟数
    now_time = now.replace(second=0, microsecond=0)
    minutes_passed = now_time.hour * 60 + now_time.minute
    # 计算自上次事件开始经过的分钟数
    minutes_from_last = (minutes_passed - daily_data.offset) % daily_data.period
    # 如果当前事件正在进行，计算当前时间结束的时间
    current_end_time = None
    if minutes_from_last < daily_data.duration:
        current_end_time = now_time + timedelta(
            minutes=daily_data.duration - minutes_from_last
        )
    # 计算下次事件开始的时间
    next_begin_time = now_time + timedelta(
        minutes=daily_data.period - minutes_from_last
    )
    return current_end_time, next_begin_time
