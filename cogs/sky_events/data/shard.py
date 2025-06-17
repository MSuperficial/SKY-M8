from datetime import datetime, time, timedelta
from enum import Enum
from typing import NamedTuple

from cogs.helper.times import SKY_TIMEZONE

__all__ = (
    "ShardType",
    "RewardType",
    "ShardTime",
    "ShardInfo",
    "get_shard_info",
    "MemoryType",
    "ShardExtra",
)

LAND_OFFSET = timedelta(minutes=8, seconds=40)
SHARD_DURATION = timedelta(hours=4)
BLACK_INTERVAL = timedelta(hours=8)
RED_INTERVAL = timedelta(hours=6)
SHARD_TIMES = 3


class ShardType(Enum):
    Black = 0
    Red = 1


class RewardType(Enum):
    Wax = 0
    AC = 1


class ShardTime(NamedTuple):
    start: datetime
    land: datetime
    end: datetime


class ShardInfo(NamedTuple):
    date: datetime
    type: ShardType
    realm: str
    map: str
    occurrences: list[ShardTime]
    reward_type: RewardType
    reward_number: float
    has_shard: bool
    extra_shard: bool


class _ShardData(NamedTuple):
    start: time
    maps: list[str]
    reward_type: RewardType
    reward_number: float
    no_shard_day: list[int]


realms = ["prairie", "forest", "valley", "wasteland", "vault"]

black_datas = [
    _ShardData(
        start=time(2, 10),
        maps=["village", "boneyard", "rink", "battlefield", "starlight"],
        reward_type=RewardType.Wax,
        reward_number=200,
        no_shard_day=[0, 6],
    ),
    _ShardData(
        start=time(1, 50),
        maps=["butterfly", "brook", "rink", "temple", "starlight"],
        reward_type=RewardType.Wax,
        reward_number=200,
        no_shard_day=[5, 6],
    ),
]
red_datas = [
    _ShardData(
        start=time(7, 40),
        maps=["cave", "end", "dreams", "graveyard", "jellyfish"],
        reward_type=RewardType.AC,
        reward_number=2,
        no_shard_day=[0, 1],
    ),
    _ShardData(
        start=time(2, 20),
        maps=["bird", "treehouse", "dreams", "crab", "jellyfish"],
        reward_type=RewardType.AC,
        reward_number=2.5,
        no_shard_day=[1, 2],
    ),
    _ShardData(
        start=time(3, 30),
        maps=["sanctuary", "granny", "hermit", "ark", "jellyfish"],
        reward_type=RewardType.AC,
        reward_number=3.5,
        no_shard_day=[2, 3],
    ),
]

reward_override = {
    "end": 2.5,
    "dreams": 2.5,
    "treehouse": 3.5,
    "jellyfish": 3.5,
}


def _get_data(day) -> tuple[_ShardData, bool]:
    is_red = day % 2 == 1
    datas = red_datas if is_red else black_datas
    index = (day - 1) // 2 % len(datas) if is_red else (day // 2 - 1) % len(datas)
    data = datas[index]
    return data, is_red


def get_shard_info(when: datetime):
    when = when.astimezone(SKY_TIMEZONE)
    date = when.replace(hour=0, minute=0, second=0, microsecond=0)
    day = date.day
    realm_idx = (day - 1) % len(realms)
    data, is_red = _get_data(day)
    realm = realms[realm_idx]
    map = data.maps[realm_idx]
    reward = reward_override.get(map) or data.reward_number
    has_shard = date.weekday() not in data.no_shard_day
    extra_shard = realm == "prairie" and map == "butterfly"

    first_start = datetime.combine(date, data.start, SKY_TIMEZONE)
    interval = RED_INTERVAL if is_red else BLACK_INTERVAL
    occur = []
    for i in range(SHARD_TIMES):
        start = first_start + i * interval
        land = start + LAND_OFFSET
        end = start + SHARD_DURATION
        occur.append(ShardTime(start, land, end))

    return ShardInfo(
        date=date,
        type=ShardType.Red if is_red else ShardType.Black,
        realm=realm,
        map=map,
        occurrences=occur,
        reward_type=data.reward_type,
        reward_number=reward,
        has_shard=has_shard,
        extra_shard=extra_shard,
    )


class MemoryType(Enum):
    Jelly = 1
    Crab = 2
    Manta = 3
    Krill = 4
    Whale = 5
    Elder = 6


class ShardExtra(NamedTuple):
    has_memory: bool
    memory_type: MemoryType
    memory_user: int
    memory_by: str
    memory_timestamp: float

    @classmethod
    def from_dict(cls, value: dict):
        return ShardExtra(
            has_memory=value["hasMemory"],
            memory_type=MemoryType(value["memoryType"]),
            memory_user=int(value["memoryUser"]),
            memory_by=value["memoryBy"],
            memory_timestamp=value["memoryTimestamp"],
        )

    def to_dict(self):
        return {
            "hasMemory": self.has_memory,
            "memoryType": self.memory_type.value,
            "memoryUser": str(self.memory_user),
            "memoryBy": self.memory_by,
            "memoryTimestamp": self.memory_timestamp,
        }
