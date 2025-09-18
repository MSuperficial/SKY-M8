from typing import cast

import discord
from discord import ButtonStyle, Interaction, app_commands, ui
from discord.ext import commands
from discord.utils import find

from ..base.views import LongTextModal, ShortTextModal
from ..helper.converters import MessageTransformer
from ..helper.embeds import fail, success

__all__ = ("RoleManager",)


class RoleManager(commands.Cog):
    group_autoroles = app_commands.Group(
        name="autoroles",
        description="Commands for Autoroles setup and editting.",
        allowed_contexts=app_commands.AppCommandContext(dm_channel=False),
        allowed_installs=app_commands.AppInstallationType(user=False),
        default_permissions=discord.Permissions(manage_roles=True),
    )

    def __init__(self, bot):
        self.bot = bot

    @group_autoroles.command(
        name="setup",
        description="Setup Autoroles message and send to current channel.",
    )
    async def autoroles_setup(self, interaction: discord.Interaction):
        view = AutoRolesSetupView()
        await interaction.response.send_message(
            view=view,
            ephemeral=True,
        )

    @group_autoroles.command(
        name="edit",
        description="Edit an existing Autoroles message.",
    )
    @app_commands.describe(message="ID or link of the message.")
    async def autoroles_edit(
        self,
        interaction: discord.Interaction,
        message: app_commands.Transform[discord.Message, MessageTransformer],
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            view = AutoRolesSetupView.parse_message(message)
        except Exception:
            await interaction.followup.send(embed=fail("Invalid message"))
            return
        await interaction.followup.send(view=view)


class AutoRolesSetupView(ui.LayoutView):
    def __init__(
        self,
        *,
        description: str = "## Autoroles",
        roles: list[tuple[discord.Role, str]] | None = None,
        existing_msg: discord.Message | None = None,
    ):
        super().__init__(timeout=900)
        self.roles = [] if roles is None else roles
        self._existing_msg = existing_msg

        self.text_description = ui.TextDisplay(description)
        self.text_roles_description = ui.TextDisplay(self.roles_content)
        self.btn_set_description = self.SetDescriptionButton()
        self.sel_select_role = self.SelectRoleSelect()
        self.btn_edit_role = self.EditRoleButton()
        self.btn_remove_role = self.RemoveRoleButton()
        self.btn_done = self.DoneButon()

        container = ui.Container(
            self.text_description,
            ui.Separator(spacing=discord.SeparatorSpacing.large),
            self.text_roles_description,
        )
        self.add_item(container)
        self.add_item(ui.ActionRow(self.btn_set_description))
        self.add_item(ui.ActionRow(self.sel_select_role))
        self.add_item(ui.ActionRow(self.btn_edit_role, self.btn_remove_role, self.btn_done))

    @classmethod
    def parse_message(cls, message: discord.Message):
        assert message.guild is not None
        if len(message.embeds) > 0:
            # backward compatibility
            embed = message.embeds[0]
            text = cast(str, embed.description)
            sep = text.rfind("\n\n")
            description = text[:sep]
            roles_description = text[sep + 2 :]
        elif len(message.components) > 0:
            view = AutoRolesView.from_message(message)
            text_description = cast(ui.TextDisplay, view.find_item(101))
            text_roles_description = cast(ui.TextDisplay, view.find_item(102))
            description = text_description.content
            roles_description = text_roles_description.content
        else:
            raise ValueError()

        lines = [line.split(" - ") for line in roles_description.splitlines()]
        lines = [(int(r[0].strip("<@&>")), r[1]) for r in lines]
        roles: list[tuple[discord.Role, str]] = []
        for id, desc in lines:
            if role := message.guild.get_role(id):
                roles.append((role, desc))
        instance = cls(description=description, roles=roles, existing_msg=message)
        if len(roles) > 0:
            instance.btn_done.disabled = False
        return instance

    @property
    def roles_content(self):
        if len(self.roles) == 0:
            return "*Select role to add/edit/remove*"
        content = "\n".join([f"{r.mention} - {d}" for r, d in self.roles])
        return content

    def _push(self, role: discord.Role, description: str):
        self.roles.append((role, description))
        self.text_roles_description.content = self.roles_content
        self.btn_edit_role.disabled = False
        self.btn_remove_role.disabled = False
        self.btn_done.disabled = False

    def _get(self, role: discord.Role):
        item = find(lambda r: r[1][0] == role, enumerate(self.roles))
        item = (item[0], *item[1]) if item else None
        return item

    def _remove(self, role: discord.Role):
        item = self._get(role)
        if item:
            self.roles.pop(item[0])
            self.text_roles_description.content = self.roles_content
            self.btn_edit_role.disabled = True
            self.btn_remove_role.disabled = True
            if len(self.roles) == 0:
                self.btn_done.disabled = True

    async def _update_message(self, interaction: Interaction):
        try:
            await interaction.edit_original_response(view=self)
        except Exception as ex:
            await interaction.followup.send(embed=fail("Error", ex), ephemeral=True)

    class SetDescriptionButton(ui.Button["AutoRolesSetupView"]):
        def __init__(self):
            super().__init__(style=ButtonStyle.secondary, label="Set Description")

        def max_length(self):
            assert self.view is not None
            other = self.view.content_length() - len(self.view.text_description.content)
            return 4000 - other

        async def callback(self, interaction: Interaction):
            assert self.view is not None
            modal = LongTextModal(
                title="Set Autoroles Description",
                label="Description",
                description="Explain what are these roles related to, or what do they allow members to do",
                default=self.view.text_description.content,
                max_length=self.max_length(),
            )
            await interaction.response.send_modal(modal)
            await modal.wait()
            self.view.text_description.content = modal.text.value
            await self.view._update_message(interaction)

    class SelectRoleSelect(ui.RoleSelect["AutoRolesSetupView"]):
        def __init__(self):
            super().__init__(placeholder="Select role to add/edit/remove")

        def max_length(self, role: discord.Role):
            assert self.view is not None
            additional = len(f"\n{role.mention} - ")
            return 4000 - self.view.content_length() - additional

        async def callback(self, interaction: Interaction):
            assert self.view is not None
            role = self.values[0]
            existing_role = find(lambda r: r[0] == role, self.view.roles)
            # 如果选中已经存在的角色，则仅启用编辑、移除按钮，以供用户后续操作
            if existing_role:
                self.view.btn_edit_role.disabled = False
                self.view.btn_remove_role.disabled = False
                await interaction.response.edit_message(view=self.view)
                return

            # 限制最大角色数量为25
            if len(self.view.roles) >= 25:
                self.view.btn_edit_role.disabled = True
                self.view.btn_remove_role.disabled = True
                await interaction.response.edit_message(view=self.view)
                await interaction.followup.send(
                    embed=fail("Cannot add over 25 roles per message"),
                    ephemeral=True,
                )
                return
            # 不可添加bot无法分配的角色
            if not role.is_assignable():
                self.view.btn_edit_role.disabled = True
                self.view.btn_remove_role.disabled = True
                await interaction.response.edit_message(view=self.view)
                await interaction.followup.send(
                    embed=fail("Role is not assignable by me"),
                    ephemeral=True,
                )
                return
            # 判断文本长度是否超限
            max_length = self.max_length(role)
            if max_length < 1:
                self.view.btn_edit_role.disabled = True
                self.view.btn_remove_role.disabled = True
                await interaction.response.edit_message(view=self.view)
                await interaction.followup.send(
                    embed=fail("Reached maximum content length"),
                    ephemeral=True,
                )
                return

            # 如果选中不存在的角色，则弹出窗口设置角色描述，之后启用编辑，移除按钮
            modal = ShortTextModal(
                title="Provide Role Description",
                label="Role Description",
                description="Additional information about this role",
                max_length=max_length,
            )
            await interaction.response.send_modal(modal)
            await modal.wait()
            self.view._push(role, modal.text.value)
            await self.view._update_message(interaction)

    class EditRoleButton(ui.Button["AutoRolesSetupView"]):
        def __init__(self):
            super().__init__(style=ButtonStyle.secondary, label="Edit", disabled=True)

        def max_length(self, desc: str):
            assert self.view is not None
            other = self.view.content_length() - len(desc)
            return 4000 - other

        async def callback(self, interaction: Interaction):
            assert self.view is not None
            role = self.view.sel_select_role.values[0]
            if (item := self.view._get(role)) is None:
                await interaction.response.defer()
                return
            index, _, desc = item
            modal = ShortTextModal(
                title="Provide Role Description",
                label="Role Description",
                description="Additional information about this role",
                default=desc,
                max_length=self.max_length(desc),
            )
            await interaction.response.send_modal(modal)
            await modal.wait()
            self.view.roles[index] = (role, modal.text.value)
            self.view.text_roles_description.content = self.view.roles_content
            await self.view._update_message(interaction)

    class RemoveRoleButton(ui.Button["AutoRolesSetupView"]):
        def __init__(self):
            super().__init__(style=ButtonStyle.danger, label="Remove", disabled=True)

        async def callback(self, interaction: Interaction):
            assert self.view is not None
            await interaction.response.defer()
            role = self.view.sel_select_role.values[0]
            self.view._remove(role)
            await self.view._update_message(interaction)

    class DoneButon(ui.Button["AutoRolesSetupView"]):
        def __init__(self):
            super().__init__(style=ButtonStyle.success, label="Done", disabled=True)

        async def callback(self, interaction: Interaction):
            assert self.view is not None
            assert isinstance(interaction.channel, discord.TextChannel)
            await interaction.response.defer()
            view = AutoRolesView(self.view.text_description.content, self.view.roles)
            if self.view._existing_msg:
                # 如果有设置消息，则编辑先前的消息
                await self.view._existing_msg.edit(
                    embed=None,
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                # 使用channel.send发送新消息（新消息不会回复配置消息）
                await interaction.channel.send(
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )


class AutoRolesView(ui.LayoutView):
    def __init__(self, description: str, roles: list[tuple[discord.Role, str]]):
        super().__init__(timeout=None)

        container = ui.Container(
            ui.TextDisplay(description, id=101),
            ui.Separator(spacing=discord.SeparatorSpacing.large),
            ui.TextDisplay("\n".join([f"{r.mention} - {d}" for r, d in roles]), id=102),
        )
        self.add_item(container)
        self.add_item(ui.ActionRow(self.AutoRoleSelect(roles)))

    class AutoRoleSelect(ui.Select["AutoRolesView"]):
        def __init__(self, roles: list[tuple[discord.Role, str]]):
            super().__init__(
                custom_id="autoroles",
                placeholder="Select role to add/remove",
                min_values=0,
                max_values=1,
                options=[discord.SelectOption(label=r.name, value=str(r.id)) for r, d in roles],
            )

        async def callback(self, interaction: Interaction):
            assert interaction.guild is not None
            assert isinstance(interaction.user, discord.Member)
            await interaction.response.defer()

            if len(self.values) == 0:
                return
            role_id = int(self.values[0])
            role = interaction.guild.get_role(role_id)
            if role is None:
                await interaction.followup.send(
                    embed=fail(f"Role {role_id} does not exist"),
                    ephemeral=True,
                )
                return

            try:
                member = interaction.user
                # 如果成员已有角色则移除，没有角色则添加
                if member.get_role(role.id):
                    await member.remove_roles(role, reason="Autoroles")
                    await interaction.followup.send(
                        embed=success("Removed role", role.mention),
                        ephemeral=True,
                    )
                else:
                    await member.add_roles(role, reason="Autoroles")
                    await interaction.followup.send(
                        embed=success("Added role", role.mention),
                        ephemeral=True,
                    )
            except Exception as ex:
                await interaction.followup.send(embed=fail("Error", ex), ephemeral=True)


async def setup(bot: commands.Bot):
    # 注册持久化view
    bot.add_view(AutoRolesView("", []))
    await bot.add_cog(RoleManager(bot))
