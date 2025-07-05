from typing import Any, NamedTuple, TypedDict, overload
from zoneinfo import ZoneInfo

from discord import ButtonStyle, Interaction, app_commands, ui
from discord.app_commands import Choice
from discord.ext import commands

from sky_m8 import SkyM8
from utils.remote_config import remote_config

from ..helper import tzutils
from ..helper.embeds import fail, success
from ..helper.tzutils import (
    TimezoneFinder,
    format_hint,
    tz_autocomplete,
)
from .display import TimezoneDisplay

__all__ = (
    "UserProfileData",
    "UserProfile",
)


class UserProfileData(NamedTuple):
    hidden: bool
    timezone: ZoneInfo | None


class _UPData(TypedDict):
    hidden: bool
    timezone: str


class FieldTransformer(app_commands.Transformer):
    field_names = {
        "timezone": "Time Zone",
    }

    @property
    def choices(self):  # type: ignore
        c = [Choice(name=v, value=k) for k, v in self.field_names.items()]
        return c

    async def transform(self, interaction: Interaction, value: str):
        return value


class UserProfile(commands.Cog):
    _PROFILE_KEY = "userProfile"
    group_profile = app_commands.Group(
        name="profile",
        description="View and edit your personal profile.",
    )

    @classmethod
    async def set(cls, user_id: int, guild_id: int, field: str, value):
        await remote_config.set_json(cls._PROFILE_KEY, user_id, guild_id, field, value=value)  # fmt: skip

    @classmethod
    async def unset(cls, user_id: int, guild_id: int, field: str):
        await remote_config.delete_json(cls._PROFILE_KEY, user_id, guild_id, field)

    @classmethod
    async def user(cls, user_id: int, guild_id=0, merge=True):
        data: _UPData = await remote_config.get_json(cls._PROFILE_KEY, user_id, guild_id) or {}  # type: ignore # fmt: skip
        if merge and guild_id != 0:
            main: _UPData = await remote_config.get_json(cls._PROFILE_KEY, user_id, 0) or {}  # type: ignore # fmt: skip
            data = main | data
        hidden = data.get("hidden", False)
        timezone = None
        if data.get("timezone") in tzutils.valid_timezones:
            timezone = ZoneInfo(data["timezone"])
        return UserProfileData(
            hidden=hidden,
            timezone=timezone,
        )

    # fmt: off
    @overload
    @classmethod
    async def fields(cls, user_id: int, *, guild_id=0, merge=True) -> None: ...
    @overload
    @classmethod
    async def fields(cls, user_id: int, __field: str, /, *, guild_id=0, merge=True) -> Any | None: ...
    @overload
    @classmethod
    async def fields(cls, user_id: int, __field: str, /, *fields: str, guild_id=0, merge=True) -> list[Any | None]: ...
    # fmt: on

    @classmethod
    async def fields(cls, user_id: int, *fields: str, guild_id=0, merge=True):
        if len(fields) == 0:
            return None
        paths = [[user_id, guild_id, f] for f in fields]
        values = await remote_config.get_json_m(cls._PROFILE_KEY, *paths)
        if merge and guild_id != 0:
            main_paths = [[user_id, 0, f] for f in fields]
            main_values = await remote_config.get_json_m(cls._PROFILE_KEY, *main_paths)
            values = [m if s is None else s for s, m in zip(values, main_values)]
        return values if len(values) > 1 else values[0]

    def __init__(self, bot: SkyM8):
        self.bot = bot

    async def __check_guild(self, interaction: Interaction, per_server: bool):
        guild_id = interaction.guild_id if per_server else 0
        if guild_id is None:
            await interaction.followup.send(embed=fail("You are not in a server"))
            return None
        return guild_id

    @group_profile.command(name="visibility", description="Set your profile's visibility to others.")  # fmt: skip
    @app_commands.describe(
        hidden="Whether to hide your profile to others, defaults to public",
        per_server="Set per-server profile instead of main, defaults to main profile",
    )
    @app_commands.rename(per_server="per-server")
    async def profile_visibility(
        self,
        interaction: Interaction,
        hidden: bool,
        per_server: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)
        if (guild_id := await self.__check_guild(interaction, per_server)) is None:
            return
        user = interaction.user
        try:
            await self.set(user.id, guild_id, "hidden", hidden)
            scope = "per-server" if per_server else "main"
            visibility = "hidden" if hidden else "public"
            await interaction.followup.send(
                embed=success(
                    "Success",
                    f"Your **{scope}** profile is now __{visibility}__.",
                )
            )
        except Exception as ex:
            await interaction.followup.send(embed=fail("Error while setting", ex))

    @group_profile.command(name="unset", description="Remove a field in your profile.")
    @app_commands.describe(
        field="The field you want to remove.",
        per_server="Remove per-server profile instead of main, defaults to main profile",
    )
    @app_commands.rename(per_server="per-server")
    async def profile_unset(
        self,
        interaction: Interaction,
        field: app_commands.Transform[str, FieldTransformer],
        per_server: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)
        if (guild_id := await self.__check_guild(interaction, per_server)) is None:
            return
        user = interaction.user
        try:
            await self.unset(user.id, guild_id, field)
            await interaction.followup.send(embed=success("Success"))
        except Exception as ex:
            await interaction.followup.send(embed=fail("Error while removing", ex))

    @group_profile.command(name="timezone", description="Set your time zone.")
    @app_commands.describe(
        timezone="Type time zone name or country name to search.",
        per_server="Set per-server profile instead of main, defaults to main profile",
    )
    @app_commands.rename(per_server="per-server")
    @app_commands.autocomplete(timezone=tz_autocomplete)
    async def profile_timezone(
        self,
        interaction: Interaction,
        timezone: str,
        per_server: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)
        if (guild_id := await self.__check_guild(interaction, per_server)) is None:
            return
        # 尝试精确匹配时区
        match = TimezoneFinder.exact_match(timezone)
        if not match:
            # 时区无效则提示用户可能的匹配并返回
            matches = TimezoneFinder.best_matches(timezone, limit=5)
            hint = format_hint(matches)
            embed = fail(
                "Invalid time zone",
                (
                    f"Cannot find a time zone matching `{timezone}`.\n"
                    "If you're not sure about your time zone, click the button below to check!"
                ),
            )
            view = ui.View().add_item(
                ui.Button(
                    style=ButtonStyle.url,
                    label="My Time Zone",
                    url="https://www.timezonevisualizer.com/my-timezone",
                )
            )
            await interaction.followup.send(
                content=hint,
                embed=embed,
                view=view,
            )
            return
        user = interaction.user
        timezone = match[0]
        try:
            await self.set(user.id, guild_id, "timezone", timezone)
            # 展示当前时区信息
            display = TimezoneDisplay()
            embed = display.embed(user, ZoneInfo(timezone))
            await interaction.followup.send(embed=embed)
        except Exception as ex:
            await interaction.followup.send(embed=fail("Error while saving", ex))
