# Golli — o'zbekcha matnlar (lotin).

## Buyruqlar ro'yxati (Telegram menyusida ko'rinadi)

cmd-start = Botni ishga tushirish
cmd-lang = Tilni o'zgartirish
cmd-help = Yordam

## Asosiy menyu tugmalari

menu-matches = ⚽ Yaqin o'yinlar
menu-recent = 🏁 Oxirgi o'yinlar
menu-tournaments = 🏆 Turnirlar
menu-table = 📊 Jadval
menu-knockout = 🏆 Pley-off
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

    ⚽ <b>Yaqin o'yinlar</b> — Chempionlar ligasi, APL va La Liga o'yinlari, O'zbekiston vaqti bilan.

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
matches-footer = 🕐 Vaqt — O'zbekiston bo'yicha
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
standings-col-wins = G'
standings-col-draws = D
standings-col-losses = M
standings-col-goals = T
standings-col-points = O
standings-updated = 🕐 Yangilangan: { $time }
# Pley-off bosqichlari nomlari (liga nomi yonida ko'rsatiladi).
stage-playoff = Pley-off
stage-round16 = 1/8 final
stage-quarter = Chorak final
stage-semi = Yarim final
stage-final = Final
matches-aggregate-note = Qavs ichida — ikki o'yin yig'indisi
tournaments-sections-text =
    <b>{ $league }</b>

    Nimani ko'rsatay? 👇
# Pley-off juftliklari jadvali: 1 va 2 — birinchi va javob o'yinlari, keyin ikki o'yin yig'indisi.
knockout-col-total = Jami
knockout-empty = Pley-off juftliklari qur'adan keyin shu yerda chiqadi.
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
favorites-done = ✅ Tayyor
favorites-onboarding =
    ⭐ <b>Sevimli klubingizni tanlang</b>

    Uning o'yinlari haqida eslatib turaman: o'yin kuni ertalab, boshlanishiga 1 soat qolganda va o'yin tugagach.

    Ligani tanlang, klublarni belgilang va oxirida «✅ Tayyor» tugmasini bosing 👇
    Keyinroq ⚙️ Sozlamalar orqali o'zgartirishingiz mumkin.

## Eslatmalar

notify-morning-title = ☀️ <b>Sevimli klubingiz o'ynaydi</b>
notify-pre-hour = ⏰ <b>O'yinga 1 soat qoldi</b>
notify-pre-minutes = ⏰ <b>O'yinga { $minutes } daqiqa qoldi</b>
notify-result-title = 🏁 <b>O'yin tugadi</b>
notify-first-leg = Birinchi o'yin: { $score }
notify-aggregate = Ikki o'yin yig'indisi: { $score }
notify-advances = ➡️ Keyingi bosqichga: { $team }
notify-champion = 🏆 G'olib: { $team }
