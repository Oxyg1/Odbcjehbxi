"""Проверка проводки: апдейт → роутер → Tracker (включая внедрение зависимостей)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BusinessMessagesDeleted, Chat, Message, Update, User

from app.db import Storage
from app.handlers import build_router
from app.tracker import Tracker
from tests.test_tracker import CHAT, CLIENT, OWNER, FakeBot, make_config


@pytest_asyncio.fixture
async def wired(tmp_path: Path):
    storage = await Storage(tmp_path / "db.sqlite").connect()
    await storage.save_connection(
        connection_id="conn",
        owner_user_id=OWNER.id,
        owner_chat_id=OWNER.id,
        owner_name="Владелец",
        is_enabled=True,
        can_reply=False,
    )
    tracker = Tracker(FakeBot(), storage, make_config(tmp_path))
    dispatcher = Dispatcher()
    dispatcher["tracker"] = tracker
    dispatcher.include_router(build_router())
    # Диспетчеру нужен объект Bot для контекста; уведомления уходят через FakeBot.
    bot = Bot(
        token="42:TEST-TOKEN-FOR-DISPATCH",
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        yield dispatcher, bot, tracker
    finally:
        await bot.session.close()
        await tracker.close()
        await storage.close()


def business_message(message_id: int, text: str) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(tz=timezone.utc),
        chat=CHAT,
        from_user=CLIENT,
        business_connection_id="conn",
        text=text,
    )


async def test_business_updates_reach_tracker(wired):
    dispatcher, bot, tracker = wired

    await dispatcher.feed_update(
        bot, Update(update_id=1, business_message=business_message(1, "исходный текст"))
    )
    assert (await tracker.storage.get_message("conn", CHAT.id, 1)).text == "исходный текст"

    edited = business_message(1, "исправленный текст")
    edited = edited.model_copy(update={"edit_date": int(edited.date.timestamp()) + 1})
    await dispatcher.feed_update(bot, Update(update_id=2, edited_business_message=edited))
    assert "исправленный текст" in tracker.bot.texts

    await dispatcher.feed_update(
        bot,
        Update(
            update_id=3,
            deleted_business_messages=BusinessMessagesDeleted(
                business_connection_id="conn", chat=CHAT, message_ids=[1]
            ),
        ),
    )
    await asyncio.sleep(0.1)

    reports = tracker.bot.texts
    assert "Сообщение изменено" in reports
    assert "Сообщение удалено" in reports
    assert all(item["chat_id"] == OWNER.id for item in tracker.bot.sent)


async def test_unknown_update_is_ignored(wired):
    dispatcher, bot, tracker = wired

    await dispatcher.feed_update(
        bot,
        Update(
            update_id=4,
            message=Message(
                message_id=1,
                date=datetime.now(tz=timezone.utc),
                chat=Chat(id=OWNER.id, type="private"),
                from_user=User(id=OWNER.id, is_bot=False, first_name="Владелец"),
                text="просто текст без команды",
            ),
        ),
    )
    assert tracker.bot.sent == []
