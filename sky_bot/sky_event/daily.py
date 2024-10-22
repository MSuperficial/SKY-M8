from datetime import datetime, timedelta

from discord import Message
from discord.utils import format_dt as timestamp

from ..utils import sky_time_now
from .daily_data import DailyEvent, daily_event_datas

__all__ = (
    "respond_daily_event",
    "get_all_daily_event_msg",
)


async def respond_daily_event(msg: Message):
    now = sky_time_now()
    dailiesInfo = get_all_daily_event_msg(now)
    await msg.channel.send(dailiesInfo)


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


def get_daily_event_msg(now: datetime, daily: DailyEvent):
    name = daily_event_datas[daily].name
    current_end, next_begin = get_daily_event_time(now, daily)
    # 事件名称
    msg = f"## {name}\n"
    # 当前事件结束时间
    if current_end is not None:
        msg += f"🔹 Current ends {timestamp(current_end, 'R')}.\n"
    # 下次事件开始时间
    msg += f"🔸 Next at {timestamp(next_begin, 't')}, {timestamp(next_begin, 'R')}."
    return msg


def get_all_daily_event_msg(now: datetime, header=True, footer=True):
    dailies = list(DailyEvent)
    msgs = [get_daily_event_msg(now, e) for e in dailies]
    dailies_msg = "\n".join(msgs)
    if header:
        dailies_msg = "# Sky Events Timer\n" + dailies_msg
    if footer:
        dailies_msg = (
            dailies_msg
            + "\n\n*See [Sky Clock](<https://sky-clock.netlify.app>) by [Chris Stead](<https://github.com/cmstead>) for more.*"
        )
    return dailies_msg
