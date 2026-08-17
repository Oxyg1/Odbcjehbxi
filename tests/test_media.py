"""Бэкап вложений и пересылка удалённых фото/голосовых владельцу."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
import pytest_asyncio
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BusinessMessagesDeleted, FSInputFile, PhotoSize, Voice

from app.db import Storage
from app.media import MediaVault
from app.tracker import Tracker
from tests.test_tracker import CHAT, OWNER, build_message, make_config


class MediaBot:
    """Фейковый Bot: считает вызовы send_* и умеет «скачивать» файл."""

    def __init__(self, fail_file_ids: set[str] | None = None) -> None:
        self.sent: list[dict] = []
        self.messages: list[dict] = []
        self.downloaded: list[str] = []
        self.fail_file_ids = fail_file_ids or set()

    async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
        self.messages.append({"chat_id": chat_id, "text": text, **kwargs})

    async def download(self, file_id: str, destination: Path, **kwargs) -> None:
        if file_id in self.fail_file_ids:
            raise TelegramBadRequest(method=None, message="file is too big")
        self.downloaded.append(file_id)
        Path(destination).write_bytes(b"\x89PNG\r\n\x1a\n fake payload")

    async def _send(self, kind: str, **kwargs) -> None:
        source = kwargs.get(kind)
        if isinstance(source, str) and source in self.fail_file_ids:
            raise TelegramBadRequest(method=None, message="wrong file identifier")
        self.sent.append({"kind": kind, **kwargs})

    async def send_photo(self, **kwargs) -> None:
        await self._send("photo", **kwargs)

    async def send_voice(self, **kwargs) -> None:
        await self._send("voice", **kwargs)

    async def send_video_note(self, **kwargs) -> None:
        await self._send("video_note", **kwargs)

    @property
    def texts(self) -> str:
        return "\n---\n".join(item["text"] for item in self.messages)


@pytest.fixture
def vault(tmp_path: Path) -> MediaVault:
    return MediaVault(MediaBot(), tmp_path / "media", max_bytes=1_000_000)


async def wait_for(condition, timeout: float = 3.0) -> bool:
    """Ждёт условия: вложения уходят с паузами, чтобы не ловить флуд-лимит."""

    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if condition():
            return True
        await asyncio.sleep(0.02)
    return condition()


async def test_backup_writes_file_and_returns_path(vault, make_record):
    record = make_record(1, media_type="photo", file_id="PHOTO", file_unique_id="u1")
    path = await vault.backup(record)

    assert path is not None
    assert Path(path).exists()
    assert Path(path).suffix == ".jpg"


async def test_backup_skips_oversized_and_undownloadable(vault, make_record):
    big = make_record(1, media_type="video", file_id="V", file_size=999_999_999)
    assert vault.can_backup(big) is False
    assert await vault.backup(big) is None

    location = make_record(2, media_type="location", file_id=None)
    assert vault.can_backup(location) is False


async def test_backup_survives_telegram_error(tmp_path, make_record):
    vault = MediaVault(MediaBot(fail_file_ids={"BAD"}), tmp_path, max_bytes=1_000_000)
    record = make_record(1, media_type="voice", file_id="BAD", file_unique_id="u")
    assert await vault.backup(record) is None


async def test_resend_uses_file_id_first(tmp_path, make_record):
    bot = MediaBot()
    vault = MediaVault(bot, tmp_path, max_bytes=1_000_000)
    record = make_record(1, media_type="photo", file_id="PHOTO")

    assert await vault.resend(OWNER.id, record, caption="подпись") is True
    assert bot.sent[0]["photo"] == "PHOTO"
    assert bot.sent[0]["caption"] == "подпись"
    assert bot.sent[0]["chat_id"] == OWNER.id


async def test_resend_falls_back_to_local_copy(tmp_path, make_record):
    local = tmp_path / "voice.ogg"
    local.write_bytes(b"payload")
    bot = MediaBot(fail_file_ids={"DEAD"})
    vault = MediaVault(bot, tmp_path, max_bytes=1_000_000)
    record = make_record(1, media_type="voice", file_id="DEAD", local_path=str(local))

    assert await vault.resend(OWNER.id, record) is True
    assert isinstance(bot.sent[0]["voice"], FSInputFile)


async def test_resend_reports_failure_when_nothing_works(tmp_path, make_record):
    bot = MediaBot(fail_file_ids={"DEAD"})
    vault = MediaVault(bot, tmp_path, max_bytes=1_000_000)
    record = make_record(1, media_type="photo", file_id="DEAD", local_path="/нет/файла")

    assert await vault.resend(OWNER.id, record) is False
    assert bot.sent == []


async def test_video_note_is_sent_without_caption(tmp_path, make_record):
    bot = MediaBot()
    vault = MediaVault(bot, tmp_path, max_bytes=1_000_000)
    record = make_record(1, media_type="video_note", file_id="VN")

    assert await vault.resend(OWNER.id, record, caption="подпись") is True
    assert "caption" not in bot.sent[0]


def test_remove_files_ignores_missing(tmp_path):
    existing = tmp_path / "a.jpg"
    existing.write_bytes(b"x")
    assert MediaVault.remove_files([str(existing), str(tmp_path / "нет.jpg")]) == 2
    assert not existing.exists()


# --------------------------------------------------------- сквозной сценарий


@pytest_asyncio.fixture
async def media_tracker(tmp_path: Path):
    storage = await Storage(tmp_path / "db.sqlite").connect()
    await storage.save_connection(
        connection_id="conn",
        owner_user_id=OWNER.id,
        owner_chat_id=OWNER.id,
        owner_name="Владелец",
        is_enabled=True,
        can_reply=False,
    )
    config = make_config(tmp_path)
    tracker = Tracker(MediaBot(), storage, config)
    await storage.set_setting(OWNER.id, "backup_media", True)
    try:
        yield tracker
    finally:
        await tracker.close()
        await storage.close()


def photo_message(message_id: int):
    photo = [
        PhotoSize(file_id="PHOTO", file_unique_id="pu", width=1280, height=720, file_size=500)
    ]
    return build_message(message_id, photo=photo, caption="счёт на оплату", text=None)


def voice_message(message_id: int):
    voice = Voice(file_id="VOICE", file_unique_id="vu", duration=7, file_size=400)
    return build_message(message_id, voice=voice, text=None)


async def test_deleted_photo_and_voice_are_sent_back(media_tracker: Tracker):
    bot: MediaBot = media_tracker.bot
    await media_tracker.on_message(photo_message(1))
    await media_tracker.on_message(voice_message(2))
    await wait_for(lambda: len(bot.downloaded) == 2)  # фоновое скачивание

    await media_tracker.on_deleted_messages(
        BusinessMessagesDeleted(
            business_connection_id="conn", chat=CHAT, message_ids=[1, 2]
        )
    )
    await wait_for(lambda: len(bot.sent) == 2)

    kinds = [item["kind"] for item in bot.sent]
    assert kinds == ["photo", "voice"], "удалённые фото и голосовое должны прийти обратно"
    assert all(item["chat_id"] == OWNER.id for item in bot.sent)
    assert "Удалённое вложение" in bot.sent[0]["caption"]

    # В текстовом отчёте видно подпись и тип вложения.
    assert "счёт на оплату" in bot.texts
    assert "голосовое сообщение" in bot.texts


async def test_media_is_backed_up_to_disk(media_tracker: Tracker):
    await media_tracker.on_message(voice_message(1))
    await wait_for(lambda: media_tracker.bot.downloaded == ["VOICE"])

    stored = await media_tracker.storage.get_message("conn", CHAT.id, 1)
    assert stored.local_path is not None
    assert Path(stored.local_path).exists()
    assert media_tracker.bot.downloaded == ["VOICE"]


async def test_deleted_media_survives_dead_file_id(tmp_path: Path):
    """Главный смысл бэкапа: file_id умер, а копия на диске осталась."""

    storage = await Storage(tmp_path / "db.sqlite").connect()
    await storage.save_connection(
        connection_id="conn",
        owner_user_id=OWNER.id,
        owner_chat_id=OWNER.id,
        owner_name="Владелец",
        is_enabled=True,
        can_reply=False,
    )
    bot = MediaBot()
    tracker = Tracker(bot, storage, make_config(tmp_path))
    await storage.set_setting(OWNER.id, "backup_media", True)

    await tracker.on_message(photo_message(1))
    await wait_for(lambda: bot.downloaded == ["PHOTO"])
    # После удаления Telegram перестаёт отдавать файл по file_id.
    bot.fail_file_ids.add("PHOTO")

    await tracker.on_deleted_messages(
        BusinessMessagesDeleted(business_connection_id="conn", chat=CHAT, message_ids=[1])
    )
    await wait_for(lambda: len(bot.sent) == 1)

    assert [item["kind"] for item in bot.sent] == ["photo"]
    assert isinstance(bot.sent[0]["photo"], FSInputFile)

    await tracker.close()
    await storage.close()


async def test_media_limit_is_respected(tmp_path: Path):
    storage = await Storage(tmp_path / "db.sqlite").connect()
    await storage.save_connection(
        connection_id="conn",
        owner_user_id=OWNER.id,
        owner_chat_id=OWNER.id,
        owner_name="Владелец",
        is_enabled=True,
        can_reply=False,
    )
    tracker = Tracker(MediaBot(), storage, make_config(tmp_path, max_media_items=3))

    for i in range(1, 7):
        await tracker.on_message(photo_message(i))
    await tracker.on_deleted_messages(
        BusinessMessagesDeleted(
            business_connection_id="conn", chat=CHAT, message_ids=[1, 2, 3, 4, 5, 6]
        )
    )
    await wait_for(lambda: len(tracker.bot.sent) >= 3)
    await asyncio.sleep(0.3)  # убеждаемся, что четвёртое вложение не уходит

    assert len(tracker.bot.sent) == 3

    await tracker.close()
    await storage.close()


async def test_replaced_attachment_is_sent_before_it_disappears(media_tracker: Tracker):
    """Если фото заменили на другое, прежнее приходит владельцу."""

    bot: MediaBot = media_tracker.bot
    await media_tracker.on_message(photo_message(1))
    await wait_for(lambda: bot.downloaded == ["PHOTO"])

    replaced = build_message(
        1,
        photo=[
            PhotoSize(
                file_id="PHOTO2", file_unique_id="pu2", width=800, height=600, file_size=400
            )
        ],
        caption="счёт на оплату",
        text=None,
        edit_date=int(time.time()) + 1,
    )
    await media_tracker.on_edited_message(replaced)
    await wait_for(lambda: len(bot.sent) == 1)

    assert "Сообщение изменено" in bot.texts
    assert bot.sent[0]["photo"] == "PHOTO", "должно прийти именно прежнее вложение"
    assert "Прежнее вложение" in bot.sent[0]["caption"]


async def test_caption_only_edit_does_not_resend_attachment(media_tracker: Tracker):
    bot: MediaBot = media_tracker.bot
    await media_tracker.on_message(photo_message(1))
    await wait_for(lambda: bot.downloaded == ["PHOTO"])

    await media_tracker.on_edited_message(
        build_message(
            1,
            photo=[
                PhotoSize(
                    file_id="PHOTO", file_unique_id="pu", width=1280, height=720, file_size=500
                )
            ],
            caption="другая подпись",
            text=None,
            edit_date=int(time.time()) + 1,
        )
    )
    await asyncio.sleep(0.2)

    assert "другая подпись" in bot.texts
    assert bot.sent == [], "вложение не менялось — пересылать нечего"
