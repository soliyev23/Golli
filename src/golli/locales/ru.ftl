# Golli — тексты на русском.

## Список команд (виден в меню Telegram)

cmd-start = Запустить бота
cmd-lang = Сменить язык
cmd-help = Помощь

## Кнопки главного меню

menu-matches = ⚽ Ближайшие матчи
menu-recent = 🏁 Последние матчи
menu-favorites = ⭐ Любимые клубы
menu-language = 🌐 Язык
menu-settings = ⚙️ Настройки
menu-back = ⬅️ Назад

## Выбор языка

lang-name = 🇷🇺 Русский
lang-choose = Выберите язык
lang-set = ✅ Язык: Русский

## /start и /help

start-welcome =
    Здравствуйте, { $name }! 👋

    Я <b>Golli</b> — бот для футбольных болельщиков.

    ⚽ Показываю матчи на сегодня и ближайшие дни
    ⭐ Напоминаю о матчах вашего любимого клуба
    🏁 Присылаю счёт после окончания матча

    Чтобы начать, воспользуйтесь кнопками ниже.

help-text =
    <b>Что умеет Golli?</b>

    ⚽ <b>Ближайшие матчи</b> — матчи Лиги чемпионов, АПЛ и Ла Лиги по ташкентскому времени.

    🏁 <b>Последние матчи</b> — результаты двух последних игровых дней.

    ⚙️ <b>Настройки</b> — любимые клубы и язык.

    ⭐ <b>Любимые клубы</b> — выберите клуб, и я буду напоминать о его матчах:
    • утром в день матча;
    • за час до начала;
    • после окончания — итоговый счёт.

    /start — главное меню
    /lang — сменить язык
    /help — эта справка

## Общие ответы

unknown-message = Не понял. Воспользуйтесь кнопками ниже 👇
menu-main = 🏠 Главное меню
buttons-outdated = Эти кнопки устарели. Воспользуйтесь меню внизу.
settings-text =
    ⚙️ <b>Настройки</b>

    Выберите раздел 👇

## Список матчей

competition-ucl = 🏆 Лига чемпионов
# Флаг Англии (последовательность невидимых символов, поэтому записан кодом).
competition-epl = { "\U01F3F4\U0E0067\U0E0062\U0E0065\U0E006E\U0E0067\U0E007F" } АПЛ
competition-laliga = 🇪🇸 Ла Лига

# Вид даты (шаблон Unicode CLDR): 28 ноября, суббота
date-format = d MMMM, EEEE
matches-title-today = ⚽ <b>Сегодня, { $date }</b>
matches-title-tomorrow = ⚽ <b>Завтра, { $date }</b>
matches-title-yesterday = ⚽ <b>Вчера, { $date }</b>
matches-title-day = ⚽ <b>{ $date }</b>
matches-none = В этот день матчей нет.
matches-none-upcoming = В ближайшие дни матчей нет.
matches-none-recent = В последние дни матчей не было.
matches-footer = 🕐 Время — ташкентское
matches-live-note = 🔴 Матч идёт — счёт обновляется с задержкой
status-postponed = перенесён
status-suspended = прерван
status-cancelled = отменён
penalties = пен. { $home }:{ $away }

## Любимые клубы

favorites-title = ⭐ <b>Любимые клубы</b>
favorites-empty = Вы пока не выбрали ни одного клуба.
favorites-current = Выбранные клубы:
favorites-hint = Чтобы добавить или убрать клуб, выберите лигу.
favorites-pick = Нажмите на клуб, чтобы выбрать. Повторное нажатие уберёт его.
favorites-added = ✅ Добавлено: { $team }
favorites-removed = ❌ Убрано: { $team }
favorites-back = ⬅️ Лиги
favorites-no-teams = Клубы этой лиги пока не загружены.
favorites-done = ✅ Готово
favorites-choose-hint = Выберите из кнопок ниже 👇
favorites-saved = ⭐ <b>Ваши любимые клубы:</b>
favorites-saved-note = Буду напоминать об их матчах.
favorites-none-saved = Клуб не выбран. В любой момент это можно сделать через ⚙️ Настройки → ⭐ Любимые клубы.
favorites-onboarding =
    ⭐ <b>Выберите любимый клуб</b>

    Я буду напоминать о его матчах: утром в день матча, за час до начала и после окончания.

    Сначала выберите лигу 👇
    Позже это можно изменить в ⚙️ Настройках.

## Напоминания

notify-morning-title = ☀️ <b>Играет ваш любимый клуб</b>
notify-pre-hour = ⏰ <b>До матча остался 1 час</b>
notify-pre-minutes = ⏰ <b>До матча { $minutes } мин.</b>
notify-result-title = 🏁 <b>Матч окончен</b>
