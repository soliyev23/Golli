"""Veb admin panel va bot tomonidagi kuzatuv (profil, oxirgi faollik, ulashish havolasi)."""

import re
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select, update

from factories import match
from golli.admin import queries
from golli.admin.app import create_app
from golli.admin.auth import LoginThrottle, hash_password, verify_password
from golli.db.favorites import toggle_favorite
from golli.db.matches import upsert_matches
from golli.db.models import InviteLink, Team, User

PASSWORD = "to'g'ri-parol-123"
NOW = datetime.now(UTC)


async def add_link(db, code: str, source: str, name: str = "Havola") -> int:
    async with db.begin() as session:
        link = InviteLink(code=code, name=name, source=source)
        session.add(link)
        await session.flush()
        return link.id


async def add_user(db, user_id: int, **fields) -> None:
    async with db.begin() as session:
        session.add(User(id=user_id, lang="uz", **fields))


async def get_user(db, user_id: int) -> User:
    async with db() as session:
        return await session.get(User, user_id)


# --- Bot: kuzatuv


async def test_bot_records_profile_and_last_seen(make_chat, db):
    chat = make_chat(first_name="Ali")
    chat.tg_user = chat.tg_user.model_copy(update={"last_name": "Valiyev", "username": "ali_v"})

    await chat.send("/start")

    user = await get_user(db, chat.user_id)
    assert (user.first_name, user.last_name, user.username, user.language_code) == (
        "Ali",
        "Valiyev",
        "ali_v",
        "uz",
    )
    assert user.last_seen_at is not None
    assert datetime.now(UTC) - user.last_seen_at < timedelta(minutes=1)
    assert user.invite_link_id is None


async def test_new_user_from_an_invite_link_is_attributed_to_it(make_chat, db):
    link_id = await add_link(db, "ig-abc123", "instagram")
    chat = make_chat()

    # t.me/golliuzbot?start=ig-abc123 → Telegram botga "/start ig-abc123" yuboradi.
    sent = await chat.send("/start ig-abc123")

    assert (await get_user(db, chat.user_id)).invite_link_id == link_id
    # Bot odatdagidek til so'raydi.
    assert sent[0].text.startswith("Tilni tanlang")


async def test_only_the_first_link_counts(make_chat, db):
    first = await add_link(db, "tg-first1", "telegram")
    await add_link(db, "ig-later1", "instagram")
    chat = make_chat()
    await chat.send("/start tg-first1")

    await chat.send("/start ig-later1")

    assert (await get_user(db, chat.user_id)).invite_link_id == first


async def test_existing_user_opening_a_link_is_not_counted(chat, db):
    await add_link(db, "ig-abc123", "instagram")

    await chat.send("/start ig-abc123")

    assert (await get_user(db, chat.user_id)).invite_link_id is None


async def test_unknown_start_code_is_ignored(make_chat, db):
    chat = make_chat()

    await chat.send("/start nimadir")

    assert (await get_user(db, chat.user_id)).invite_link_id is None


# --- Parol va kirish cheklovi


def test_password_hash_roundtrip():
    stored = hash_password(PASSWORD)

    assert stored.startswith("scrypt:") and "$" not in stored and PASSWORD not in stored
    assert verify_password(PASSWORD, stored)
    assert not verify_password("boshqa", stored)
    assert not verify_password(PASSWORD, "buzuq")


def test_login_throttle_blocks_after_repeated_failures():
    throttle = LoginThrottle(attempts=3)
    for _ in range(3):
        assert not throttle.blocked("1.2.3.4")
        throttle.failed("1.2.3.4")

    assert throttle.blocked("1.2.3.4")
    assert not throttle.blocked("5.6.7.8")
    throttle.succeeded("1.2.3.4")
    assert not throttle.blocked("1.2.3.4")


# --- Veb panel


@pytest.fixture
def admin_app(settings, db):
    configured = settings.model_copy(
        update={
            "admin_username": "admin",
            "admin_password_hash": SecretStr(hash_password(PASSWORD)),
            "admin_secret": SecretStr("sinov-kaliti-" * 4),
        }
    )

    async def bot_username() -> str:
        return "golliuzbot"

    return create_app(configured, db, bot_username, secure_cookies=False)


@pytest.fixture
async def client(admin_app):
    transport = httpx.ASGITransport(app=admin_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://admin.test") as client:
        yield client


def csrf_of(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


async def login(client, password: str = PASSWORD) -> httpx.Response:
    page = await client.get("/login")
    return await client.post(
        "/login",
        data={"username": "admin", "password": password, "csrf": csrf_of(page.text)},
    )


@pytest.fixture
async def logged_in(client):
    response = await login(client)
    assert response.status_code == 303
    return client


async def test_pages_require_login(client):
    for path in ("/", "/links", "/users.csv"):
        response = await client.get(path)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


async def test_wrong_password_is_rejected(client):
    response = await login(client, "noto'g'ri")

    assert response.status_code == 200
    assert "Login yoki parol noto&#39;g&#39;ri" in response.text
    assert (await client.get("/")).status_code == 303


async def test_login_without_csrf_token_is_rejected(client):
    response = await client.post("/login", data={"username": "admin", "password": PASSWORD})

    assert response.status_code == 400


async def test_too_many_wrong_passwords_lock_the_login(client):
    for _ in range(5):
        await login(client, "noto'g'ri")

    response = await login(client)

    assert "Juda ko&#39;p urinish" in response.text
    assert (await client.get("/")).status_code == 303


async def test_logout(logged_in):
    page = await logged_in.get("/")

    await logged_in.post("/logout", data={"csrf": csrf_of(page.text)})

    assert (await logged_in.get("/")).status_code == 303


async def test_dashboard_kpis(logged_in, db):
    tg = await add_link(db, "tg-aaaaaa", "telegram")
    ig = await add_link(db, "ig-bbbbbb", "instagram")
    await add_user(db, 1, last_seen_at=NOW - timedelta(hours=1), invite_link_id=tg)
    await add_user(db, 2, last_seen_at=NOW - timedelta(hours=30), invite_link_id=ig)
    await add_user(db, 3, last_seen_at=NOW - timedelta(minutes=5), invite_link_id=ig)
    await add_user(db, 4, is_active=False)

    async with db() as session:
        kpi = await queries.load_kpi(session, NOW, ZONE)

    assert (kpi.total, kpi.active_24h, kpi.from_telegram, kpi.from_instagram, kpi.blocked) == (
        4,
        2,
        1,
        2,
        1,
    )
    page = await logged_in.get("/")
    assert page.status_code == 200
    assert "Foydalanuvchilar" in page.text and "Instagramdan" in page.text
    # Foydalanuvchi olib tashlashni so'ragan kartalar yo'q.
    assert "Sevimli klub tanlagan" not in page.text and "Havolasiz kelgan" not in page.text
    assert page.text.count('class="card kpi ') == 5
    assert "Yangi (7 kun)" not in page.text and "Umumiy ko&#39;rinish" not in page.text


ZONE = __import__("zoneinfo").ZoneInfo("Asia/Tashkent")


async def test_users_are_sorted_newest_first_by_default_and_active_first_on_request(logged_in, db):
    await add_user(db, 1, first_name="Eski", created_at=NOW - timedelta(days=3), last_seen_at=NOW)
    await add_user(db, 2, first_name="Yangi", created_at=NOW - timedelta(days=1), last_seen_at=None)
    await add_user(
        db,
        3,
        first_name="Orta",
        created_at=NOW - timedelta(days=2),
        last_seen_at=NOW - timedelta(hours=2),
    )

    def order(html: str) -> list[str]:
        return sorted(
            ("Eski", "Yangi", "Orta"),
            key=lambda name: html.index(f'<div class="cell-main">{name}</div>'),
        )

    assert order((await logged_in.get("/")).text) == ["Yangi", "Orta", "Eski"]
    assert order((await logged_in.get("/?sort=active")).text) == ["Eski", "Orta", "Yangi"]


async def test_filters_search_status_and_source(logged_in, db):
    ig = await add_link(db, "ig-cccccc", "instagram", name="Instagram bio")
    await add_user(db, 1, first_name="Faol", username="faol_user", last_seen_at=NOW)
    await add_user(db, 2, first_name="Bloklagan", is_active=False)
    await add_user(db, 3, first_name="Instagramchi", invite_link_id=ig)

    def names(html: str) -> set[str]:
        return {
            name
            for name in ("Faol", "Bloklagan", "Instagramchi")
            if f'<div class="cell-main">{name}</div>' in html
        }

    assert names((await logged_in.get("/?status=active")).text) == {"Faol"}
    assert names((await logged_in.get("/?status=blocked")).text) == {"Bloklagan"}
    assert names((await logged_in.get("/?source=instagram")).text) == {"Instagramchi"}
    assert names((await logged_in.get(f"/?source=link:{ig}")).text) == {"Instagramchi"}
    assert names((await logged_in.get("/?source=organic")).text) == {"Faol", "Bloklagan"}
    assert names((await logged_in.get("/?q=@faol_user")).text) == {"Faol"}
    assert names((await logged_in.get("/?q=2")).text) == {"Bloklagan"}


async def test_user_table_shows_favourite_clubs(logged_in, db):
    async with db.begin() as session:
        await upsert_matches(session, "fake", [match("m1", NOW, "Real Madrid", "Barcelona")])
    await add_user(db, 1, first_name="Muxlis")
    async with db.begin() as session:
        team_id = await session.scalar(select(Team.id).where(Team.name == "Barcelona"))
        await toggle_favorite(session, 1, team_id)

    page = (await logged_in.get("/")).text

    assert "Barselona" in page


async def test_creating_and_deleting_an_invite_link(logged_in, db):
    page = await logged_in.get("/links")

    response = await logged_in.post(
        "/links", data={"name": "Instagram bio", "source": "instagram", "csrf": csrf_of(page.text)}
    )

    assert response.status_code == 303
    async with db() as session:
        link = await session.scalar(select(InviteLink))
    assert (link.name, link.source) == ("Instagram bio", "instagram")
    assert re.fullmatch(r"ig-[a-z0-9]{6}", link.code)
    listing = (await logged_in.get("/links")).text
    assert f"https://t.me/golliuzbot?start={link.code}" in listing

    # O'chirilgan havola orqali kelganlar «Havolasiz» bo'lib qoladi, o'zlari o'chmaydi.
    await add_user(db, 1, invite_link_id=link.id)
    await logged_in.post(f"/links/{link.id}/delete", data={"csrf": csrf_of(listing)})
    async with db() as session:
        assert await session.scalar(select(InviteLink)) is None
        assert (await session.get(User, 1)).invite_link_id is None


async def test_link_needs_a_name_and_a_known_source(logged_in, db):
    page = await logged_in.get("/links")

    response = await logged_in.post(
        "/links", data={"name": " ", "source": "tiktok", "csrf": csrf_of(page.text)}
    )

    assert "Havola nomini yozing" in response.text
    async with db() as session:
        assert await session.scalar(select(InviteLink)) is None


async def test_link_page_counts_users_per_link(logged_in, db):
    link = await add_link(db, "tg-dddddd", "telegram", name="Kanal posti")
    await add_user(db, 1, invite_link_id=link, last_seen_at=NOW)
    await add_user(db, 2, invite_link_id=link, last_seen_at=NOW - timedelta(days=2))

    async with db() as session:
        [stats] = await queries.load_links(session, NOW)

    assert (stats.users, stats.active_24h) == (2, 1)


async def test_csv_export(logged_in, db):
    await add_user(db, 1, first_name="Ali", username="ali_v", last_seen_at=NOW)
    await add_user(db, 2, first_name="Vali", is_active=False)

    response = await logged_in.get("/users.csv?status=blocked")

    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.lstrip("﻿").strip().splitlines()
    assert lines[0].startswith("ID,Ism,Username")
    assert len(lines) == 2 and lines[1].startswith("2,Vali")


async def test_security_headers(client):
    response = await client.get("/login")

    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"


async def test_new_users_by_day(db):
    await add_user(db, 1, created_at=NOW)
    await add_user(db, 2, created_at=NOW)
    await add_user(db, 3, created_at=NOW - timedelta(days=40))

    async with db() as session:
        days = await queries.new_users_by_day(session, NOW, ZONE)

    assert len(days) == 30
    assert days[-1] == (NOW.astimezone(ZONE).date(), 2)
    assert sum(count for _, count in days) == 2


async def test_blocked_flag_comes_from_the_bot(db):
    await add_user(db, 1)
    async with db.begin() as session:
        await session.execute(update(User).where(User.id == 1).values(is_active=False))

    async with db() as session:
        users, total = await queries.load_users(session, queries.UserFilter(status="blocked"), NOW)

    assert total == 1 and users[0].id == 1


async def test_chart_shows_the_count_on_hover(logged_in, db):
    await add_user(db, 1, created_at=NOW)
    await add_user(db, 2, created_at=NOW)

    page = (await logged_in.get("/")).text

    # Har bir ustunda kursor borganda ko'rinadigan maslahat: son va sana.
    tips = re.findall(r'<span class="chart-tip"><b>(\d+) ta</b>', page)
    assert len(tips) == 30
    assert tips[-1] == "2" and tips.count("0") == 29
