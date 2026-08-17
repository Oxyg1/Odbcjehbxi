"""Резервное копирование вложений и пересылка их владельцу после удаления."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile

from .models import DOWNLOADABLE, StoredMessage

logger = logging.getLogger(__name__)

# Расширение файла на диске по типу вложения.
_EXTENSIONS = {
    "photo": ".jpg",
    "video": ".mp4",
    "video_note": ".mp4",
    "voice": ".ogg",
    "audio": ".mp3",
    "animation": ".mp4",
    "document": ".bin",
    "sticker": ".webp",
}

# Методы Bot, которыми можно переслать вложение, и поддержка подписи.
_SENDERS = {
    "photo": ("send_photo", "photo", True),
    "video": ("send_video", "video", True),
    "video_note": ("send_video_note", "video_note", False),
    "voice": ("send_voice", "voice", True),
    "audio": ("send_audio", "audio", True),
    "animation": ("send_animation", "animation", True),
    "document": ("send_document", "document", True),
    "sticker": ("send_sticker", "sticker", False),
}

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _safe(part: str) -> str:
    return _SAFE.sub("_", str(part))[:64] or "x"


class MediaVault:
    def __init__(self, bot: Bot, media_dir: Path, max_bytes: int) -> None:
        self._bot = bot
        self._dir = Path(media_dir)
        self._max_bytes = max_bytes

    def can_backup(self, record: StoredMessage) -> bool:
        if record.media_type not in DOWNLOADABLE or not record.file_id:
            return False
        if record.file_size and record.file_size > self._max_bytes:
            return False
        return True

    def _path_for(self, record: StoredMessage) -> Path:
        ext = _EXTENSIONS.get(record.media_type or "", ".bin")
        name = f"{record.message_id}_{_safe(record.file_unique_id or 'file')}{ext}"
        return self._dir / _safe(record.connection_id) / _safe(record.chat_id) / name

    async def backup(self, record: StoredMessage) -> str | None:
        """Скачивает вложение на диск. Возвращает путь либо None."""

        if not self.can_backup(record):
            return None
        path = self._path_for(record)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            await self._bot.download(record.file_id, destination=path)
        except (TelegramAPIError, OSError) as exc:
            logger.warning(
                "Не удалось сохранить вложение %s из чата %s: %s",
                record.message_id,
                record.chat_id,
                exc,
            )
            return None
        return str(path)

    async def resend(
        self,
        chat_id: int,
        record: StoredMessage,
        caption: str | None = None,
        silent: bool = False,
    ) -> bool:
        """Пересылает удалённое вложение владельцу: сначала по file_id, потом с диска."""

        sender = _SENDERS.get(record.media_type or "")
        if sender is None:
            return False
        method_name, argument, supports_caption = sender
        method = getattr(self._bot, method_name)

        attempts: list[object] = []
        if record.file_id:
            attempts.append(record.file_id)
        if record.local_path and Path(record.local_path).exists():
            attempts.append(FSInputFile(record.local_path))

        for source in attempts:
            kwargs: dict[str, object] = {
                "chat_id": chat_id,
                argument: source,
                "disable_notification": silent,
            }
            if supports_caption and caption:
                kwargs["caption"] = caption[:1024]
                kwargs["parse_mode"] = "HTML"
            try:
                await method(**kwargs)
                return True
            except TelegramAPIError as exc:
                logger.info(
                    "Пересылка вложения %s не удалась (%s), пробую запасной вариант",
                    record.message_id,
                    exc,
                )
        return False

    @staticmethod
    def remove_files(paths: list[str]) -> int:
        removed = 0
        for raw in paths:
            try:
                Path(raw).unlink(missing_ok=True)
                removed += 1
            except OSError:  # pragma: no cover - файл занят/недоступен
                logger.debug("Не удалось удалить файл %s", raw)
        return removed
