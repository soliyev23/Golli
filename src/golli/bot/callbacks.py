from aiogram.filters.callback_data import CallbackData


class LangCallback(CallbackData, prefix="lang"):
    """Til tanlash tugmasi: callback_data = "lang:<til kodi>"."""

    code: str


# DayCallback va UpcomingCallback tugmalari endi yuborilmaydi (kundan kunga o'tish olib
# tashlangan). Ular eski xabarlarda qolgan tugmalarni tanib, javobsiz qoldirmaslik uchun turibdi.


class DayCallback(CallbackData, prefix="day"):
    """Eski: o'yinlar ro'yxatida boshqa kunga o'tish, callback_data = "day:<YYYY-MM-DD>"."""

    day: str


class UpcomingCallback(CallbackData, prefix="upcoming"):
    """Eski: bitta kun ko'rinishidan asosiy ro'yxatga ("Yaqin o'yinlar") qaytish."""


class FavoritesCallback(CallbackData, prefix="fav"):
    """Sevimli klublar bosh sahifasi (ligalar ro'yxati)."""


class FavoriteListCallback(CallbackData, prefix="favl"):
    """Bitta liganing klublari ro'yxati."""

    competition: str
    page: int = 0


class FavoriteToggleCallback(CallbackData, prefix="favt"):
    """Klubni tanlash yoki olib tashlash; competition va page — ro'yxatni qayta chizish uchun."""

    competition: str
    page: int
    team_id: int
