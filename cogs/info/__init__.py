from sky_bot import SkyBot

from .profile import Profile


async def setup(bot: SkyBot):
    await bot.add_cog(Profile(bot))
