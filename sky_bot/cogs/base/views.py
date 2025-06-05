from discord import Interaction, TextStyle, ui


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
