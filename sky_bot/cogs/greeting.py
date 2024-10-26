import asyncio

import discord
from discord.ext import commands

from ..utils import get_id_from_env

__all__ = ("Greeting",)


class Greeting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.default_role_id = get_id_from_env("DEFAULT_ROLE_ID")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        # 如果默认角色存在，就添加默认角色
        if (
            self.default_role_id is not None
            and (default_role := guild.get_role(self.default_role_id)) is not None
        ):
            await member.add_roles(default_role)
        # 发送欢迎消息
        if guild.system_channel is not None:
            await asyncio.sleep(1)
            welcome = f"Welcome {member.mention} to **{guild.name}**!"
            await guild.system_channel.send(welcome)

    @commands.command()
    async def hello(self, ctx: commands.Context):
        author = ctx.author
        is_member = isinstance(author, discord.Member)
        # 如果成员有分配角色
        if is_member and author.top_role.name != "@everyone":
            hello = f"Hello **{author.top_role.name}** {author.mention}!"
        # 如果非成员，或成员没有分配角色
        else:
            hello = f"Hello {author.mention}!"
        await ctx.send(hello)


async def setup(bot: commands.Bot):
    await bot.add_cog(Greeting(bot))
