from aiogram.filters import Filter
from aiogram.types import Message

from golli.competitions import COMPETITIONS
from golli.i18n import I18n


class MenuButton(Filter):
    """Asosiy menyu tugmasi bosilganini taniydi — matn qaysi tilda bo'lishidan qat'i nazar."""

    def __init__(self, key: str) -> None:
        self._key = key

    async def __call__(self, message: Message, i18n: I18n) -> bool:
        return message.text in i18n.variants(self._key)


class LeagueButton(Filter):
    """Liga tugmasi (sevimli klublar bo'limida). Handlerga `competition` kodini uzatadi."""

    async def __call__(self, message: Message, i18n: I18n) -> bool | dict[str, str]:
        for competition in COMPETITIONS:
            if message.text in i18n.variants(f"competition-{competition}"):
                return {"competition": competition}
        return False
