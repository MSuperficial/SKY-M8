from sky_m8 import SkyM8

from . import daily_clock, shard_calendar


async def setup(bot: SkyM8):
    await daily_clock.setup(bot)
    await shard_calendar.setup(bot)
