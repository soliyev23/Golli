"""Matnlar koddan ajratilgan: har bir til uchun locales/<til>.ftl (Fluent) fayli.

Yangi til qo'shish uchun shu papkaga yangi .ftl faylini qo'yish kifoya.
Barcha fayllar bot ishga tushganda bir marta xotiraga o'qiladi; xabar yuborishda
diskka ham, bazaga ham murojaat bo'lmaydi.
"""

import logging
from pathlib import Path

from fluent.runtime import FluentBundle, FluentResource

logger = logging.getLogger(__name__)

LOCALES_DIR = Path(__file__).parent / "locales"

# Til tanlash tugmalari shu tartibda chiqadi; ro'yxatda yo'q tillar oxiridan qo'shiladi.
PREFERRED_ORDER = ("uz", "ru", "en")


def _order(locale: str) -> tuple[int, str]:
    position = PREFERRED_ORDER.index(locale) if locale in PREFERRED_ORDER else len(PREFERRED_ORDER)
    return position, locale


class I18n:
    def __init__(self, default_locale: str = "uz", locales_dir: Path = LOCALES_DIR) -> None:
        self._bundles: dict[str, FluentBundle] = {}
        for path in sorted(locales_dir.glob("*.ftl"), key=lambda p: _order(p.stem)):
            # use_isolating=False: aks holda Fluent o'zgaruvchilar atrofiga ko'rinmas
            # Unicode belgilarini qo'shadi va ular Telegram xabarida ortiqcha.
            bundle = FluentBundle([path.stem], use_isolating=False)
            bundle.add_resource(FluentResource(path.read_text(encoding="utf-8")))
            self._bundles[path.stem] = bundle
        if default_locale not in self._bundles:
            raise ValueError(f"Asosiy til fayli topilmadi: {locales_dir / default_locale}.ftl")
        self.default_locale = default_locale
        self._variants: dict[str, frozenset[str]] = {}

    @property
    def locales(self) -> tuple[str, ...]:
        return tuple(self._bundles)

    def resolve_locale(self, locale: str | None) -> str:
        """Til tanlanmagan yoki qo'llab-quvvatlanmasa, asosiy tilga qaytadi."""
        return locale if locale in self._bundles else self.default_locale

    def translate(self, locale: str, key: str, /, **kwargs: object) -> str:
        # Kalit tanlangan tilda bo'lmasa, asosiy tildan olinadi.
        for name in dict.fromkeys((locale, self.default_locale)):
            bundle = self._bundles.get(name)
            if bundle is None or not bundle.has_message(key):
                continue
            value, errors = bundle.format_pattern(bundle.get_message(key).value, kwargs)
            for error in errors:
                logger.warning("Tarjimada xato: til=%s kalit=%s: %r", name, key, error)
            return value
        raise KeyError(f"Tarjima kaliti topilmadi: {key}")

    def translator(self, locale: str | None) -> "Translator":
        return Translator(self, self.resolve_locale(locale))

    def in_all_locales(self, key: str) -> list[str]:
        """Kalitning har bir tildagi matni, tillar tartibida."""
        return [self.translate(locale, key) for locale in self._bundles]

    def variants(self, key: str) -> frozenset[str]:
        """Kalitning barcha tillardagi matnlari — menyu tugmasini tanib olish uchun."""
        if key not in self._variants:
            self._variants[key] = frozenset(self.in_all_locales(key))
        return self._variants[key]


class Translator:
    """Bitta tilga bog'langan tarjimon: t("kalit", name=...)."""

    def __init__(self, i18n: I18n, locale: str) -> None:
        self._i18n = i18n
        self.locale = locale

    def __call__(self, key: str, /, **kwargs: object) -> str:
        return self._i18n.translate(self.locale, key, **kwargs)
