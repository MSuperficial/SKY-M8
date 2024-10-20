import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from sky_bot import SkyBot
from sky_bot.cogs.cog_manager import CogManager
from sky_bot.cogs.greeting import Greeting

load_dotenv(override=True)


async def main():
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True

    bot = SkyBot(commands.when_mentioned_or("!"), intents=intents)

    token = os.getenv("SKYBOT_TOKEN")
    if token is None:
        raise Exception("Please add your token to .env file.")

    async with bot:
        await bot.add_cog(CogManager(bot))
        await bot.add_cog(Greeting(bot))
        try:
            await bot.start(token)
        except discord.HTTPException as e:
            if e.status == 429:
                print(
                    "The Discord servers denied the connection for making too many requests"
                )
                print(
                    "Get help from https://stackoverflow.com/questions/66724687/in-discord-py-how-to-solve-the-error-for-toomanyrequests"
                )
            else:
                raise e


if __name__ == "__main__":
    asyncio.run(main())
