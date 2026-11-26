from aiogram.filters import Filter
from aiogram.types import Message

from golli.i18n import I18n


class MenuButton(Filter):
    """Asosiy menyu tugmasi bosilganini taniydi — matn qaysi tilda bo'lishidan qat'i nazar."""

    def __init__(self, key: str) -> None:
        self._key = key

    async def __call__(self, message: Message, i18n: I18n) -> bool:
        return message.text in i18n.variants(self._key)
