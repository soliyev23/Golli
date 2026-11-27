# Golli — English texts.

## Command list (shown in the Telegram menu)

cmd-start = Start the bot
cmd-lang = Change language
cmd-help = Help

## Main menu buttons

menu-matches = ⚽ Upcoming matches
menu-recent = 🏁 Recent matches
menu-tournaments = 🏆 Tournaments
menu-table = 📊 Table
menu-knockout = 🏆 Knockout
menu-favorites = ⭐ Favourite clubs
menu-language = 🌐 Language
menu-settings = ⚙️ Settings
menu-back = ⬅️ Back

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

    🏆 <b>Tournaments</b> — Champions League, Premier League and La Liga tables.

    ⚙️ <b>Settings</b> — favourite clubs and language.

    ⭐ <b>Favourite clubs</b> — pick a club and I'll remind you about its matches:
    • on the morning of match day;
    • one hour before kick-off;
    • after the final whistle — the final score.

    /start — main menu
    /lang — change language
    /help — this help

## General replies

unknown-message = I didn't get that. Please use the buttons below 👇
menu-main = 🏠 Main menu
buttons-outdated = These buttons are outdated. Please use the menu below.
choose-hint = Pick from the buttons below 👇
settings-text =
    ⚙️ <b>Settings</b>

    Choose a section 👇

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

## Tournaments and tables

# Date and time format (Unicode CLDR pattern): 27 November, 06:05
datetime-format = d MMMM, HH:mm
tournaments-text =
    🏆 <b>Tournaments</b>

    Choose a tournament to see its table 👇
# Table column headings: monospace font, so they are short (2 characters at most).
standings-col-club = Club
standings-col-played = P
standings-col-wins = W
standings-col-draws = D
standings-col-losses = L
standings-col-goals = G
standings-col-points = Pt
standings-updated = 🕐 Updated: { $time }
# Knockout stage names (shown next to the league name).
stage-playoff = Play-offs
stage-round16 = Round of 16
stage-quarter = Quarter-finals
stage-semi = Semi-finals
stage-final = Final
matches-aggregate-note = In brackets — aggregate score
tournaments-sections-text =
    <b>{ $league }</b>

    What would you like to see? 👇
# Knockout ties table: 1 and 2 are the first and second legs, then the aggregate score.
knockout-col-total = Agg
knockout-empty = Knockout ties will appear here after the draw.
standings-empty = The table hasn't been loaded yet. Please try again a bit later.

## Favourite clubs

favorites-title = ⭐ <b>Favourite clubs</b>
favorites-empty = You haven't picked any clubs yet.
favorites-current = Your clubs:
favorites-hint = Choose a league to add or remove a club.
favorites-pick = Tap a club to pick it. Tap again to remove it.
favorites-added = ✅ Added: { $team }
favorites-removed = ❌ Removed: { $team }
favorites-no-teams = This league's clubs haven't been loaded yet.
favorites-done = ✅ Done
favorites-onboarding =
    ⭐ <b>Pick your favourite club</b>

    I'll remind you about its matches: on the morning of match day, one hour before kick-off and after the final whistle.

    Choose a league, mark your clubs, then tap “✅ Done” 👇
    You can change this later in ⚙️ Settings.

## Reminders

notify-morning-title = ☀️ <b>Your favourite club is playing</b>
notify-pre-hour = ⏰ <b>One hour to kick-off</b>
notify-pre-minutes = ⏰ <b>{ $minutes } min to kick-off</b>
notify-result-title = 🏁 <b>Full time</b>
notify-first-leg = First leg: { $score }
notify-aggregate = Aggregate: { $score }
notify-advances = ➡️ Through to the next round: { $team }
notify-champion = 🏆 Winner: { $team }
