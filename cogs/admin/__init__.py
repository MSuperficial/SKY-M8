from sky_m8 import SkyM8

from . import role_manager, welcome


async def setup(bot: SkyM8):
    await role_manager.setup(bot)
    await welcome.setup(bot)
