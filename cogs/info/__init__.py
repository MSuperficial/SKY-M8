from sky_bot import SkyBot

from .clock import Clock
from .profile import UserProfile


async def setup(bot: SkyBot):
    await bot.add_cog(UserProfile(bot))
    await bot.add_cog(Clock(bot))
