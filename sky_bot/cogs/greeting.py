from typing import Any

import discord
from discord import ButtonStyle, Interaction, app_commands, ui
from discord.ext import commands

from ..embed_template import fail, success
from ..remote_config import remote_config
from ..sky_bot import SkyBot
from .base.views import LongTextModal, ShortTextModal
from .helper.var_parser import VarParser

__all__ = ("Greeting",)


class Greeting(commands.Cog):
    _WELCOME_KEY = "welcomeSetup"
    _DEFAULT_MSG: dict[str, Any] = {
        "ping": False,
        "showAvatar": True,
        "color": "#5865F2",
        "title": "Welcome to {server.name}",
        "content": "We are glad to have you here, {member.mention}.",
        "footer": "You are the {member.ordinal} member of this server",
        "image": "{randomImage}",
    }
    group_welcome = app_commands.Group(
        name="welcome",
        description="Commands to setup welcome for new members.",
        allowed_contexts=app_commands.AppCommandContext(dm_channel=False),
        allowed_installs=app_commands.AppInstallationType(user=False),
    )

    def __init__(self, bot: SkyBot):
        self.bot = bot

    async def fetch_welcome_msg(self, guild_id: int):
        msg = await remote_config.get_json(self._WELCOME_KEY, guild_id, "message")
        msg = msg or await remote_config.get_json(self._WELCOME_KEY, 0, "message")
        msg = msg or self._DEFAULT_MSG
        return msg

    async def fetch_valid_welcome_roles(self, guild: discord.Guild):
        role_ids: list[str] = (
            await remote_config.get_json(self._WELCOME_KEY, guild.id, "roles") or []
        )  # type: ignore
        roles = [r for id in role_ids if (r := guild.get_role(int(id)))]
        roles = [r for r in roles if r.is_assignable()]
        return roles

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        # 检查权限并设置角色
        if guild.me.guild_permissions.manage_roles:
            roles = await self.fetch_valid_welcome_roles(guild)
            if roles:
                await member.add_roles(*roles, reason="Default roles")
        # 检查系统频道并发送欢迎消息
        if guild.system_channel:
            msg_obj = await self.fetch_welcome_msg(guild.id)
            builder = WelcomeMessageBuilder(
                VarParser.from_member_join(self.bot, member)
            )
            msg_data = builder.build(msg_obj)
            await guild.system_channel.send(**msg_data)

    @group_welcome.command(name="enable", description="Switch welcome features, by default all False.")  # fmt: skip
    @app_commands.describe(
        message="Whether to send welcome message, leave empty to keep it as is.",
    )
    async def welcome_enable(
        self,
        interaction: Interaction,
        message: bool | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        guild: discord.Guild = interaction.guild  # type: ignore
        options = {
            "message": message,
        }
        # 筛选选项并设置
        options = {k: v for k, v in options.items() if v is not None}
        await remote_config.merge_json(
            self._WELCOME_KEY, guild.id, "enable", value=options
        )
        # 获取当前选项并展示
        options = await remote_config.get_json(self._WELCOME_KEY, guild.id, "enable")
        await interaction.followup.send(
            embed=discord.Embed(
                color=discord.Color.greyple(),
                title="Welcome feature options",
                description="\n".join(
                    [f"`{k}` : {'Yes' if v else 'No'}" for k, v in options.items()]  # type: ignore
                ),
            ),
        )

    @group_welcome.command(name="message", description="Edit welcome message.")
    async def welcome_message(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        # 获取消息对象
        msg_obj = await self.fetch_welcome_msg(interaction.guild.id)  # type: ignore
        # 生成消息
        builder = WelcomeMessageBuilder(VarParser.from_interaction(interaction))
        msg_data = builder.build(msg_obj)
        view = WelcomeMessageView(msg_obj=msg_obj, builder=builder)
        await interaction.followup.send(**msg_data, view=view)

    @group_welcome.command(name="roles", description="Set default roles for new members.")  # fmt: skip
    async def welcome_roles(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        guild: discord.Guild = interaction.guild  # type: ignore
        # 检查权限
        if not guild.me.guild_permissions.manage_roles:
            await interaction.followup.send(
                embed=await fail(
                    "Missing permission",
                    description=f"Please add `Manage Roles` permission for {guild.me.mention} first.",
                ),
            )
            return
        # 获取有效角色
        roles = await self.fetch_valid_welcome_roles(guild)
        view = WelcomeRolesView(default_roles=roles)
        await interaction.followup.send(
            content="### Select default roles for new member:",
            view=view,
        )

    @group_welcome.command(name="preview", description="Preview welcome message for selected member.")  # fmt: skip
    @app_commands.describe(
        member="The member to welcome, by default is yourself.",
        private="Only you can see the message, by default True.",
    )
    async def welcome_preview(
        self,
        interaction: Interaction,
        member: discord.Member | None = None,
        private: bool = True,
    ):
        await interaction.response.defer(ephemeral=private)
        # 获取消息对象
        msg_obj = await self.fetch_welcome_msg(interaction.guild.id)  # type: ignore
        # 生成消息
        builder = WelcomeMessageBuilder(
            VarParser.from_interaction(interaction, user=member)
        )
        msg_data = builder.build(msg_obj)
        await interaction.followup.send(**msg_data)


class WelcomeMessageBuilder:
    def __init__(self, parser: VarParser):
        self.parser = parser
        self.member: discord.Member = parser.context.member  # type: ignore

    def build(self, obj: dict[str, Any]):
        obj_copy = {}
        for k, v in obj.items():
            if isinstance(v, str):
                v = self.parser.parse(v)
            obj_copy[k] = v
        if not obj_copy["color"]:
            color = None
        else:
            color = discord.Color.from_str(obj_copy["color"])
        embed = (
            discord.Embed(
                color=color,
                title=obj_copy["title"],
                description=obj_copy["content"],
            )
            .set_footer(text=obj_copy["footer"])
            .set_image(url=obj_copy["image"])
        )
        if obj_copy["showAvatar"]:
            embed.set_author(
                name=self.member.display_name,
                icon_url=self.member.display_avatar.url,
            )
        content = self.member.mention if obj_copy["ping"] else None
        return {
            "content": content,
            "embed": embed,
        }


class WelcomeMessageView(ui.View):
    def __init__(self, *, msg_obj: dict[str, Any], builder: WelcomeMessageBuilder):
        super().__init__(timeout=900)
        self.add_item(
            ui.Button(
                style=ButtonStyle.url,
                label="Color Picker",
                emoji="🎨",
                url="https://g.co/kgs/Pxm4qRy",
                row=2,
            )
        )
        self.msg_obj = msg_obj
        self.builder = builder

    async def update_message(self, interaction: Interaction):
        msg_data = self.builder.build(self.msg_obj)
        await interaction.edit_original_response(**msg_data)

    @ui.button(label="Toggle ping", row=0)
    async def toggle_ping(self, interaction: Interaction, button):
        await interaction.response.defer()
        self.msg_obj["ping"] = not self.msg_obj["ping"]
        await self.update_message(interaction)

    @ui.button(label="Toggle avatar", row=0)
    async def toggle_avatar(self, interaction: Interaction, button):
        await interaction.response.defer()
        self.msg_obj["showAvatar"] = not self.msg_obj["showAvatar"]
        await self.update_message(interaction)

    @ui.button(label="Title", row=1)
    async def edit_title(self, interaction: Interaction, button):
        modal = ShortTextModal(
            title="Set message title",
            label="Title (Optional)",
            default=self.msg_obj["title"],
            required=False,
        )
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.msg_obj["title"] = modal.text.value
        await self.update_message(interaction)

    @ui.button(label="Content", row=1)
    async def edit_content(self, interaction: Interaction, button):
        modal = LongTextModal(
            title="Set message content",
            label="Content",
            default=self.msg_obj["content"],
        )
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.msg_obj["content"] = modal.text.value
        await self.update_message(interaction)

    @ui.button(label="Footer", row=1)
    async def edit_footer(self, interaction: Interaction, button):
        modal = ShortTextModal(
            title="Set message footer",
            label="Footer (Optional)",
            default=self.msg_obj["footer"],
            required=False,
        )
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.msg_obj["footer"] = modal.text.value
        await self.update_message(interaction)

    @ui.button(label="Color", row=1)
    async def set_color(self, interaction: Interaction, button):
        modal = ShortTextModal(
            title="Set border color",
            label="Color (Optional)",
            default=self.msg_obj["color"],
            required=False,
        )
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.text.value:
            # 检查颜色格式是否正确
            try:
                discord.Color.from_str(modal.text.value)
            except ValueError:
                await interaction.followup.send(
                    embed=await fail("Invalid color format"),
                    ephemeral=True,
                )
                return
        self.msg_obj["color"] = modal.text.value
        await self.update_message(interaction)

    @ui.button(label="Image", row=1)
    async def set_image(self, interaction: Interaction, button):
        modal = ShortTextModal(
            title="Set image url",
            label="Image url (Optional)",
            default=self.msg_obj["image"],
            required=False,
        )
        await interaction.response.send_modal(modal)
        await modal.wait()
        old_image = self.msg_obj["image"]
        try:
            self.msg_obj["image"] = modal.text.value
            await self.update_message(interaction)
        except discord.HTTPException as ex:
            if ex.status == 400:
                # url格式错误
                self.msg_obj["image"] = old_image
                await interaction.followup.send(
                    embed=await fail("Invalid url format"),
                    ephemeral=True,
                )
            else:
                raise ex

    @ui.button(label="Help", emoji="❔", style=ButtonStyle.primary, row=2)
    async def show_help(self, interaction: Interaction, button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        color_help = (
            "## Color How-to\n"
            "Click the **Color Picker** button, pick your color, and use the HEX value (include the '#')."
        )
        var_help = await VarParser.get_help()
        await interaction.followup.send(
            content="\n".join([color_help, var_help]),
        )

    @ui.button(label="Save", style=ButtonStyle.success, row=3)
    async def save(self, interaction: Interaction, button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild: discord.Guild = interaction.guild  # type: ignore
        try:
            await remote_config.merge_json(
                Greeting._WELCOME_KEY, guild.id, "message", value=self.msg_obj
            )
            await interaction.followup.send(
                embed=await success("Welcome message saved"),
            )
        except Exception as ex:
            await interaction.followup.send(
                embed=await fail("Error while saving", description=str(ex)),
            )


class WelcomeRolesView(ui.View):
    def __init__(self, *, default_roles: list[discord.Role] = []):
        super().__init__(timeout=300)
        self.select_roles.default_values = default_roles

    @ui.select(
        cls=ui.RoleSelect,
        placeholder="Select default roles...",
        min_values=0,
        max_values=25,
    )
    async def select_roles(self, interaction: Interaction, select: ui.RoleSelect):
        await interaction.response.defer()
        roles = select.values
        roles = [r for r in roles if not r.is_assignable()]
        if roles:
            mentions = " ".join([r.mention for r in roles])
            await interaction.followup.send(
                embed=await fail(
                    "Invalid roles",
                    description="These roles aren't assignable:\n" + mentions,
                ),
                ephemeral=True,
            )

    @ui.button(label="Save", style=ButtonStyle.success)
    async def save(self, interaction: Interaction, button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild: discord.Guild = interaction.guild  # type: ignore
        roles = self.select_roles.values
        valid = [r for r in roles if r.is_assignable()]
        invalid = [r for r in roles if not r.is_assignable()]
        try:
            await remote_config.merge_json(
                Greeting._WELCOME_KEY,
                guild.id,
                "roles",
                value=[str(r.id) for r in valid],
            )
            msg = "Current roles:\n"
            msg += " ".join([r.mention for r in valid]) or "**None**"
            if invalid:
                msg += "\nRemoved unassignable roles:\n"
                msg += " ".join([r.mention for r in invalid])
            await interaction.followup.send(
                embed=await success("Default roles saved", description=msg),
            )
        except Exception as ex:
            await interaction.followup.send(
                embed=await fail("Error while saving", description=str(ex)),
            )


async def setup(bot: SkyBot):
    await bot.add_cog(Greeting(bot))
