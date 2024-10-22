from discord.ext import commands

from .greeting import Greeting

__all__ = ("CogManager",)

_cogs_dict = {
    Greeting.__name__: Greeting,
}


class CogManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context):
        # 检查调用者是否是owner
        return await commands.is_owner().predicate(ctx)

    async def cog_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("`You do not have permission!`")

    def _create_cog(self, name):
        cog = _cogs_dict.get(name)
        if cog is not None:
            cog = cog(self.bot)
        return cog

    async def add_cog(self, cog, override=True):
        await self.bot.add_cog(cog, override=override)

    async def remove_cog(self, name):
        return await self.bot.remove_cog(name)

    @commands.command()
    async def enable(self, ctx: commands.Context, cog_name):
        cog = self._create_cog(cog_name)
        if cog is None:
            await ctx.send(f"`No function named {cog_name}.`")
        else:
            await self.add_cog(cog, override=True)

    @commands.command()
    async def disable(self, ctx: commands.Context, cog_name):
        if cog_name == CogManager.__name__ or self.bot.get_cog(cog_name) is None:
            await ctx.send(f"`No function named {cog_name}.`")
        await self.remove_cog(cog_name)
