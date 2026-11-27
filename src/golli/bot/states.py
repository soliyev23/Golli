"""Suhbat holatlari (FSM)."""

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Sevimli klublar bo'limiga qayerdan kirilgani: "Orqaga" tugmasi o'sha yerga qaytaradi.
FROM_SETTINGS = "settings"
FROM_START = "start"


class FavoritesFlow(StatesGroup):
    """Sevimli klublar bo'limi: pastki klaviaturadagi tugmalar shu holatga qarab o'qiladi."""

    # Ligalar ro'yxati.
    leagues = State()
    # Bitta liganing klublari: bosilgan tugma matni klub nomi deb o'qiladi. Qaysi liga ekani
    # holat ma'lumotida ("competition") turadi.
    clubs = State()


class TournamentsFlow(StatesGroup):
    """Turnirlar bo'limi: liga tugmasi bosilsa, shu liganing jadvali ko'rsatiladi."""

    leagues = State()
    # Pley-off bosqichi bor turnir tanlangan: "Jadval" yoki "Pley-off". Qaysi turnir ekani
    # holat ma'lumotida ("competition") turadi.
    sections = State()


async def open_favorites(state: FSMContext, origin: str) -> None:
    """Foydalanuvchini ligalar ro'yxatiga o'tkazadi va qayerdan kelganini eslab qoladi."""
    await state.set_state(FavoritesFlow.leagues)
    await state.set_data({"origin": origin})
