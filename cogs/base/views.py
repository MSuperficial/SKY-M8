from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import discord
from discord import Interaction, Message, TextStyle, ui

from ..helper.embeds import fail
from ..helper.tzutils import TimezoneFinder, format_hint


class AutoDisableView(ui.View):
    def __init__(self, *, timeout: float | None = 180):
        super().__init__(timeout=timeout)
        self.response_msg: Message | None = None

    async def on_timeout(self) -> None:
        if self.response_msg:
            # 禁用所有UI
            for item in self.children:
                if isinstance(item, ui.DynamicItem):
                    item = item.item
                item.disabled = True  # type: ignore
            try:
                await self.response_msg.edit(view=self)
            except discord.HTTPException as ex:
                # 忽略webhook到期超时，和消息不存在（已被删除）异常
                if ex.status in [401, 404]:  # 应该是status而不是code！
                    pass
                else:
                    raise


class EmptyModal(ui.Modal):
    async def on_submit(self, interaction: Interaction):
        # 默认什么都不做，使用时通过对象实例取回文本框的内容
        await interaction.response.defer()


class ShortTextModal(EmptyModal):
    text = ui.TextInput(label="Text")

    def __init__(
        self,
        *,
        title: str,
        label: str,
        default: str | None = None,
        required: bool = True,
    ):
        self.text.label = label
        self.text.default = default
        self.text.required = required
        super().__init__(title=title)


class LongTextModal(EmptyModal):
    text = ui.TextInput(label="Text")

    def __init__(
        self,
        *,
        title: str,
        label: str,
        default: str | None = None,
        required: bool = True,
    ):
        self.text.style = TextStyle.long
        self.text.label = label
        self.text.default = default
        self.text.required = required
        super().__init__(title=title)


class DateModal(ui.Modal, title="Set Date"):
    text_year = ui.TextInput(label="Year (1~9999)", min_length=1, max_length=4)
    text_month = ui.TextInput(label="Month (1~12)", min_length=1, max_length=2)
    text_day = ui.TextInput(label="Day (1~31)", min_length=1, max_length=2)

    def __init__(self, *, dt: datetime) -> None:
        self.date = dt.date()
        self.valid = False
        self.text_year.default = str(dt.year)
        self.text_month.default = str(dt.month)
        self.text_day.default = str(dt.day)
        super().__init__()

    @property
    def year(self):
        return self.date.year

    @property
    def month(self):
        return self.date.month

    @property
    def day(self):
        return self.date.day

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer()
        try:
            self.date = date(
                int(self.text_year.value),
                int(self.text_month.value),
                int(self.text_day.value),
            )
            self.valid = True
        except ValueError:
            await interaction.followup.send(
                embed=fail("Invalid date"),
                ephemeral=True,
            )


class TimeModal(ui.Modal, title="Set Time"):
    text_hour = ui.TextInput(label="Hour (0~23 or 1~12AM/PM)", min_length=1, max_length=4)  # fmt: skip
    text_minute = ui.TextInput(label="Minute (0~59)", min_length=1, max_length=2)
    text_second = ui.TextInput(label="Second (0~59)", min_length=1, max_length=2)

    def __init__(self, *, dt: datetime) -> None:
        self.time = dt.time()
        self.valid = False
        self.text_hour.default = str(dt.hour)
        self.text_minute.default = str(dt.minute)
        self.text_second.default = str(dt.second)
        super().__init__()

    @property
    def hour(self):
        return self.time.hour

    @property
    def minute(self):
        return self.time.minute

    @property
    def second(self):
        return self.time.second

    def parse_hour(self, hour: str):
        try:
            return int(hour)  # 24小时制
        except ValueError:
            return datetime.strptime(hour, "%I%p").hour  # 12小时制

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer()
        try:
            self.time = time(
                self.parse_hour(self.text_hour.value),
                int(self.text_minute.value),
                int(self.text_second.value),
            )
            self.valid = True
        except ValueError:
            await interaction.followup.send(
                embed=fail("Invalid time"),
                ephemeral=True,
            )


class TimeZoneModal(ui.Modal, title="Set Time Zone"):
    text_tz = ui.TextInput(label="Time Zone")

    def __init__(self, *, dt: datetime):
        self.timezone = dt.tzinfo
        self.valid = False
        super().__init__()

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer()
        tz = self.text_tz.value
        # 尝试精确匹配时区
        if match := TimezoneFinder.exact_match(tz):
            self.timezone = ZoneInfo(match[0])
            self.valid = True
        else:
            # 时区无效则提示用户可能的匹配
            matches = TimezoneFinder.best_matches(tz, limit=5)
            hint = format_hint(matches)
            await interaction.followup.send(
                content=hint,
                embed=fail("Invalid time zone"),
                ephemeral=True,
            )
