import io
import os
import re
from itertools import chain
from pathlib import Path
from typing import Any, Literal, TypeAlias, overload

import aiohttp
import discord
from discord import Interaction, app_commands, ui
from discord.ext import commands
from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageSequence
from PIL.Image import Image as PImage
from webptools import webpmux_animate

from sky_m8 import AppUser, SkyM8

from ..base.views import ShortTextModal
from ..emoji_manager import Emojis
from ..helper.embeds import fail, success

__all__ = ("Utility",)

NoSendChannel: TypeAlias = discord.ForumChannel | discord.CategoryChannel

_sticker_name_pattern = re.compile(r"^[a-zA-Z0-9_\-\. ]{1,32}$")


class StickerPadding:
    _padding_options = [
        {
            "name": f"{v}%",
            "value": v / 100,
            "description": {0: "No Padding", 5: "Zoom Out", -5: "Zoon In"}.get(v),
            "default": v == 0,
        }
        for v in chain(range(0, 55, 5), range(-5, -55, -5))
    ]

    @classmethod
    def get_choices(cls):
        return [app_commands.Choice(name=o["name"], value=o["value"]) for o in cls._padding_options]

    @classmethod
    def get_options(cls):
        return [
            discord.SelectOption(
                label=o["name"],
                value=str(o["value"]),
                description=o["description"],
                default=o["default"],
            )
            for o in cls._padding_options
        ]


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
        size="The size of made sticker in pixels, by default 320.",
        auto_crop="Whether to crop empty region around the image, by default True.",
        padding="Extra padding to image border, creating zoom in (negative) or out (positive) effect, by default 0% (no padding).",
    )
    @app_commands.choices(
        padding=StickerPadding.get_choices(),
    )
    async def mimic_stickers(
        self,
        interaction: Interaction,
        file: discord.Attachment | None = None,
        url: str | None = None,
        sticker_name: app_commands.Range[str, 0, 32] = "",
        size: app_commands.Range[int, 128, 1024] = 320,
        auto_crop: bool = True,
        padding: app_commands.Range[float, -0.5, 0.5] = 0.0,
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
            sticker_name = Path(im.filename).stem[:32]

        # 发送Sticker制作面板
        maker = MimicStickerMaker(
            size=size,
            auto_crop=auto_crop,
            padding=padding,
        )
        view = MimicStickerMakerView(im, maker, sticker_name, interaction.user)
        msg_data = view.create_message()
        await interaction.edit_original_response(**msg_data)


class MimicStickerMaker:
    def __init__(
        self,
        *,
        size: int = 320,
        auto_crop: bool = True,
        padding: float = 0.0,
    ):
        self.size = size
        self.auto_crop = auto_crop
        self.padding = padding

    def _get_bbox(self, im: PImage):
        # 计算多帧图像共同的包围框，只考虑透明通道
        # 不含透明通道直接返回完整大小，避免getbbox加载图像
        if not im.has_transparency_data:
            return (int(0), int(0), im.size[0], im.size[1])

        bboxes: list[tuple[int, int, int, int]] = []
        for f in ImageSequence.Iterator(im):
            f = f.convert("RGBA").getchannel("A")
            # 形态学开运算，移除透明通道中的噪声
            f = f.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))
            b = f.getbbox()
            if b is not None:
                bboxes.append(b)
        im.seek(0)
        if len(bboxes) == 0:
            return None

        x0, y0, x1, y1 = list(zip(*bboxes))
        bbox: tuple[int, int, int, int] = min(x0), min(y0), max(x1), max(y1)
        return bbox

    def _make_singleframe(self, frame: PImage, duration: int, loop: int):
        # 如果输入是单帧图像，使用webpmux工具合成动画WebP文件，再读取到缓冲区
        # 因为在使用PIL保存WebP图片时，编码算法会将连续重复帧进行优化，导致无法生成多帧图片
        frame.save("_temp_frame.webp", quality=90, method=4)
        # +duration+offset_x+offset_y+dispose+blend
        # dispose 0: NONE 1: BACKGROUND
        # blend +b: BLEND -b: NO_BLEND
        webpmux_animate(
            [f"_temp_frame.webp +{duration}+0+0+1+b"] * 2,
            "_temp_sticker.webp",
            loop=str(loop),
            bgcolor="0,0,0,0",
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

    def _make_staticframe(self, frame: PImage):
        # 用于创建单帧缩略图
        buffer = io.BytesIO()
        frame.save(
            buffer,
            format="WEBP",
            quality=90,
            method=4,
        )
        return buffer

    def _frames_identical(self, frames: list[PImage]):
        f0 = frames[0]
        for f in frames[1:]:
            diff = ImageChops.difference(f0, f)
            # 设置alpha_only=False，需要对比所有通道而非只有透明通道
            if diff.getbbox(alpha_only=False):
                return False
        return True

    # fmt: off
    @overload
    def make_sticker(self, im: PImage) -> io.BytesIO: ...
    @overload
    def make_sticker(self, im: PImage, *, thumbnail: Literal[False]) -> io.BytesIO: ...
    @overload
    def make_sticker(self, im: PImage, *, thumbnail: Literal[True]) -> tuple[io.BytesIO, io.BytesIO]: ...
    # fmt: on

    def make_sticker(self, im: PImage, *, thumbnail: bool = False):
        # 获取图片信息
        duration = im.info.get("duration", 500)
        loop = im.info.get("loop", 0)
        bbox = (0, 0, im.size[0], im.size[1])

        # 自动裁剪参数
        if self.auto_crop:
            bbox = self._get_bbox(im) or bbox

        # padding参数
        full_box = bbox  # full_box：padding后的完整图像区域
        if self.padding != 0:
            x0, y0, x1, y1 = full_box
            w, h = x1 - x0, y1 - y0
            # 计算padding对应的缩放系数并应用到full_box
            factor = 1 / (1 - self.padding) if self.padding >= 0 else 1 + self.padding
            w_diff, h_diff = [(s * factor - s) / 2 for s in (w, h)]
            full_box = x0 - w_diff, y0 - h_diff, x1 + w_diff, y1 + h_diff
            # 对于放大的情况，需要计算正确的宽和高
            if self.padding < 0:
                sx0, sy0, sx1, sy1 = full_box
                sw, sh = sx1 - sx0, sy1 - sy0
                if sw > sh:
                    correct_h = min(h, sw)
                    diff = (correct_h - sh) / 2
                    full_box = sx0, sy0 - diff, sx1, sy1 + diff
                else:
                    correct_w = min(w, sh)
                    diff = (correct_w - sw) / 2
                    full_box = sx0 - diff, sy0, sx1 + diff, sy1

        # 每一帧转换格式
        frames: list[PImage] = []
        tn_frames: list[PImage] = []
        for f in ImageSequence.Iterator(im):
            # 转换为RGBA（原图像可能是palette格式图像，不适合进行插值运算）
            f = f.convert("RGBA")
            # padding + resize 到目标尺寸
            f = f.crop(full_box)
            f = ImageOps.pad(f, (self.size, self.size))
            # 创建缩略图
            if thumbnail:
                tn = f.resize((128, 128), resample=Image.Resampling.BICUBIC)
                tn_frames.append(tn)
            # 向右填充一倍尺寸的空白，使得贴纸在客户端上显示尺寸缩小
            f = ImageOps.pad(f, (self.size * 2, self.size), centering=(0, 0))
            frames.append(f)

        # 如果所有帧都相同，则取第一帧并以单帧的方法做处理
        tn_buffer = io.BytesIO()
        if len(frames) == 1 or self._frames_identical(frames):
            buffer = self._make_singleframe(frames[0], duration, loop)
            if thumbnail:
                tn_buffer = self._make_staticframe(tn_frames[0])
        else:
            buffer = self._make_multiframe(frames, duration, loop)
            if thumbnail:
                tn_buffer = self._make_multiframe(tn_frames, duration, loop)

        return (buffer, tn_buffer) if thumbnail else buffer


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
                max_length=32,
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
            # 设置make_new=False，仅改名不需要重新制作图片
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

    class CropToggleButton(ui.Button["MimicStickerMakerView"]):
        def __init__(self, value: bool):
            super().__init__(
                style=discord.ButtonStyle.secondary,
                label="Enabled" if value else "Disabled",
                emoji=Emojis("success", "✅") if value else Emojis("cancel", "➖"),
            )

        @property
        def value_text(self):
            assert self.view is not None
            value = self.view.maker.auto_crop
            return "Enabled" if value else "Disabled"

        @property
        def value_emoji(self):
            assert self.view is not None
            value = self.view.maker.auto_crop
            return Emojis("success", "✅") if value else Emojis("cancel", "➖")

        async def callback(self, interaction: Interaction):
            await interaction.response.defer()
            assert self.view is not None
            value = not self.view.maker.auto_crop

            self.view.maker.auto_crop = value
            self.label = self.value_text
            self.emoji = self.value_emoji
            msg_data = self.view.create_message()
            await interaction.edit_original_response(**msg_data)

    class PaddingSetting(ui.ActionRow["MimicStickerMakerView"]):
        def __init__(self, value: float):
            super().__init__()
            self._update_option(value)

        def _update_option(self, value: float):
            for option in self.select_padding.options:
                option.default = float(option.value) == value

        @ui.select(options=StickerPadding.get_options())
        async def select_padding(self, interaction: Interaction, select: ui.Select):
            await interaction.response.defer()
            assert self.view is not None
            value = float(select.values[0])

            self.view.maker.padding = value
            self._update_option(value)
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

    class CreateEmojiButton(ui.Button["MimicStickerMakerView"]):
        def __init__(self, *, disabled: bool):
            super().__init__(
                style=discord.ButtonStyle.blurple,
                label="Create Emoji",
                disabled=disabled,
            )

        async def callback(self, interaction: Interaction):
            await interaction.response.defer()
            user = interaction.user
            guild = interaction.guild
            assert guild is not None
            assert self.view is not None

            # 检查权限
            perm = guild.me.guild_permissions
            if not (perm.create_expressions and perm.manage_expressions):
                await interaction.followup.send(
                    embed=fail(
                        "Missing Permission",
                        f"Please add `Create Expressions` and `Manage Expressions` permission for {guild.me.mention} first.",
                    ),
                    ephemeral=True,
                )
                return

            if self.view.emoji is None:
                # 创建emoji
                data = self.view.emoji_buffer.getvalue()
                try:
                    self.view.emoji = await guild.create_custom_emoji(
                        name=self.view.emoji_name,
                        image=data,
                        reason=f"Created by {user.name}:{user.id}",
                    )
                    await interaction.followup.send(
                        content=str(self.view.emoji),
                        embed=success("Emoji created", f"`:{self.view.emoji.name}:`"),
                        ephemeral=True,
                    )
                except Exception as ex:
                    await interaction.followup.send(embed=fail("Error", ex), ephemeral=True)
                    return

                self.view.emoji_state = 0
                self.label = "Edit Emoji"
                await interaction.edit_original_response(view=self.view)
                return
            else:
                # 编辑emoji
                if self.view.emoji_state == 0:
                    # 无需更新
                    return
                elif self.view.emoji_state == 1:
                    # emoji改名
                    try:
                        self.view.emoji = await self.view.emoji.edit(
                            name=self.view.emoji_name,
                            reason=f"Edited by {user.name}:{user.id}",
                        )
                        await interaction.followup.send(
                            embed=success("Emoji name edited", f"`:{self.view.emoji.name}:`"),
                            ephemeral=True,
                        )
                        self.view.emoji_state = 0
                    except Exception as ex:
                        await interaction.followup.send(embed=fail("Error", ex), ephemeral=True)
                elif self.view.emoji_state == 2:
                    # emoji更新图像（先删除再创建）
                    try:
                        await self.view.emoji.delete(reason=f"Recreated by {user.name}:{user.id}")
                        data = self.view.emoji_buffer.getvalue()
                        self.view.emoji = await guild.create_custom_emoji(
                            name=self.view.emoji_name,
                            image=data,
                            reason=f"Recreated by {user.name}:{user.id}",
                        )
                        await interaction.followup.send(
                            content=str(self.view.emoji),
                            embed=success("Emoji updated", f"`:{self.view.emoji.name}:`"),
                            ephemeral=True,
                        )
                        self.view.emoji_state = 0
                    except Exception as ex:
                        await interaction.followup.send(embed=fail("Error", ex), ephemeral=True)

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

        self.emoji_buffer = io.BytesIO()
        self.emoji: discord.Emoji | None = None
        self.emoji_state = 2  # 0: 最新 1: 改名 2: 改图像

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
                    ui.TextDisplay("### Sticker Name\n-# The displayed name of your sticker"),
                    accessory=self.SetNameButton(sticker_name),
                ),
                ui.Separator(visible=False),
                ui.Section(
                    ui.TextDisplay(
                        "### Sticker Size\n-# Size of the sticker in pixels (between 128 and 1024)"
                    ),
                    accessory=self.SetSizeButton(maker.size),
                ),
                ui.Separator(visible=False),
                ui.Section(
                    ui.TextDisplay("### Auto Crop\n-# Crop empty region around the image"),
                    accessory=self.CropToggleButton(maker.auto_crop),
                ),
                ui.Separator(visible=False),
                ui.TextDisplay(
                    "### Padding\n-# Extra padding to image border, creating zoom in/out effect"
                ),
                self.PaddingSetting(maker.padding),
                ui.Separator(spacing=discord.SeparatorSpacing.large),
                ui.MediaGallery(self.preview_media),
                ui.ActionRow(
                    self.SendButton(),
                    # 是User类型说明不在服务器里，不能创建emoji
                    self.CreateEmojiButton(disabled=isinstance(author, discord.User)),
                ),
            )
        )

    @property
    def filename(self):
        name = self.sticker_name.replace(" ", "_")
        return name + "_sticker.webp"

    @property
    def emoji_name(self):
        trans = str.maketrans("-. ", "___")
        name = self.sticker_name.translate(trans)
        if len(name) < 2:
            name += "_"
        return name

    def _create_file(self, *, make_new=True):
        self.emoji_state = 1
        if make_new:
            self.buffer, self.emoji_buffer = self.maker.make_sticker(self.image, thumbnail=True)
            self.emoji_state = 2
        self.buffer.seek(0)
        self.emoji_buffer.seek(0)
        file = discord.File(self.buffer, self.filename)
        return file

    def create_message(self, *, make_new=True) -> dict[str, Any]:
        file = self._create_file(make_new=make_new)
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

        file = self._create_file(make_new=False)
        embed.set_image(url=file.uri)

        return {
            "embed": embed,
            "file": file,
        }
