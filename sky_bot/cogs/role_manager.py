import re

import discord
from discord import ButtonStyle, Embed, Interaction, TextStyle, app_commands, ui
from discord.ext import commands

from ..embed_template import fail, success

__all__ = ("RoleManager",)


class RoleManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command()
    async def autoroles(self, interaction: discord.Interaction):
        """Setup Autoroles message and send to current channel

        Parameters
        ----------
        interaction : discord.Interaction
        """
        embed = Embed(color=discord.Color.blue(), title="Setup Autoroles")
        view = AutoRolesSetupView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class AutoRolesSetupView(ui.View):
    class EmptyModal(ui.Modal):
        async def on_submit(self, interaction: Interaction):
            # 默认什么都不做，使用时通过对象实例取回文本框的内容
            await interaction.response.defer()

    class SetTitleModal(EmptyModal, title="Set Autoroles title"):
        text_title = ui.TextInput(label="Title (Optional)", required=False)

    class SetDescriptionModal(EmptyModal, title="Set Autoroles description"):
        text_description = ui.TextInput(
            label="Description (Optional)", style=TextStyle.long, required=False
        )

    class RoleDescriptionModal(EmptyModal, title="Provide role description"):
        description = ui.TextInput(label="Role Description")

    def __init__(self, *, timeout=600):
        super().__init__(timeout=timeout)
        self.title: str = ""
        self.description: str = ""
        self.roles: list[tuple[discord.Role, str]] = []

    def push(self, role: discord.Role, description: str):
        self.roles.append((role, description))
        if len(self.roles) == 1:
            self.remove_last.disabled = False
            self.done.disabled = False

    def pop(self):
        self.roles.pop()
        if len(self.roles) == 0:
            self.remove_last.disabled = True
            self.done.disabled = True

    def create_embed(self):
        desc = self.description
        desc = (desc + "\n\n") if desc else desc
        desc += "\n".join([f"{r[0].mention} - {r[1]}" for r in self.roles])
        embed = Embed(color=discord.Color.blue(), title=self.title, description=desc)
        return embed

    @ui.button(label="Set Title", style=ButtonStyle.secondary, row=0)
    async def set_title(self, interaction: Interaction, button: ui.Button):
        modal = self.SetTitleModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.title = modal.text_title.value
        await interaction.edit_original_response(embed=self.create_embed())

    @ui.button(label="Set Description", style=ButtonStyle.secondary, row=0)
    async def set_description(self, interaction: Interaction, button: ui.Button):
        modal = self.SetDescriptionModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.description = modal.text_description.value
        await interaction.edit_original_response(embed=self.create_embed())

    @ui.select(cls=ui.RoleSelect, placeholder="Select a role to add...", row=1)
    async def select_role(self, interaction: Interaction, select: ui.RoleSelect):
        role = select.values[0]
        if role in [r[0] for r in self.roles]:
            # 角色重复时发送提示并返回
            await interaction.response.send_message("Duplicated role!", ephemeral=True)
            return
        modal = self.RoleDescriptionModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.push(role, modal.description.value)
        await interaction.edit_original_response(embed=self.create_embed(), view=self)

    @ui.button(label="Remove Last", style=ButtonStyle.danger, disabled=True, row=2)
    async def remove_last(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer()
        self.pop()
        await interaction.edit_original_response(embed=self.create_embed(), view=self)

    @ui.button(label="Done", style=ButtonStyle.success, disabled=True, row=2)
    async def done(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer()
        # 使用channel.send发送新消息（不显示回复配置消息）
        await interaction.channel.send(
            embed=self.create_embed(),
            view=AutoRolesView([r[0] for r in self.roles]),  # 传入配置好的角色列表
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
