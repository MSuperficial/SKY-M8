from datetime import datetime
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

import pytz
from discord import ButtonStyle, Interaction, app_commands, ui
from discord.app_commands import Choice
from discord.ext import commands

from ..embed_template import fail, success
from ..remote_config import remote_config
from ..sky_bot import SkyBot
from ..utils import format_dt_full, format_utcoffset
from .helper.timezone import TimezoneFinder, format_hint, tz_autocomplete

__all__ = (
    "UserProfile",
    "Profile",
)


class UserProfile(NamedTuple):
    private: bool
    timezone: ZoneInfo | None


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


class Profile(commands.Cog):
    _PROFILE_KEY = "userProfile"
    group_profile = app_commands.Group(
        name="profile",
        description="View and edit your personal profile.",
    )

    @classmethod
    async def user(cls, user_id: int):
        obj: dict[str, Any] | None = await remote_config.get_json(
            cls._PROFILE_KEY, user_id
        )
        if not obj:
            return None
        timezone = None
        if obj["timezone"] in pytz.common_timezones:
            timezone = ZoneInfo(obj["timezone"])
        return UserProfile(
            private=obj["private"],
            timezone=timezone,
        )

    @classmethod
    async def user_fields(cls, user_id: int, *fields: str):
        paths = [[user_id, f] for f in fields]
        values = await remote_config.get_json_m(cls._PROFILE_KEY, *paths)
        return values

    def __init__(self, bot: SkyBot):
        self.bot = bot

    @group_profile.command(name="visibility", description="Set your profile's visibility to others.")  # fmt: skip
    @app_commands.describe(
        private="Whether to hide your profile to others, by default False",
    )
    async def profile_visibility(self, interaction: Interaction, private: bool):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user
        try:
            await remote_config.set_json(self._PROFILE_KEY, user.id, "private", value=private)  # fmt: skip
            await interaction.followup.send(
                embed=await success(
                    "Success",
                    description=f"Your profile is now __{'private' if private else 'public'}__.",
                )
            )
        except Exception as ex:
            await interaction.followup.send(
                embed=await fail("Error while setting", description=str(ex))
            )

    @group_profile.command(name="unset", description="Remove a field in your profile.")
    @app_commands.describe(
        field="The field you want to remove.",
    )
    async def profile_unset(
        self,
        interaction: Interaction,
        field: app_commands.Transform[str, FieldTransformer],
    ):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user
        try:
            await remote_config.delete_json(self._PROFILE_KEY, user.id, field)
            await interaction.followup.send(embed=await success("Success"))
        except Exception as ex:
            await interaction.followup.send(
                embed=await fail("Error while removing", description=str(ex))
            )

    @group_profile.command(name="timezone", description="Set your time zone.")
    @app_commands.describe(
        timezone="IANA identifier of your time zone.",
    )
    @app_commands.autocomplete(timezone=tz_autocomplete)
    async def profile_timezone(self, interaction: Interaction, timezone: str):
        await interaction.response.defer(ephemeral=True)
        # 检查时区是否有效
        if timezone not in pytz.common_timezones:
            # 提示用户可能的匹配
            matches = TimezoneFinder.best_matches(timezone, limit=5)
            hint = format_hint(matches)
            embed = await fail(
                "Invalid time zone",
                description="If you're not sure about your time zone, click the button below to check!",
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
                ephemeral=True,
            )
            return
        user = interaction.user
        try:
            tz = ZoneInfo(timezone)
            await remote_config.set_json(self._PROFILE_KEY, user.id, "timezone", value=timezone)  # fmt: skip
            # 展示当前时区信息
            now = datetime.now(tz)
            desc = (
                f"### Your Time Zone\n`{timezone}`\n"
                f"### UTC Offset\n`{format_utcoffset(now)}`\n"
                f"### Current Local Time\n`{format_dt_full(now)}`"
            )
            await interaction.followup.send(
                embed=await success("Success", description=desc)
            )
        except Exception as ex:
            await interaction.followup.send(
                embed=await fail("Error while saving", description=str(ex))
            )


async def setup(bot: SkyBot):
    await bot.add_cog(Profile(bot))
