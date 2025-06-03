import re

import discord
from discord import (
    ButtonStyle,
    Embed,
    Interaction,
    Message,
    TextStyle,
    app_commands,
    ui,
)
from discord.ext import commands
from discord.utils import MISSING, find

from ..embed_template import fail, success
from .helper.common import MessageTransformer

__all__ = ("RoleManager",)


class RoleManager(commands.Cog):
    group_autoroles = app_commands.Group(
        name="autoroles",
        description="Commands for Autoroles setup and editting.",
        allowed_contexts=app_commands.AppCommandContext(dm_channel=False),
        allowed_installs=app_commands.AppInstallationType(user=False),
    )

    def __init__(self, bot):
        self.bot = bot

    @group_autoroles.command(
        name="setup",
        description="Setup Autoroles message and send to current channel.",
    )
    async def autoroles_setup(self, interaction: discord.Interaction):
        embed = Embed(color=discord.Color.blue(), title="Setup Autoroles")
        view = AutoRolesSetupView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @group_autoroles.command(
        name="edit",
        description="Edit content of previous Autoroles message.",
    )
    @app_commands.describe(message="ID or link of the message.")
    async def autoroles_edit(
        self,
        interaction: discord.Interaction,
        message: app_commands.Transform[Message, MessageTransformer],
    ):
        if not message or len(message.embeds) == 0:
            await interaction.response.send_message(
                embed=await fail("Invalid message"),
                ephemeral=True,
            )
        await interaction.response.defer(ephemeral=True)
        view = AutoRolesSetupView.edit_message(message)
        embed = view.create_embed()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class AutoRolesSetupView(ui.View):
    class EmptyModal(ui.Modal):
        async def on_submit(self, interaction: Interaction):
            # 默认什么都不做，使用时通过对象实例取回文本框的内容
            await interaction.response.defer()

    class SetTitleModal(EmptyModal, title="Set Autoroles title"):
        text_title = ui.TextInput(label="Title (Optional)", required=False)

        def __init__(self, *, default: str = "") -> None:
            self.text_title.default = default
            super().__init__()

    class SetDescriptionModal(EmptyModal, title="Set Autoroles description"):
        text_description = ui.TextInput(
            label="Description (Optional)", style=TextStyle.long, required=False
        )

        def __init__(self, *, default: str = "") -> None:
            self.text_description.default = default
            super().__init__()

    class RoleDescriptionModal(EmptyModal, title="Provide role description"):
        description = ui.TextInput(label="Role Description")

        def __init__(self, *, default: str = "") -> None:
            self.description.default = default
            super().__init__()

    def __init__(self, *, timeout=600):
        super().__init__(timeout=timeout)
        self.title: str = ""
        self.description: str = ""
        self.roles: list[tuple[discord.Role, str]] = []
        self._editting: Message = MISSING

    @classmethod
    def edit_message(cls, message: Message):
        instance = cls()
        instance._editting = message
        embed = message.embeds[0]
        if embed.title:
            instance.title = embed.title
        desc: str = embed.description  # type: ignore
        if (sep := desc.rfind("\n\n")) != -1:
            instance.description = desc[:sep]
            desc = desc[sep + 2 :]
        lines = [line.split(" - ") for line in desc.splitlines()]
        lines = [(int(r[0].strip("<@&>")), r[1]) for r in lines]
        roles: list[tuple[discord.Role, str]] = []
        for id, description in lines:
            if role := message.guild.get_role(id):  # type:ignore
                roles.append((role, description))
        instance.roles = roles
        if len(roles) > 0:
            instance.done.disabled = False
        return instance

    def _push(self, role: discord.Role, description: str):
        self.roles.append((role, description))
        self.edit_role.disabled = False
        self.remove_role.disabled = False
        self.done.disabled = False

    def _get(self, role: discord.Role):
        item = find(lambda r: r[1][0] == role, enumerate(self.roles))
        return item

    def _remove(self, role: discord.Role):
        item = self._get(role)
        if item:
            self.roles.pop(item[0])
            self.edit_role.disabled = True
            self.remove_role.disabled = True
            if len(self.roles) == 0:
                self.done.disabled = True

    def create_embed(self):
        desc = self.description
        desc = (desc + "\n\n") if desc else desc
        desc += "\n".join([f"{r[0].mention} - {r[1]}" for r in self.roles])
        embed = Embed(color=discord.Color.blue(), title=self.title, description=desc)
        return embed

    def create_view(self):
        # 传入配置好的角色列表
        view = AutoRolesView([r[0] for r in self.roles])
        return view

    @ui.button(label="Set Title", style=ButtonStyle.secondary, row=0)
    async def set_title(self, interaction: Interaction, button: ui.Button):
        modal = self.SetTitleModal(default=self.title)
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.title = modal.text_title.value
        await interaction.edit_original_response(embed=self.create_embed())

    @ui.button(label="Set Description", style=ButtonStyle.secondary, row=0)
    async def set_description(self, interaction: Interaction, button: ui.Button):
        modal = self.SetDescriptionModal(default=self.description)
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.description = modal.text_description.value
        await interaction.edit_original_response(embed=self.create_embed())

    @ui.select(cls=ui.RoleSelect, placeholder="Select role to add/edit/remove", row=1)
    async def select_role(self, interaction: Interaction, select: ui.RoleSelect):
        role = select.values[0]
        existing_role = find(lambda r: r[0] == role, self.roles)
        # 如果选中已经存在的角色，则仅启用编辑，移除按钮，以供用户后续操作
        if existing_role:
            await interaction.response.defer()
            self.edit_role.disabled = False
            self.remove_role.disabled = False
            await interaction.edit_original_response(view=self)
            return
        # 如果选中不存在的角色，则弹出窗口设置角色描述，之后启用编辑，移除按钮
        modal = self.RoleDescriptionModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        self._push(role, modal.description.value)
        await interaction.edit_original_response(embed=self.create_embed(), view=self)

    @ui.button(label="Edit", style=ButtonStyle.secondary, disabled=True, row=2)
    async def edit_role(self, interaction: Interaction, button: ui.Button):
        """Edit selected role description."""
        role = self.select_role.values[0]
        index, (_, desc) = self._get(role)  # type: ignore
        modal = self.RoleDescriptionModal(default=desc)
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.roles[index] = (role, modal.description.value)
        await interaction.edit_original_response(embed=self.create_embed())

    @ui.button(label="Remove", style=ButtonStyle.danger, disabled=True, row=2)
    async def remove_role(self, interaction: Interaction, button: ui.Button):
        """Remove selected role."""
        await interaction.response.defer()
        role = self.select_role.values[0]
        self._remove(role)
        await interaction.edit_original_response(embed=self.create_embed(), view=self)

    @ui.button(label="Done", style=ButtonStyle.success, disabled=True, row=2)
    async def done(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer()
        if self._editting:
            # 如果有设置消息，则编辑先前的消息
            await self._editting.edit(
                embed=self.create_embed(),
                view=self.create_view(),
            )
        else:
            # 使用channel.send发送新消息（新消息不会回复配置消息）
            await interaction.channel.send(  # type: ignore
                embed=self.create_embed(),
                view=self.create_view(),
            )


class AutoRolesView(ui.View):
    # 继承DynamicItem以在运行时动态添加按钮
    class AutoRoleButton(
        ui.DynamicItem[ui.Button], template=r"autoroles:(?P<role_id>[0-9]+)"
    ):
        def __init__(self, role_id: int, role_name: str = ""):
            super().__init__(
                ui.Button(
                    style=ButtonStyle.primary,
                    label=role_name,
                    custom_id=f"autoroles:{role_id}",
                )
            )
            self.role_id = role_id

        @classmethod
        async def from_custom_id(cls, interaction, item, match: re.Match[str]):
            role_id = int(match["role_id"])
            return cls(role_id)

        async def callback(self, interaction: Interaction):
            await interaction.response.defer(ephemeral=True, thinking=True)
            role = interaction.guild.get_role(self.role_id)
            if not role:
                await interaction.followup.send(
                    embed=await fail(f"Role {self.role_id} does not exist"),
                )
                return
            member = interaction.user
            try:
                # 如果成员已有角色则移除，没有角色则添加
                if member.get_role(role.id):
                    await member.remove_roles(role, reason="Autoroles")
                    await interaction.followup.send(
                        embed=await success("Removed role", description=role.mention),
                    )
                else:
                    await member.add_roles(role, reason="Autoroles")
                    await interaction.followup.send(
                        embed=await success("Added role", description=role.mention),
                    )
            except discord.HTTPException as ex:
                await interaction.followup.send(
                    embed=await fail("Error in Autoroles", description=str(ex)),
                )

    def __init__(self, roles: list[discord.Role]):
        super().__init__(timeout=None)
        # 根据角色列表动态生成对应按钮
        for r in roles:
            self.add_item(self.AutoRoleButton(r.id, r.name))


async def setup(bot: commands.Bot):
    # 注册动态UI
    bot.add_dynamic_items(AutoRolesView.AutoRoleButton)
    await bot.add_cog(RoleManager(bot))
