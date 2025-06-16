from sky_bot import SkyBot

from .clock import Clock
from .profile import Profile


async def setup(bot: SkyBot):
    await bot.add_cog(Profile(bot))
    await bot.add_cog(Clock(bot))
