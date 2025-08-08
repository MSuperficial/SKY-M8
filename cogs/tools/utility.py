import io
import os
from pathlib import Path
from typing import Any

import aiohttp
import discord
from discord import ButtonStyle, Interaction, app_commands, ui
from discord.ext import commands
from PIL import Image, ImageOps, ImageSequence
from webptools import webpmux_animate

from sky_m8 import SkyM8

from ..helper.embeds import fail


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
        description="Create a sticker-like image that can be added to fav GIFs.",
    )
    @app_commands.describe(
        file="Use image by uploading image file.",
        url="Use image by reading from url.",
        size="The size of created image in pixels, by default 320.",
    )
    async def mimic_stickers(
        self,
        interaction: Interaction,
        file: discord.Attachment | None = None,
        url: str | None = None,
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

        await interaction.followup.send(
            embed=discord.Embed(
                title="⏳ Converting image...",
                description="This may take a while.",
            ),
        )

        # 获取图片信息
        duration = im.info.get("duration", 500)
        loop = im.info.get("loop", 0)
        filename = im.filename or "mimic.webp"
        filename = Path(filename).stem + "_sticker.webp"

        # 每一帧转换格式
        frames: list[Image.Image] = []
        for f in ImageSequence.Iterator(im):
            f = f.convert("RGBA")
            f = ImageOps.pad(f, (size, size))
            f = ImageOps.pad(f, (size * 2, size), centering=(0, 0))
            frames.append(f)

        if len(frames) == 1:
            # 如果原图是单帧图像，使用webpmux工具合成动画WebP文件，再读取到缓冲区
            # 因为在使用PIL保存WebP图片时，编码算法会将连续重复帧进行优化，导致无法生成多帧图片
            frames[0].save("_temp_frame.webp", quality=90, method=4)
            webpmux_animate(
                [f"_temp_frame.webp +{duration}+0+0+1+b"] * 2,
                "_temp_sticker.webp",
                loop,
                "0,0,0,0",
            )
            with open("_temp_sticker.webp", "rb") as f:
                buffer = io.BytesIO(f.read())
            try:
                os.remove("_temp_frame.webp")
                os.remove("_temp_sticker.webp")
            except Exception:
                pass
        else:
            # 如果原图是多帧图像，可以直接保存到缓冲区
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

        # 关闭图像
        im.close()
        # 发送转换得到的WebP动画图片
        view = MimicStickerView(buffer, filename, interaction.user)
        msg_data = view.create_message()
        await interaction.edit_original_response(**msg_data, embed=None, view=view)


class MimicStickerView(ui.View):
    def __init__(
        self,
        buffer: io.BufferedIOBase,
        filename: str,
        author: discord.User | discord.Member,
    ):
        super().__init__(timeout=None)
        self.buffer = buffer
        self.filename = filename
        self.author = author

    def create_message(self) -> dict[str, Any]:
        self.buffer.seek(0)
        file = discord.File(self.buffer, self.filename)
        return {
            "content": "**Conversion successful!**",
            "attachments": [file],
        }

    @ui.button(label="Send Image", style=ButtonStyle.success)
    async def send(self, interaction: Interaction, button):
        await interaction.response.defer()
        self.buffer.seek(0)
        file = discord.File(self.buffer, self.filename)
        await interaction.channel.send(  # type: ignore
            content=f"**Mimic sticker created by {self.author.mention}**",
            file=file,
        )
