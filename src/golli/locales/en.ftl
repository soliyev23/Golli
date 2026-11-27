# Golli — English texts.

## Command list (shown in the Telegram menu)

cmd-start = Start the bot
cmd-lang = Change language
cmd-help = Help

## Main menu buttons

menu-matches = ⚽ Upcoming matches
menu-recent = 🏁 Recent matches
menu-favorites = ⭐ Favourite clubs
menu-language = 🌐 Language

## Language selection

lang-name = 🇬🇧 English
lang-choose = Choose a language
lang-set = ✅ Language: English

## /start and /help

start-welcome =
    Hello, { $name }! 👋

    I'm <b>Golli</b>, a bot for football fans.

    ⚽ I show today's and upcoming matches
    ⭐ I remind you about your favourite club's matches
    🏁 I send the final score when the match ends

    Use the buttons below to get started.

help-text =
    <b>What can Golli do?</b>

    ⚽ <b>Upcoming matches</b> — Champions League, Premier League and La Liga fixtures, in Tashkent time.

    🏁 <b>Recent matches</b> — results from the last two match days.

    ⭐ <b>Favourite clubs</b> — pick a club and I'll remind you about its matches:
    • on the morning of match day;
    • one hour before kick-off;
    • after the final whistle — the final score.

    /start — main menu
    /lang — change language
    /help — this help

## General replies

unknown-message = I didn't get that. Please use the buttons below 👇

## Match list

competition-ucl = 🏆 Champions League
# Flag of England (a sequence of invisible characters, so it is written as a code).
competition-epl = { "\U01F3F4\U0E0067\U0E0062\U0E0065\U0E006E\U0E0067\U0E007F" } Premier League
competition-laliga = 🇪🇸 La Liga

# Date pattern (Unicode CLDR): Saturday, 28 November
date-format = EEEE, d MMMM
matches-title-today = ⚽ <b>Today, { $date }</b>
matches-title-tomorrow = ⚽ <b>Tomorrow, { $date }</b>
matches-title-yesterday = ⚽ <b>Yesterday, { $date }</b>
matches-title-day = ⚽ <b>{ $date }</b>
matches-none = No matches on this day.
matches-none-upcoming = No matches in the coming days.
matches-none-recent = No matches in recent days.
matches-footer = 🕐 Times are in Tashkent time
matches-live-note = 🔴 In play — the score updates with a delay
status-postponed = postponed
status-suspended = suspended
status-cancelled = cancelled
penalties = pens { $home }:{ $away }

## Favourite clubs

favorites-title = ⭐ <b>Favourite clubs</b>
favorites-empty = You haven't picked any clubs yet.
favorites-current = Your clubs:
favorites-hint = Choose a league to add or remove a club.
favorites-pick = Tap a club to pick it. Tap again to remove it.
favorites-added = ✅ Added: { $team }
favorites-removed = ❌ Removed: { $team }
favorites-back = ⬅️ Leagues
favorites-no-teams = This league's clubs haven't been loaded yet.

## Reminders

notify-morning-title = ☀️ <b>Your favourite club is playing</b>
notify-pre-hour = ⏰ <b>One hour to kick-off</b>
notify-pre-minutes = ⏰ <b>{ $minutes } min to kick-off</b>
notify-result-title = 🏁 <b>Full time</b>
