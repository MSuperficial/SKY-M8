from sky_bot import SkyBot

from . import daily_clock, shard_calendar


async def setup(bot: SkyBot):
    await daily_clock.setup(bot)
    await shard_calendar.setup(bot)
