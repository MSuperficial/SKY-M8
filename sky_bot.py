from logging import getLogger
from typing import Generator, List, Optional

import discord
from discord import app_commands
from discord.app_commands import AppCommandContext, AppInstallationType
from discord.ext import commands
from discord.utils import MISSING

from cogs.cog_manager import CogManager

__all__ = (
    "SkyBot",
    "MentionableTree",
)

_log = getLogger(__name__)


class SkyBot(commands.Bot):
    def __init__(self, *args, initial_extensions: list[str], **kwargs):
        super().__init__(
            allowed_installs=AppInstallationType(guild=True, user=True),
            allowed_contexts=AppCommandContext(
                guild=True, dm_channel=True, private_channel=True
            ),
            *args,
            **kwargs,
        )
        self.initial_extensions = initial_extensions
        self._owner: discord.User = MISSING

    async def setup_hook(self) -> None:
        # 加载初始扩展
        await self.add_cog(CogManager(self))
        for extension in self.initial_extensions:
            extension = "cogs." + extension
            await self.load_extension(extension)

    async def on_ready(self):
        print(f"We have logged in as {self.user}")

    @property
    def owner(self):
        if not self._owner:
            self._owner = self.get_user(self.owner_id)  # type: ignore
        return self._owner

    def is_mine(self, message: discord.Message):
        return message.author == self.user

    async def on_message(self, message: discord.Message):
        # 忽略自己的消息
        if self.is_mine(message):
            return
        # 处理命令
        await super().on_message(message)


# fmt: off
class MentionableTree(app_commands.CommandTree):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.application_commands: dict[Optional[int], List[app_commands.AppCommand]] = {}
        self.cache: dict[Optional[int], dict[app_commands.Command | commands.HybridCommand | str, str]] = {}

    async def sync(self, *, guild: Optional[discord.abc.Snowflake] = None):
        """Method overwritten to store the commands."""
        ret = await super().sync(guild=guild)
        guild_id = guild.id if guild else None
        self.application_commands[guild_id] = ret
        self.cache.pop(guild_id, None)
        return ret

    async def fetch_commands(self, *, guild: Optional[discord.abc.Snowflake] = None):
        """Method overwritten to store the commands."""
        ret = await super().fetch_commands(guild=guild)
        guild_id = guild.id if guild else None
        self.application_commands[guild_id] = ret
        self.cache.pop(guild_id, None)
        return ret

    async def get_or_fetch_commands(self, *, guild: Optional[discord.abc.Snowflake] = None):
        """Method overwritten to store the commands."""
        try:
            return self.application_commands[guild.id if guild else None]
        except KeyError:
            return await self.fetch_commands(guild=guild)


    async def find_mention_for(
        self,
        command: app_commands.Command | commands.HybridCommand | str,
        *,
        guild: Optional[discord.abc.Snowflake] = None,
    ) -> Optional[str]:
        """Retrieves the mention of an AppCommand given a specific command name, and optionally, a guild.
        Parameters
        ----------
        name: Union[app_commands.Command, commands.HybridCommand, str]
            The command to retrieve the mention for.
        guild: Optional[discord.abc.Snowflake]
            The scope (guild) from which to retrieve the commands from. If None is given or not passed,
            only the global scope will be searched, however the global scope will also be searched if
            a guild is passed.
        
        Returns
        -------
        str | None
            The command mention, if found.
        """

        guild_id = guild.id if guild else None
        try:
            return self.cache[guild_id][command]
        except KeyError:
            pass

        # If a guild is given, and fallback to global is set to True, then we must also
        # check the global scope, as commands for both show in a guild.
        check_global = self.fallback_to_global is True and guild is not None

        if isinstance(command, str):
            # Try and find a command by that name. discord.py does not return children from tree.get_command, but
            # using walk_commands and utils.get is a simple way around that.
            _command = discord.utils.get(self.walk_commands(guild=guild), qualified_name=command)

            if check_global and not _command:
                _command = discord.utils.get(self.walk_commands(), qualified_name=command)

        else:
            _command = command

        if not _command:
            return None

        local_commands = await self.get_or_fetch_commands(guild=guild)
        app_command_found = discord.utils.get(local_commands, name=(_command.root_parent or _command).name)

        if check_global and not app_command_found:
            global_commands = await self.get_or_fetch_commands(guild=None)
            app_command_found = discord.utils.get(global_commands, name=(_command.root_parent or _command).name)

        if not app_command_found:
            return None

        mention = f"</{_command.qualified_name}:{app_command_found.id}>"
        self.cache.setdefault(guild_id, {})
        self.cache[guild_id][command] = mention
        return mention
    
    def _walk_children(self, commands: list[app_commands.Group | app_commands.Command]) -> Generator[app_commands.Command, None, None]:
        for command in commands:
            if isinstance(command, app_commands.Group):
                yield from self._walk_children(command.commands)
            else:
                yield command

    async def walk_mentions(self, *, guild: Optional[discord.abc.Snowflake] = None, yield_unknown: bool = False):
        """Gets all valid mentions for app commands in a specific guild.
        This takes into consideration group commands, it will only return mentions for
        the command's children, and not the parent as parents aren't mentionable.
        
        Parameters
        ----------
        guild: Optional[discord.Guild]
            The guild to get commands for. If not given, it will only return global commands.
        yield_unknown: bool
            If this is set to True, the yielded mention can be None, instead of it being ignored. Defaults to False.
        Yields
        ------
        Tuple[Union[app_commands.Command`, commands.HybridCommand], str]
       
        """
        for command in self._walk_children(self.get_commands(guild=guild, type=discord.AppCommandType.chat_input)):
            mention = await self.find_mention_for(command, guild=guild)
            if mention or yield_unknown:
                yield command, mention
        if guild and self.fallback_to_global is True:
            for command in self._walk_children(self.get_commands(guild=None, type=discord.AppCommandType.chat_input)):
                mention = await self.find_mention_for(command, guild=guild)
                if mention or yield_unknown:
                    yield command, mention
                else:
                    _log.warn("Could not find a mention for command %s in the API. Are you out of sync?", command)
