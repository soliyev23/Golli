"""Bot egasiga yangi foydalanuvchi haqida xabar."""

import pytest
from aiogram.methods import SendMessage

from golli.bot.middlewares import UserMiddleware
from golli.db.models import InviteLink

OWNER_ID = 900


@pytest.fixture
def alerts_to_owner(dispatcher):
    middleware = next(
        m for m in dispatcher.update.outer_middleware if isinstance(m, UserMiddleware)
    )
    middleware._alert_chat_id = OWNER_ID
    yield
    middleware._alert_chat_id = None


def owner_messages(chat) -> list[str]:
    return [m.text for m in chat.requests if isinstance(m, SendMessage) and m.chat_id == OWNER_ID]


async def test_owner_gets_name_and_username_of_new_user(make_chat, alerts_to_owner):
    chat = make_chat(user_id=2001, first_name="Vali")
    chat.tg_user = chat.tg_user.model_copy(update={"last_name": "Karimov", "username": "vali_k"})

    await chat.send("/start")

    assert owner_messages(chat) == [
        "🆕 <b>Yangi foydalanuvchi</b>\nVali Karimov\n@vali_k\nID: <code>2001</code>"
    ]


async def test_alert_mentions_invite_link(make_chat, db, alerts_to_owner):
    async with db.begin() as session:
        session.add(InviteLink(code="ig-test", name="Instagram bio", source="instagram"))
    chat = make_chat(user_id=2002, first_name="<Ali>")

    await chat.send("/start ig-test")

    assert owner_messages(chat) == [
        "🆕 <b>Yangi foydalanuvchi</b>\n&lt;Ali&gt;\nID: <code>2002</code>\nHavola: Instagram bio"
    ]


async def test_returning_user_does_not_trigger_alert(make_chat, alerts_to_owner):
    chat = make_chat(user_id=2003)
    await chat.send("/start")

    await chat.send("/start")

    assert owner_messages(chat) == []


async def test_no_alert_when_not_configured(make_chat):
    chat = make_chat(user_id=2004)

    await chat.send("/start")

    assert owner_messages(chat) == []
