from sky_m8 import SkyM8

from .timestamp import TimestampMaker


async def setup(bot: SkyM8):
    await bot.add_cog(TimestampMaker(bot))
