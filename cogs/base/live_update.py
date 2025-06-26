import asyncio
import json
import os
from contextlib import suppress
from typing import Any, NamedTuple

import discord
from discord import Interaction, app_commands
from discord.ext import commands, tasks
from discord.utils import MISSING, get

from sky_bot import SkyBot
from utils.remote_config import remote_config

from ..helper.embeds import fail, success
from ..helper.formats import code_block
from ..helper.times import sky_time_now

__all__ = ("LiveUpdateCog",)


class LiveUpdateCog(commands.Cog):
    _WEBHOOKS_KEY = "liveUpdate.webhooks"
    _DISPLAY_NAME = "Live Update"
    _global_update_lock = asyncio.Lock()

    def __init_subclass__(
        cls,
        *,
        live_key: str,
        group_live_name: str,
        live_display_name: str,
        live_update_interval: dict[str, Any] = {},
        **kwargs,
    ):
        super().__init_subclass__(**kwargs)
        cls._WEBHOOKS_KEY = live_key
        cls._DISPLAY_NAME = live_display_name

        # 每个子类在初始化时需要创建以下对象新的实例
        # 否则会共用同一个实例可能导致问题

        # 创建新命令对象
        cls.live_setup = app_commands.Command(
            name="setup",
            description=f"Setup {live_display_name} live message in this server.",
            callback=cls._live_setup_impl,
        )
        app_commands.describe(
            channel="Where to send the live message.",
        )(cls.live_setup)
        cls.live_removve = app_commands.Command(
            name="remove",
            description=f"Remove {live_display_name} live message in this server.",
            callback=cls._live_remove_impl,
        )

        # 创建新命令组并添加命令
        cls.group_live = app_commands.Group(
            name=group_live_name,
            description=f"Commands to manage {live_display_name} live message.",
            allowed_contexts=app_commands.AppCommandContext(dm_channel=False),
            allowed_installs=app_commands.AppInstallationType(user=False),
        )
        cls.group_live.add_command(cls.live_setup)
        cls.group_live.add_command(cls.live_removve)

        # 创建新任务对象
        cls.update_live_msg = tasks.loop(
            **live_update_interval,
            name=f"update_live_msg[{live_display_name}]",
        )(cls.update_live_msg.coro)
        cls.update_live_msg.before_loop(cls._task_live_before)
        cls.update_live_msg.error(cls._task_live_error)

    def __init__(self, bot: SkyBot):
        self.bot = bot
        self.live_webhooks: list[LiveUpdateWebhook] = []
        self.last_msg_data: dict[str, Any] = {}
        self._live_lock = asyncio.Lock()

    async def cog_load(self):
        self.live_webhooks = await self.refresh_live_webhooks()
        self.update_live_msg.start()

    async def cog_unload(self):
        self.update_live_msg.cancel()

    async def refresh_live_webhooks(self):
        old_data = await remote_config.get_list(self._WEBHOOKS_KEY)
        old_data = [json.loads(d) for d in old_data]
        new_webhooks: list[LiveUpdateWebhook] = []
        bot_token = os.getenv("SKYBOT_TOKEN")
        for data in old_data:
            try:
                lw = await LiveUpdateWebhook.from_dict(data, self.bot, bot_token)
                # 如果live消息已经被删除，则也删除webhook并跳过
                if not lw.message:
                    await lw.webhook.delete(reason="Live message not found.")
                    continue
                new_webhooks.append(lw)
            except Exception:
                continue
        new_data = [w.to_dict() for w in new_webhooks]
        await remote_config.set_list(self._WEBHOOKS_KEY, new_data)
        return new_webhooks

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        async with self._live_lock:
            if lw := get(self.live_webhooks, message__id=payload.message_id):
                # 如果live消息被删除，则同时删除webhook
                try:
                    self.live_webhooks.remove(lw)
                    data = [w.to_dict() for w in self.live_webhooks]
                    await remote_config.set_list(self._WEBHOOKS_KEY, data)
                    with suppress(discord.NotFound):
                        await lw.webhook.delete(reason="Live message was deleted.")
                    print(
                        f"[{sky_time_now()}] {self._DISPLAY_NAME} live message removed.\n"
                        f"{lw.message.jump_url}."
                    )
                except Exception as ex:
                    print(f"[{sky_time_now()}] Error deleting live webhook: {ex}")

    async def _live_setup_impl(
        self,
        interaction: Interaction,
        channel: discord.TextChannel | None = None,  # type: ignore
    ):
        channel: discord.TextChannel = channel or interaction.channel  # type: ignore
        await interaction.response.defer(ephemeral=True)
        # 检查权限
        me = interaction.guild.me  # type: ignore
        if not channel.permissions_for(me).manage_webhooks:
            await interaction.followup.send(
                embed=fail(
                    "Missing permission",
                    f"Please add `Manage Webhooks` permission for {me.mention} first.",
                ),
            )
            return
        # 如果当前服务器已配置live消息则返回
        if lw := get(self.live_webhooks, message__guild=interaction.guild):
            await interaction.followup.send(
                embed=fail(
                    "Already setup",
                    f"{self._DISPLAY_NAME} live message already setup: {lw.message.jump_url}.",
                ),
            )
            return
        followup = await interaction.followup.send(
            embed=discord.Embed(
                title=f"⏳ Setting up {self._DISPLAY_NAME} live message...",
                description="This may take a while.",
            ),
            wait=True,
        )
        try:
            # 创建webhook
            user = interaction.user
            webhook = await channel.create_webhook(
                name=f"{self._DISPLAY_NAME} Live Update",
                avatar=await me.display_avatar.read(),
                reason=f"Setup by {user.name}:{user.id}.",
            )
            # 发送消息
            data = await self.get_live_message_data()
            message = await webhook.send(**data, wait=True)
            # 记录webhook和消息
            async with self._live_lock:
                live_webhook = LiveUpdateWebhook(webhook=webhook, message=message)
                await remote_config.append_list(self._WEBHOOKS_KEY, live_webhook.to_dict())  # fmt: skip
                self.live_webhooks.append(live_webhook)
            await followup.edit(
                embed=success(
                    "Success",
                    f"{self._DISPLAY_NAME} live message {message.jump_url} setup in {channel.mention}.",
                )
            )
            print(
                f"[{sky_time_now()}] {self._DISPLAY_NAME} live message setup by {user.name}:{user.id}.\n"
                f"{message.jump_url}."
            )
        except Exception as ex:
            await followup.edit(embed=fail("Error", ex))

    async def _live_remove_impl(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        # 如果当前服务器还未配置live消息则返回
        if not (lw := get(self.live_webhooks, message__guild=interaction.guild)):
            await interaction.followup.send(
                embed=fail(
                    "Not setup",
                    f"{self._DISPLAY_NAME} live message hasn't been setup in this server.",
                ),
            )
            return
        followup = await interaction.followup.send(
            embed=discord.Embed(
                title=f"⏳ Removing {self._DISPLAY_NAME} live message...",
                description="This may take a while.",
            ),
            wait=True,
        )
        try:
            user = interaction.user
            # 删除webhook和消息
            async with self._live_lock:
                # 锁内重新检查一次webhook是否存在，以防在获取锁之前被其他操作删除
                if lw := get(self.live_webhooks, message__guild=interaction.guild):
                    # 通过channel删除消息，避免webhook已被删掉的情况
                    await lw.message.channel.delete_messages([lw.message])  # type: ignore
                    with suppress(discord.NotFound):
                        await lw.webhook.delete(
                            reason=f"Removed by {user.name}:{user.id}."
                        )
                    self.live_webhooks.remove(lw)
                    data = [w.to_dict() for w in self.live_webhooks]
                    await remote_config.set_list(self._WEBHOOKS_KEY, data)
                    print(
                        f"[{sky_time_now()}] {self._DISPLAY_NAME} live message removed by {user.name}:{user.id}.\n"
                        f"{lw.message.jump_url}."
                    )
            await followup.edit(
                embed=success(f"{self._DISPLAY_NAME} live message removed")
            )
        except Exception as ex:
            await followup.edit(embed=fail("Error", ex))

    async def get_live_message_data(self, **kwargs) -> dict[str, Any]:
        """Get the live message data.

        Returns
        -------
        dict[str, Any]
            The live message data.

        Raises
        ------
        NotImplementedError
            If not implemented by subclass.
        """
        raise NotImplementedError()

    def check_need_update(self, data: dict[str, Any]) -> bool:
        """Check if the live message needs to be updated.

        Parameters
        ----------
        data : dict[str, Any]
            New live message data.

        Returns
        -------
        bool
            Whether the live message needs to be updated.
        """
        return True

    @tasks.loop()
    async def update_live_msg(self):
        # 生成消息数据
        data = await self.get_live_message_data()
        # 检查是否需要更新
        if not self.check_need_update(data):
            return
        # 如果没有配置live消息则跳过
        if not self.live_webhooks:
            print(f"[{sky_time_now()}] No {self._DISPLAY_NAME} live messages to update.")  # fmt: skip
            # 记录消息数据
            self.last_msg_data = data
            return
        # 依次更新所有消息
        errors = []
        # _global_update_lock 主要作用是在程序启动时全局限制编辑频率（所有子类范围内）
        # 而 _live_lock 主要是保护对 live_webhooks 属性的同步访问（某个子类范围内）
        async with self._global_update_lock:
            async with self._live_lock:
                for lw in self.live_webhooks:
                    try:
                        await lw.message.edit(**data)
                    except discord.HTTPException as ex:
                        errors.append(f"- Message {lw.message.jump_url}: {str(ex)}")
                    await asyncio.sleep(1)  # 降低编辑频率
        total = len(self.live_webhooks)
        success = total - len(errors)
        print(f"[{sky_time_now()}] Updated {self._DISPLAY_NAME} live message in {success}/{total} servers.")  # fmt: skip
        if errors:
            print("Errors occurred during update:")
            print(*errors, sep="\n")
        # 记录消息数据
        self.last_msg_data = data

    async def get_ready_for_live(self):
        """Stuff to do before live update task starts."""
        pass

    async def _task_live_before(self):
        # 等待客户端就绪
        await self.bot.wait_until_ready()
        # 先更新一次
        await self.update_live_msg()
        # 准备就绪
        await self.get_ready_for_live()

    async def _task_live_error(self, error):
        task_name = self.update_live_msg._name
        error_msg = (
            f"Error during task `{task_name}`: `{type(error).__name__}`\n"
            f"{code_block(error)}"
        )
        print(error_msg)
        await self.bot.owner.send(error_msg)


class LiveUpdateWebhook(NamedTuple):
    webhook: discord.Webhook
    message: discord.WebhookMessage

    @classmethod
    async def from_dict(cls, data: dict, client, bot_token):
        webhook = discord.Webhook.partial(
            int(data["id"]),
            data["token"],
            client=client,
            bot_token=bot_token,
        )
        webhook.proxy = os.getenv("PROXY")
        try:
            message = await webhook.fetch_message(int(data["messageId"]))
        except discord.NotFound:
            message = MISSING
        return cls(webhook=webhook, message=message)

    def to_dict(self):
        # 这里id转换为str是避免整型数值溢出导致传输过程中数据丢失
        return {
            "id": str(self.webhook.id),
            "token": self.webhook.token,
            "messageId": str(self.message.id),
        }
