from sky_m8 import SkyM8

from .timestamp import TimestampMaker
from .utility import Utility


async def setup(bot: SkyM8):
    await bot.add_cog(TimestampMaker(bot))
    await bot.add_cog(Utility(bot))
