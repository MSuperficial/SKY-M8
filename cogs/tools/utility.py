import io
import os
import re
from pathlib import Path
from typing import Any, TypeAlias

import aiohttp
import discord
from discord import Interaction, app_commands, ui
from discord.ext import commands
from PIL import Image, ImageChops, ImageOps, ImageSequence
from PIL.Image import Image as PImage
from webptools import webpmux_animate

from sky_m8 import AppUser, SkyM8

from ..base.views import ShortTextModal
from ..helper.embeds import fail

__all__ = ("Utility",)

NoSendChannel: TypeAlias = discord.ForumChannel | discord.CategoryChannel

_sticker_name_pattern = re.compile(r"^[a-zA-Z0-9_\-\. ]+$")


class Utility(commands.Cog):
    group_utility = app_commands.Group(
        name="utility",
        description="A group of useful commands.",
    )

    def __init__(self, bot: SkyM8):
        self.bot = bot
        self._img_types = ["jpg", "jpeg", "png", "webp", "gif", "tiff", "tif", "avif", "avifs"]  # fmt: skip

    def _is_mime_valid(self, mime: str):
        return mime in ["image/" + t for t in self._img_types]

    def _is_img_file_valid(self, file: discord.Attachment):
        mime = file.content_type
        suffix = Path(file.filename).suffix[1:]
        suffix_valid = suffix in self._img_types
        return mime is not None and self._is_mime_valid(mime) and suffix_valid

    @group_utility.command(
        name="mimic-stickers",
        description="Make a sticker-like image that can be added to fav GIFs.",
    )
    @app_commands.describe(
        file="Use image by uploading image file.",
        url="Use image by reading from url.",
        sticker_name="The displayed name of your sticker.",
        size="The size of made image in pixels, by default 320.",
    )
    async def mimic_stickers(
        self,
        interaction: Interaction,
        file: discord.Attachment | None = None,
        url: str | None = None,
        sticker_name: app_commands.Range[str, 0, 80] = "",
        size: app_commands.Range[int, 128, 1024] = 320,
    ):
        await interaction.response.defer(ephemeral=True)
        # 至少要指定一个参数
        if not file and not url:
            await interaction.followup.send(
                embed=fail(
                    "Both options are empty",
                    "You need to use either `file` or `url` option",
                )
            )
            return
        # 检查名称是否合法
        sticker_name = sticker_name.strip()
        if sticker_name and not re.match(_sticker_name_pattern, sticker_name):
            await interaction.followup.send(
                embed=fail(
                    "Invalid sticker name",
                    (
                        "Sticker name can only contain:\n"
                        "- alphanumeric characters\n"
                        "- underscores(`_`)\n"
                        "- dashes(`-`)\n"
                        "- dots(`.`)\n"
                        "- spaces(` `)"
                    ),
                )
            )
            return
        if file:
            # 检查图片文件格式
            if not self._is_img_file_valid(file):
                valid_types = ", ".join([f"`{t}`" for t in self._img_types])
                await interaction.followup.send(
                    embed=fail("Format not supported", "Only support " + valid_types),
                )
                return
            # 将文件读取到PIL Image对象
            try:
                buffer = io.BytesIO()
                await file.save(buffer)
                im = Image.open(buffer)
                im.filename = file.filename
            except Exception as ex:
                await interaction.followup.send(embed=fail("Invalid file", ex))
                return
        else:
            # 从url读取图片到PIL Image对象
            try:
                proxy = os.getenv("PROXY")
                async with aiohttp.ClientSession() as cs:
                    async with cs.get(url, proxy=proxy) as res:  # type: ignore
                        if res.status != 200:
                            await interaction.followup.send(
                                embed=fail(f"Request failed: {res.status}")
                            )
                            return
                        # 检查图片文件格式
                        if not self._is_mime_valid(res.content_type):
                            valid_types = ", ".join([f"`{t}`" for t in self._img_types])
                            await interaction.followup.send(
                                embed=fail(
                                    "Format not supported",
                                    "Only support " + valid_types,
                                ),
                            )
                            return
                        buffer = io.BytesIO(await res.read())
                        im = Image.open(buffer)
                        im.filename = res.url.name
            except Exception as ex:
                await interaction.followup.send(embed=fail("Invalid url", ex))
                return

        pending_view = ui.LayoutView(timeout=None)
        pending_view.add_item(
            ui.Container(
                ui.TextDisplay("### ⏳ Converting image..."),
                ui.TextDisplay("This may take a while"),
            )
        )
        await interaction.followup.send(view=pending_view)

        im.filename = im.filename or "mimic.webp"
        if not sticker_name:
            sticker_name = Path(im.filename).stem

        # 发送Sticker制作面板
        maker = MimicStickerMaker(size=size)
        view = MimicStickerMakerView(im, maker, sticker_name, interaction.user)
        msg_data = view.create_message()
        await interaction.edit_original_response(**msg_data)


class MimicStickerMaker:
    def __init__(self, *, size: int = 320):
        self.size = size

    def _make_singleframe(self, frame: PImage, duration: int, loop: int):
        # 如果输入是单帧图像，使用webpmux工具合成动画WebP文件，再读取到缓冲区
        # 因为在使用PIL保存WebP图片时，编码算法会将连续重复帧进行优化，导致无法生成多帧图片
        frame.save("_temp_frame.webp", quality=90, method=4)
        webpmux_animate(
            [f"_temp_frame.webp +{duration}+0+0+1+b"] * 2,
            "_temp_sticker.webp",
            str(loop),
            "0,0,0,0",
        )
        with open("_temp_sticker.webp", "rb") as f:
            buffer = io.BytesIO(f.read())
        try:
            os.remove("_temp_frame.webp")
            os.remove("_temp_sticker.webp")
        except Exception:
            pass
        return buffer

    def _make_multiframe(self, frames: list[PImage], duration: int, loop: int):
        # 如果输入是多帧图像，可以直接保存到缓冲区
        buffer = io.BytesIO()
        frames[0].save(
            buffer,
            format="WEBP",
            append_images=frames[1:],
            duration=duration,
            loop=loop,
            quality=90,
            method=4,
        )
        return buffer

    def _frames_identical(self, frames: list[PImage]):
        f0 = frames[0]
        for f in frames[1:]:
            diff = ImageChops.difference(f0, f)
            if diff.getbbox(alpha_only=False):
                return False
        return True

    def make_sticker(self, im: PImage):
        # 获取图片信息
        duration = im.info.get("duration", 500)
        loop = im.info.get("loop", 0)

        # 每一帧转换格式
        frames: list[PImage] = []
        for f in ImageSequence.Iterator(im):
            f = f.convert("RGBA")
            f = ImageOps.pad(f, (self.size, self.size))
            f = ImageOps.pad(f, (self.size * 2, self.size), centering=(0, 0))
            frames.append(f)

        # 如果所有帧都相同，则取第一帧并以单帧的方法做处理
        if len(frames) == 1 or self._frames_identical(frames):
            buffer = self._make_singleframe(frames[0], duration, loop)
        else:
            buffer = self._make_multiframe(frames, duration, loop)

        return buffer


class MimicStickerMakerView(ui.LayoutView):
    class SetNameButton(ui.Button["MimicStickerMakerView"]):
        def __init__(self, name: str):
            super().__init__(style=discord.ButtonStyle.secondary, label=name)

        async def callback(self, interaction: Interaction):
            assert self.view is not None
            modal = ShortTextModal(
                title="Set Sticker Name",
                label="Name",
                default=self.label,
                min_length=1,
                max_length=80,
            )
            await interaction.response.send_modal(modal)
            await modal.wait()

            name = modal.text.value.strip()
            if not name:
                return
            if not re.match(_sticker_name_pattern, name):
                await interaction.followup.send(
                    embed=fail(
                        "Invalid sticker name",
                        (
                            "Sticker name can only contain:\n"
                            "- alphanumeric characters\n"
                            "- underscores(`_`)\n"
                            "- dashes(`-`)\n"
                            "- dots(`.`)\n"
                            "- spaces(` `)"
                        ),
                    ),
                    ephemeral=True,
                )
                return

            self.label = self.view.sticker_name = name
            # make_new=False 仅改名不需要重新制作图片
            msg_data = self.view.create_message(make_new=False)
            await interaction.edit_original_response(**msg_data)

    class SetSizeButton(ui.Button["MimicStickerMakerView"]):
        def __init__(self, size: int):
            super().__init__(style=discord.ButtonStyle.secondary, label=str(size))

        async def callback(self, interaction: Interaction):
            assert self.view is not None
            modal = ShortTextModal(
                title="Set Image Size",
                label="Size",
                default=self.label,
                min_length=3,
                max_length=4,
            )
            await interaction.response.send_modal(modal)
            await modal.wait()

            try:
                size = int(modal.text.value)
            except ValueError:
                return
            if size < 128 or size > 1024:
                await interaction.followup.send(
                    embed=fail(
                        "Out of range",
                        "Image size must be between 128 and 1024",
                    ),
                    ephemeral=True,
                )
                return
            if self.label == str(size):
                return

            self.label = str(size)
            self.view.maker.size = size
            msg_data = self.view.create_message()
            await interaction.edit_original_response(**msg_data)

    class SendButton(ui.Button["MimicStickerMakerView"]):
        def __init__(self):
            super().__init__(style=discord.ButtonStyle.green, label="Send It!")

        async def callback(self, interaction: Interaction):
            ch = interaction.channel
            assert self.view is not None
            assert ch is not None and not isinstance(ch, NoSendChannel)
            await interaction.response.defer()
            msg_data = self.view.create_display_message()
            await ch.send(**msg_data)

    def __init__(
        self,
        image: PImage,
        maker: MimicStickerMaker,
        sticker_name: str,
        author: AppUser,
    ):
        super().__init__(timeout=None)
        self.image = image
        self.maker = maker
        self.buffer = io.BytesIO()
        self.sticker_name = sticker_name
        self.author = author

        self.preview_media = discord.MediaGalleryItem("attachment://" + self.filename)
        self.add_item(
            ui.Container(
                ui.TextDisplay("## Mimic Sticker Maker"),
                ui.Section(
                    ui.TextDisplay(f"### Making Sticker By\n> {author.mention}"),
                    ui.TextDisplay("-# You can use settings below to edit the image"),
                    accessory=ui.Thumbnail(author.display_avatar.url),
                ),
                ui.Separator(),
                ui.Section(
                    ui.TextDisplay(
                        "### Sticker Name\n-# The displayed name of your sticker"
                    ),
                    accessory=self.SetNameButton(sticker_name),
                ),
                ui.Separator(visible=False),
                ui.Section(
                    ui.TextDisplay(
                        "### Image Size\n-# Size of the image in pixels (between 128 and 1024)"
                    ),
                    accessory=self.SetSizeButton(maker.size),
                ),
                ui.Separator(spacing=discord.SeparatorSpacing.large),
                ui.MediaGallery(self.preview_media),
                ui.ActionRow(self.SendButton()),
            )
        )

    @property
    def filename(self):
        name = self.sticker_name.replace(" ", "_")
        return name + "_sticker.webp"

    def _get_file(self, *, make_new=True):
        if make_new:
            self.buffer = self.maker.make_sticker(self.image)
        self.buffer.seek(0)
        file = discord.File(self.buffer, self.filename)
        return file

    def create_message(self, *, make_new=True) -> dict[str, Any]:
        file = self._get_file(make_new=make_new)
        self.preview_media.media.url = file.uri
        return {
            "view": self,
            "attachments": [file],
        }

    def create_display_message(self) -> dict[str, Any]:
        if isinstance(self.author, discord.Member):
            color = self.author.top_role.color
        else:
            color = None

        embed = discord.Embed(
            color=color,
            title="Mimic Sticker",
        )
        embed.set_thumbnail(url=self.author.display_avatar.url)
        embed.add_field(
            name="Made By",
            value=f"> {self.author.mention}",
            inline=False,
        )
        embed.add_field(
            name="Sticker Name",
            value=f"> {self.sticker_name}",
            inline=False,
        )

        file = self._get_file(make_new=False)
        embed.set_image(url=file.uri)

        return {
            "embed": embed,
            "file": file,
        }
