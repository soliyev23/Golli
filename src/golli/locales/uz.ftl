# Golli — o'zbekcha matnlar (lotin).

## Buyruqlar ro'yxati (Telegram menyusida ko'rinadi)

cmd-start = Botni ishga tushirish
cmd-lang = Tilni o'zgartirish
cmd-help = Yordam

## Asosiy menyu tugmalari

menu-matches = ⚽ Yaqin o'yinlar
menu-recent = 🏁 Oxirgi o'yinlar
menu-tournaments = 🏆 Turnirlar
menu-favorites = ⭐ Sevimli klublar
menu-language = 🌐 Til
menu-settings = ⚙️ Sozlamalar
menu-back = ⬅️ Orqaga

## Til tanlash

lang-name = 🇺🇿 O'zbekcha
lang-choose = Tilni tanlang
lang-set = ✅ Til: O'zbekcha

## /start va /help

start-welcome =
    Assalomu alaykum, { $name }! 👋

    Men <b>Golli</b> — futbol muxlislari uchun botman.

    ⚽ Bugungi va yaqin kunlardagi o'yinlarni ko'rsataman
    ⭐ Sevimli klubingiz o'yini haqida eslataman
    🏁 O'yin tugagach, hisobni yuboraman

    Boshlash uchun pastdagi tugmalardan foydalaning.

help-text =
    <b>Golli nima qiladi?</b>

    ⚽ <b>Yaqin o'yinlar</b> — Chempionlar ligasi, APL va La Liga o'yinlari, Toshkent vaqti bilan.

    🏁 <b>Oxirgi o'yinlar</b> — oxirgi ikki o'yin kunining natijalari.

    🏆 <b>Turnirlar</b> — Chempionlar ligasi, APL va La Liga jadvallari.

    ⚙️ <b>Sozlamalar</b> — sevimli klublar va til.

    ⭐ <b>Sevimli klublar</b> — klub tanlang, uning o'yinlari haqida eslatib turaman:
    • o'yin kuni ertalab;
    • o'yinga 1 soat qolganda;
    • o'yin tugagach — yakuniy hisob.

    /start — asosiy menyu
    /lang — tilni o'zgartirish
    /help — shu yordam

## Umumiy javoblar

unknown-message = Tushunmadim. Pastdagi tugmalardan foydalaning 👇
menu-main = 🏠 Asosiy menyu
buttons-outdated = Bu tugmalar eskirgan. Pastdagi menyudan foydalaning.
choose-hint = Pastdagi tugmalardan tanlang 👇
settings-text =
    ⚙️ <b>Sozlamalar</b>

    Kerakli bo'limni tanlang 👇

## O'yinlar ro'yxati

competition-ucl = 🏆 Chempionlar ligasi
# Angliya bayrog'i (ko'rinmas belgilar ketma-ketligi, shuning uchun kod bilan yozilgan).
competition-epl = { "\U01F3F4\U0E0067\U0E0062\U0E0065\U0E006E\U0E0067\U0E007F" } APL
competition-laliga = 🇪🇸 La Liga

# Sana ko'rinishi (Unicode CLDR andozasi): 28-noyabr, shanba
date-format = d-MMMM, EEEE
matches-title-today = ⚽ <b>Bugun, { $date }</b>
matches-title-tomorrow = ⚽ <b>Ertaga, { $date }</b>
matches-title-yesterday = ⚽ <b>Kecha, { $date }</b>
matches-title-day = ⚽ <b>{ $date }</b>
matches-none = Bu kuni o'yin yo'q.
matches-none-upcoming = Yaqin kunlarda o'yin yo'q.
matches-none-recent = So'nggi kunlarda o'yin bo'lmadi.
matches-footer = 🕐 Vaqt — Toshkent bo'yicha
matches-live-note = 🔴 O'yin ketmoqda — hisob kechikib yangilanadi
status-postponed = ko'chirilgan
status-suspended = to'xtatilgan
status-cancelled = bekor qilingan
penalties = pen. { $home }:{ $away }

## Turnirlar va jadvallar

# Sana va vaqt ko'rinishi (Unicode CLDR andozasi): 27-noyabr, 06:05
datetime-format = d-MMMM, HH:mm
tournaments-text =
    🏆 <b>Turnirlar</b>

    Jadvalini ko'rish uchun turnirni tanlang 👇
# Jadval ustunlari sarlavhalari: teng enli shriftda, shuning uchun qisqa (ko'pi bilan 2 belgi).
standings-col-club = Klub
standings-col-played = O'
standings-col-points = O
standings-updated = 🕐 Yangilangan: { $time }
standings-empty = Jadval hali yuklanmagan. Birozdan keyin urinib ko'ring.

## Sevimli klublar

favorites-title = ⭐ <b>Sevimli klublar</b>
favorites-empty = Hali klub tanlanmagan.
favorites-current = Tanlangan klublar:
favorites-hint = Klub qo'shish yoki olib tashlash uchun ligani tanlang.
favorites-pick = Klubni bosib tanlang. Qayta bossangiz, olib tashlanadi.
favorites-added = ✅ Qo'shildi: { $team }
favorites-removed = ❌ Olib tashlandi: { $team }
favorites-no-teams = Bu liga klublari hali yuklanmagan.
favorites-saved = ⭐ <b>Sevimli klublaringiz:</b>
favorites-saved-note = Ularning o'yinlari haqida eslatib turaman.
favorites-none-saved = Klub tanlanmadi. Istalgan payt ⚙️ Sozlamalar → ⭐ Sevimli klublar orqali tanlashingiz mumkin.
favorites-onboarding =
    ⭐ <b>Sevimli klubingizni tanlang</b>

    Uning o'yinlari haqida eslatib turaman: o'yin kuni ertalab, boshlanishiga 1 soat qolganda va o'yin tugagach.

    Avval ligani tanlang 👇
    Keyinroq ⚙️ Sozlamalar orqali o'zgartirishingiz mumkin.

## Eslatmalar

notify-morning-title = ☀️ <b>Sevimli klubingiz o'ynaydi</b>
notify-pre-hour = ⏰ <b>O'yinga 1 soat qoldi</b>
notify-pre-minutes = ⏰ <b>O'yinga { $minutes } daqiqa qoldi</b>
notify-result-title = 🏁 <b>O'yin tugadi</b>
