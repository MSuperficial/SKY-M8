from sky_m8 import SkyM8

from . import daily_guides, shard_calendar, sky_clock


async def setup(bot: SkyM8):
    await sky_clock.setup(bot)
    await shard_calendar.setup(bot)
    await daily_guides.setup(bot)
