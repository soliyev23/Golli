"""Bot kuzatadigan turnirlar. Tartib — ro'yxatlarda ko'rsatish tartibi.

Yangi turnir qo'shish uchun: shu yerga kod, provayder adapteriga uning ID'si,
locales/*.ftl fayllariga "competition-<kod>" nomi qo'shiladi.
"""

COMPETITIONS: tuple[str, ...] = ("ucl", "epl", "laliga")

# Klub tanlash ro'yxatiga faqat asosiy bosqich ishtirokchilari kiradi: Chempionlar ligasida
# saralash bosqichida chiqib ketgan o'nlab klublar bor. Qiymat — provayder beradigan
# tur nomining boshlanishi (matches.round).
MAIN_STAGE_ROUND_PREFIX: dict[str, str] = {"ucl": "League Stage"}

# Pley-off bosqichlari: provayder (Highlightly) bergan tur nomi (matches.round) -> bosqich kodi.
# Kodlar matn kalitlarida ishlatiladi ("stage-<kod>"). Chempionlar ligasining 9–24-o'rinlar
# o'ynaydigan pley-off bosqichini provayder "Round of 32" deb ataydi; avgustdagi saralash
# pley-offi ("Play-offs") bu yerga kirmaydi.
KNOCKOUT_STAGES: dict[str, dict[str, str]] = {
    "ucl": {
        "Round of 32": "playoff",
        "Knockout Round Play-offs": "playoff",
        "Round of 16": "round16",
        "Quarter-finals": "quarter",
        "Semi-finals": "semi",
        "Final": "final",
    },
}
# Bosqichlar ko'rsatish tartibida: eng so'nggisi (final) tepada.
STAGE_ORDER: tuple[str, ...] = ("final", "semi", "quarter", "round16", "playoff")
# Ikki o'yindan iborat bosqichlar: g'olib ikki o'yin yig'indisi bo'yicha aniqlanadi.
TWO_LEGGED_STAGES = frozenset({"playoff", "round16", "quarter", "semi"})


def knockout_stage(competition: str, round_name: str | None) -> str | None:
    """Pley-off bosqichi kodi; oddiy tur (liga o'yini) uchun None."""
    return KNOCKOUT_STAGES.get(competition, {}).get(round_name or "")
