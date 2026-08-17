from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from aiogram.types import BusinessMessagesDeleted, Chat, Message, User

from app.config import Config, NotificationDefaults
from app.db import Storage
from app.tracker import Tracker

CHAT = Chat(id=-100, type="private", first_name="Иван", username="ivan")
CLIENT = User(id=555, is_bot=False, first_name="Иван", username="ivan")
OWNER = User(id=42, is_bot=False, first_name="Владелец")


class FakeBot:
    """Минимальная замена aiogram.Bot: запоминает отправленные сообщения."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
        self.sent.append({"chat_id": chat_id, "text": text, **kwargs})

    async def get_business_connection(self, business_connection_id: str):  # pragma: no cover
        raise AssertionError("подключение должно браться из базы")

    @property
    def texts(self) -> str:
        return "\n---\n".join(item["text"] for item in self.sent)


def make_config(tmp_path: Path, **overrides) -> Config:
    params = dict(
        bot_token="test:token",
        db_path=tmp_path / "db.sqlite",
        media_dir=tmp_path / "media",
        timezone="Europe/Moscow",
        retention_days=30,
        delete_debounce=0.01,
        chat_delete_threshold=5,
        preview_limit=700,
        max_messages_in_report=25,
        max_media_items=10,
        max_media_bytes=1024,
        log_level="INFO",
        defaults=NotificationDefaults(backup_media=False),
    )
    params.update(overrides)
    return Config(**params)


def build_message(message_id: int = 1, sender: User = CLIENT, **kwargs) -> Message:
    payload = dict(
        message_id=message_id,
        date=datetime.now(tz=timezone.utc),
        chat=CHAT,
        from_user=sender,
        business_connection_id="conn",
        text=f"сообщение {message_id}",
    )
    payload.update(kwargs)
    return Message(**payload)


@pytest_asyncio.fixture
async def tracker(tmp_path: Path):
    storage = await Storage(tmp_path / "db.sqlite").connect()
    await storage.save_connection(
        connection_id="conn",
        owner_user_id=OWNER.id,
        owner_chat_id=OWNER.id,
        owner_name="Владелец",
        is_enabled=True,
        can_reply=False,
    )
    instance = Tracker(FakeBot(), storage, make_config(tmp_path))
    try:
        yield instance
    finally:
        await instance.close()
        await storage.close()


async def flush(tracker: Tracker) -> None:
    """Даёт буферу удалений сработать."""

    await asyncio.sleep(0.1)


async def test_incoming_message_is_cached(tracker: Tracker):
    await tracker.on_message(build_message(1, text="привет"))
    stored = await tracker.storage.get_message("conn", CHAT.id, 1)
    assert stored is not None and stored.text == "привет"
    assert tracker.bot.sent == [], "получение сообщения не должно слать уведомление"


async def test_deleted_message_is_reported_with_content(tracker: Tracker):
    await tracker.on_message(build_message(1, text="перевод отправлен"))
    await tracker.on_deleted_messages(
        BusinessMessagesDeleted(business_connection_id="conn", chat=CHAT, message_ids=[1])
    )
    await flush(tracker)

    assert len(tracker.bot.sent) == 1
    report = tracker.bot.sent[0]
    assert report["chat_id"] == OWNER.id
    assert "Сообщение удалено" in report["text"]
    assert "перевод отправлен" in report["text"]
    assert "Иван" in report["text"]

    stored = await tracker.storage.get_message("conn", CHAT.id, 1)
    assert stored.deleted_at is not None


async def test_own_deleted_message_is_silent_by_default(tracker: Tracker):
    await tracker.on_message(build_message(1, sender=OWNER, text="мой текст"))
    await tracker.on_deleted_messages(
        BusinessMessagesDeleted(business_connection_id="conn", chat=CHAT, message_ids=[1])
    )
    await flush(tracker)

    assert tracker.bot.sent == []


async def test_own_deleted_message_reported_when_include_own_enabled(tracker: Tracker):
    await tracker.storage.set_setting(OWNER.id, "include_own", True)
    await tracker.on_message(build_message(1, sender=OWNER, text="мой текст"))
    await tracker.on_deleted_messages(
        BusinessMessagesDeleted(business_connection_id="conn", chat=CHAT, message_ids=[1])
    )
    await flush(tracker)

    assert "мой текст" in tracker.bot.texts


async def test_bulk_deletion_is_reported_as_chat_deletion(tracker: Tracker):
    for i in range(1, 7):
        await tracker.on_message(build_message(i))
    for i in range(1, 7):
        await tracker.on_deleted_messages(
            BusinessMessagesDeleted(
                business_connection_id="conn", chat=CHAT, message_ids=[i]
            )
        )
    await flush(tracker)

    assert "удалена вся переписка" in tracker.bot.texts
    # Пачка удалений склеена в один отчёт.
    assert len(tracker.bot.sent) == 1


async def test_partial_deletion_is_not_chat_deletion(tracker: Tracker):
    for i in range(1, 8):
        await tracker.on_message(build_message(i))
    await tracker.on_deleted_messages(
        BusinessMessagesDeleted(
            business_connection_id="conn", chat=CHAT, message_ids=[1, 2, 3, 4, 5]
        )
    )
    await flush(tracker)

    text = tracker.bot.texts
    assert "удалена вся переписка" not in text
    assert "Удалено сообщений: 5" in text


async def test_unknown_messages_are_counted(tracker: Tracker):
    await tracker.on_deleted_messages(
        BusinessMessagesDeleted(
            business_connection_id="conn", chat=CHAT, message_ids=[100, 101]
        )
    )
    await flush(tracker)

    assert "бот не видел" in tracker.bot.texts


async def test_deletes_can_be_muted(tracker: Tracker):
    await tracker.storage.set_setting(OWNER.id, "notify_deletes", False)
    await tracker.on_message(build_message(1))
    await tracker.on_deleted_messages(
        BusinessMessagesDeleted(business_connection_id="conn", chat=CHAT, message_ids=[1])
    )
    await flush(tracker)

    assert tracker.bot.sent == []


async def test_edit_is_reported_with_before_and_after(tracker: Tracker):
    await tracker.on_message(build_message(1, text="переведу 5000"))
    edited = build_message(1, text="переведу 500", edit_date=int(time.time()) + 5)
    await tracker.on_edited_message(edited)

    text = tracker.bot.texts
    assert "Сообщение изменено" in text
    assert "переведу 5000" in text
    assert "переведу 500" in text

    stored = await tracker.storage.get_message("conn", CHAT.id, 1)
    assert stored.text == "переведу 500"
    assert stored.edits == 1


async def test_link_preview_edit_is_not_reported(tracker: Tracker):
    await tracker.on_message(build_message(1, text="одинаковый текст"))
    await tracker.on_edited_message(
        build_message(1, text="одинаковый текст", edit_date=int(time.time()))
    )

    assert tracker.bot.sent == []


async def test_edit_of_unknown_message_still_reported(tracker: Tracker):
    await tracker.on_edited_message(
        build_message(9, text="новая версия", edit_date=int(time.time()))
    )

    assert "не видел исходную версию" in tracker.bot.texts
    stored = await tracker.storage.get_message("conn", CHAT.id, 9)
    assert stored.edits == 1, "правка считается один раз, даже если сообщение новое"


async def test_repeated_edits_are_counted(tracker: Tracker):
    await tracker.on_message(build_message(1, text="v1"))
    await tracker.on_edited_message(build_message(1, text="v2", edit_date=int(time.time())))
    await tracker.on_edited_message(
        build_message(1, text="v3", edit_date=int(time.time()) + 1)
    )

    stored = await tracker.storage.get_message("conn", CHAT.id, 1)
    assert stored.edits == 2
    assert stored.text == "v3"
    assert "v2" in tracker.bot.texts and "v3" in tracker.bot.texts


async def test_edits_can_be_muted(tracker: Tracker):
    await tracker.storage.set_setting(OWNER.id, "notify_edits", False)
    await tracker.on_message(build_message(1, text="раз"))
    await tracker.on_edited_message(
        build_message(1, text="два", edit_date=int(time.time()))
    )

    assert tracker.bot.sent == []
    assert (await tracker.storage.get_message("conn", CHAT.id, 1)).text == "два"


@pytest.mark.parametrize("silent", [True, False])
async def test_silent_setting_is_applied(tracker: Tracker, silent: bool):
    await tracker.storage.set_setting(OWNER.id, "silent", silent)
    await tracker.on_message(build_message(1))
    await tracker.on_deleted_messages(
        BusinessMessagesDeleted(business_connection_id="conn", chat=CHAT, message_ids=[1])
    )
    await flush(tracker)

    assert tracker.bot.sent[0]["disable_notification"] is silent
