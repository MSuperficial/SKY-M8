from sky_m8 import SkyM8

from .clock import Clock
from .profile import UserProfile


async def setup(bot: SkyM8):
    await bot.add_cog(UserProfile(bot))
    await bot.add_cog(Clock(bot))
