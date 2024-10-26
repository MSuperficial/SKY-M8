from datetime import datetime, timedelta

from .daily_data import DailyEvent, daily_event_datas

__all__ = ("get_daily_event_time",)


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
