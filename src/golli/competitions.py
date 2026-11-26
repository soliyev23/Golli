"""Bot kuzatadigan turnirlar. Tartib — ro'yxatlarda ko'rsatish tartibi.

Yangi turnir qo'shish uchun: shu yerga kod, provayder adapteriga uning ID'si,
locales/*.ftl fayllariga "competition-<kod>" nomi qo'shiladi.
"""

COMPETITIONS: tuple[str, ...] = ("ucl", "epl", "laliga")

# Klub tanlash ro'yxatiga faqat asosiy bosqich ishtirokchilari kiradi: Chempionlar ligasida
# saralash bosqichida chiqib ketgan o'nlab klublar bor. Qiymat — provayder beradigan
# tur nomining boshlanishi (matches.round).
MAIN_STAGE_ROUND_PREFIX: dict[str, str] = {"ucl": "League Stage"}
