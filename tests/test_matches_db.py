from dataclasses import replace
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from factories import logo_url, match
from golli.db.matches import has_unfinished, unfinished_kickoffs, upsert_matches
from golli.db.models import ExternalRef, Match, Team
from golli.providers.base import MatchStatus

KICKOFF = datetime(2026, 11, 29, 16, 30, tzinfo=UTC)


async def upsert(db, *items, provider="fake"):
    async with db.begin() as session:
        return await upsert_matches(session, provider, items)


async def count(db, model) -> int:
    async with db() as session:
        return await session.scalar(select(func.count()).select_from(model))


async def all_matches(db) -> list[Match]:
    async with db() as session:
        return list(await session.scalars(select(Match).order_by(Match.id)))


async def test_new_matches_and_teams_are_created(db):
    result = await upsert(
        db,
        match("m1", KICKOFF, "Arsenal", "Manchester City"),
        match("m2", KICKOFF, "Liverpool", "Arsenal"),
    )

    assert (result.created, result.updated, result.teams_created) == (2, 0, 3)
    assert await count(db, Match) == 2
    assert await count(db, Team) == 3  # Arsenal ikki o'yinda, lekin bitta qator
    assert await count(db, ExternalRef) == 5

    stored = (await all_matches(db))[0]
    assert stored.competition == "epl"
    assert stored.season == 2026
    assert stored.kickoff_at == KICKOFF
    assert stored.status == "scheduled"
    assert stored.home_score is None


async def test_same_data_twice_changes_nothing(db):
    items = [match("m1", KICKOFF), match("m2", KICKOFF, "Liverpool", "Everton")]
    await upsert(db, *items)

    result = await upsert(db, *items)

    assert (result.created, result.updated, result.teams_created) == (0, 0, 0)
    assert await count(db, Match) == 2
    assert await count(db, Team) == 4


async def test_score_and_status_are_updated(db):
    await upsert(db, match("m1", KICKOFF))

    result = await upsert(
        db, match("m1", KICKOFF, status=MatchStatus.LIVE, score=(1, 0), minute=34)
    )

    assert (result.created, result.updated) == (0, 1)
    stored = (await all_matches(db))[0]
    assert (stored.status, stored.home_score, stored.away_score, stored.minute) == (
        "live",
        1,
        0,
        34,
    )


async def test_rescheduled_match_keeps_its_row(db):
    await upsert(db, match("m1", KICKOFF))
    original_id = (await all_matches(db))[0].id

    await upsert(db, match("m1", KICKOFF + timedelta(days=1)))

    stored = await all_matches(db)
    assert [m.id for m in stored] == [original_id]
    assert stored[0].kickoff_at == KICKOFF + timedelta(days=1)


async def test_penalties_are_stored(db):
    await upsert(
        db,
        match(
            "m1",
            KICKOFF,
            competition="ucl",
            status=MatchStatus.FINISHED,
            score=(1, 0),
            penalties=(6, 5),
        ),
    )

    stored = (await all_matches(db))[0]
    assert (stored.home_penalties, stored.away_penalties) == (6, 5)


async def test_duplicate_in_one_batch_creates_single_row(db):
    result = await upsert(db, match("m1", KICKOFF), match("m1", KICKOFF))

    assert result.created == 1
    assert await count(db, Match) == 1


async def test_providers_do_not_share_ids(db):
    await upsert(db, match("m1", KICKOFF), provider="a")
    await upsert(db, match("m1", KICKOFF), provider="b")

    assert await count(db, Match) == 2


async def test_unfinished_queries(db):
    now = datetime(2026, 11, 29, 18, 0, tzinfo=UTC)
    await upsert(
        db,
        match("live", now - timedelta(minutes=90), status=MatchStatus.LIVE, score=(0, 0)),
        match("started", now - timedelta(minutes=5), "Liverpool", "Everton"),
        match("done", now - timedelta(hours=3), status=MatchStatus.FINISHED, score=(2, 1)),
        match("future", now + timedelta(hours=2), competition="laliga"),
        match("old", now - timedelta(hours=30), competition="ucl"),
    )

    async with db() as session:
        recent = await unfinished_kickoffs(session, now - timedelta(hours=4), now)
        stale = await has_unfinished(session, now - timedelta(days=3), now - timedelta(hours=4))
        none = await has_unfinished(session, now - timedelta(days=30), now - timedelta(days=2))

    assert sorted(recent) == [
        ("epl", now - timedelta(minutes=90)),
        ("epl", now - timedelta(minutes=5)),
    ]
    assert stale is True
    assert none is False


async def teams_by_name(db) -> dict[str, Team]:
    async with db() as session:
        return {team.name: team for team in await session.scalars(select(Team))}


async def test_team_logo_is_stored_and_filled_in_for_known_teams(db):
    without_logo = match("m1", KICKOFF)
    without_logo = replace(
        without_logo,
        home=replace(without_logo.home, logo_url=None),
        away=replace(without_logo.away, logo_url=None),
    )
    await upsert(db, without_logo)
    assert (await teams_by_name(db))["Arsenal"].logo_url is None

    # Keyingi sinxronizatsiyada havola keladi: mavjud klubga yozib qo'yiladi.
    await upsert(db, match("m1", KICKOFF))

    assert (await teams_by_name(db))["Arsenal"].logo_url == logo_url("Arsenal")


async def test_changed_logo_drops_the_old_emoji(db):
    await upsert(db, match("m1", KICKOFF))
    async with db.begin() as session:
        await session.execute(update(Team).values(emoji_id="5001"))

    # Havola o'sha-o'sha: emoji joyida qoladi.
    await upsert(db, match("m1", KICKOFF))
    assert (await teams_by_name(db))["Arsenal"].emoji_id == "5001"

    rebranded = match("m1", KICKOFF)
    rebranded = replace(
        rebranded, home=replace(rebranded.home, logo_url="https://logos.test/arsenal-new.png")
    )
    await upsert(db, rebranded)

    teams = await teams_by_name(db)
    assert (teams["Arsenal"].logo_url, teams["Arsenal"].emoji_id) == (
        "https://logos.test/arsenal-new.png",
        None,
    )
    assert teams["Manchester City"].emoji_id == "5001"
