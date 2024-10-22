from enum import Enum
from typing import NamedTuple

__all__ = (
    "DailyEvent",
    "daily_event_datas",
)


class DailyEvent(Enum):
    GEYSER = (1,)
    GRANDMA = (2,)
    TURTLE = (3,)
    DAILY_RESET = (4,)


class DailyEventData(NamedTuple):
    id: DailyEvent
    name: str
    offset: int
    period: int
    duration: int


daily_event_ids = {
    "geyser": DailyEvent.GEYSER,
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
