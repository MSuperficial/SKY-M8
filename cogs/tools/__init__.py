from sky_bot import SkyBot

from .timestamp import TimestampMaker


async def setup(bot: SkyBot):
    await bot.add_cog(TimestampMaker(bot))
