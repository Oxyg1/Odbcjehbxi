"""Основная логика: кэширование бизнес-переписки и уведомления владельцу."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import (
    BusinessConnection,
    BusinessMessagesDeleted,
    LinkPreviewOptions,
    Message,
)

from . import formatters as fmt
from .buffer import DeletionBuffer
from .config import Config
from .db import Storage
from .media import MediaVault
from .models import StoredMessage, chat_display_title, message_to_record, user_display_name

logger = logging.getLogger(__name__)


class Tracker:
    def __init__(self, bot: Bot, storage: Storage, config: Config) -> None:
        self.bot = bot
        self.storage = storage
        self.config = config
        self.vault = MediaVault(bot, config.media_dir, config.max_media_bytes)
        self.buffer = DeletionBuffer(config.delete_debounce, self._report_deletions)
        self._connections: dict[str, dict[str, Any]] = {}
        self._chat_meta: dict[tuple[str, int], tuple[str, str | None]] = {}
        self._background: set[asyncio.Task[Any]] = set()

    # ------------------------------------------------------------ вспомогательное

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def close(self) -> None:
        await self.buffer.close()
        for task in list(self._background):
            task.cancel()
        for task in list(self._background):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def connection_info(self, connection_id: str) -> dict[str, Any] | None:
        """Данные подключения: из памяти, из БД либо запросом к Telegram."""

        cached = self._connections.get(connection_id)
        if cached:
            return cached

        stored = await self.storage.get_connection(connection_id)
        if stored:
            self._connections[connection_id] = stored
            return stored

        try:
            connection = await self.bot.get_business_connection(connection_id)
        except TelegramAPIError as exc:
            logger.warning("Не удалось получить подключение %s: %s", connection_id, exc)
            return None
        return await self._store_connection(connection)

    async def _store_connection(self, connection: BusinessConnection) -> dict[str, Any]:
        rights = getattr(connection, "rights", None)
        can_reply = bool(
            getattr(rights, "can_reply", None)
            if rights is not None
            else getattr(connection, "can_reply", False)
        )
        owner_name = user_display_name(connection.user)
        await self.storage.save_connection(
            connection_id=connection.id,
            owner_user_id=connection.user.id,
            owner_chat_id=connection.user_chat_id,
            owner_name=owner_name,
            is_enabled=bool(connection.is_enabled),
            can_reply=can_reply,
        )
        info = await self.storage.get_connection(connection.id) or {}
        self._connections[connection.id] = info
        return info

    async def settings_for(self, owner_user_id: int) -> dict[str, bool]:
        return await self.storage.get_settings(
            owner_user_id, self.config.defaults.as_dict()
        )

    async def send(self, chat_id: int, text: str, silent: bool = False) -> None:
        """Отправка уведомления с одной повторной попыткой при флуд-лимите."""

        for attempt in range(2):
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    disable_notification=silent,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
                return
            except TelegramRetryAfter as exc:
                if attempt == 0:
                    await asyncio.sleep(exc.retry_after + 0.5)
                    continue
                logger.warning("Флуд-лимит при отправке уведомления в %s", chat_id)
            except TelegramAPIError as exc:
                logger.error("Не удалось отправить уведомление в %s: %s", chat_id, exc)
                return

    # ------------------------------------------------------------------ апдейты

    async def on_connection(self, connection: BusinessConnection) -> None:
        info = await self._store_connection(connection)
        rights = getattr(connection, "rights", None)
        can_reply = bool(
            getattr(rights, "can_reply", None)
            if rights is not None
            else getattr(connection, "can_reply", False)
        )
        await self.send(
            connection.user_chat_id,
            fmt.connection_report(
                enabled=bool(connection.is_enabled),
                can_reply=can_reply,
                owner_name=info.get("owner_name", ""),
                tz_name=self.config.timezone,
            ),
        )

    async def on_message(self, message: Message) -> None:
        connection_id = message.business_connection_id or ""
        info = await self.connection_info(connection_id)
        owner_user_id = info.get("owner_user_id") if info else None

        record = message_to_record(message, owner_user_id)
        self._chat_meta[(connection_id, message.chat.id)] = (
            record.chat_title,
            record.chat_username,
        )
        await self.storage.save_message(record)

        if not info:
            return
        settings = await self.settings_for(int(info["owner_user_id"]))
        if settings.get("backup_media") and self.vault.can_backup(record):
            self._spawn(self._backup_media(record))

    async def _backup_media(self, record: StoredMessage) -> None:
        path = await self.vault.backup(record)
        if path:
            await self.storage.set_local_path(
                record.connection_id, record.chat_id, record.message_id, path
            )

    async def on_edited_message(self, message: Message) -> None:
        connection_id = message.business_connection_id or ""
        info = await self.connection_info(connection_id)
        owner_user_id = info.get("owner_user_id") if info else None

        before = await self.storage.get_message(
            connection_id, message.chat.id, message.message_id
        )
        after = message_to_record(message, owner_user_id)
        # edit_date приходит как unix-время, date — как datetime.
        after.edited_at = int(message.edit_date or message.date.timestamp())
        # Счётчик правок ведёт apply_edit; здесь храним значение «до».
        after.edits = before.edits if before else 0

        unchanged = (
            before is not None
            and before.text == after.text
            and before.file_unique_id == after.file_unique_id
        )

        await self.storage.save_message(after)
        if unchanged:
            # Telegram присылает "правку" и при добавлении превью ссылки — это не изменение.
            return
        await self.storage.apply_edit(
            connection_id,
            message.chat.id,
            message.message_id,
            before.text if before else "",
            after.text,
            after.edited_at or 0,
        )
        after.edits += 1

        if not info:
            return
        settings = await self.settings_for(int(info["owner_user_id"]))
        if not settings.get("notify_edits"):
            return
        if after.outgoing and not settings.get("include_own"):
            return

        await self.send(
            int(info["owner_chat_id"]),
            fmt.edit_report(before, after, self.config.timezone, self.config.preview_limit),
            silent=bool(settings.get("silent")),
        )

    async def on_deleted_messages(self, event: BusinessMessagesDeleted) -> None:
        connection_id = event.business_connection_id
        self._chat_meta.setdefault(
            (connection_id, event.chat.id),
            (chat_display_title(event.chat), getattr(event.chat, "username", None)),
        )
        await self.buffer.add(connection_id, event.chat.id, event.message_ids)

    # ------------------------------------------------------------------- отчёты

    async def _report_deletions(
        self, connection_id: str, chat_id: int, message_ids: list[int]
    ) -> None:
        info = await self.connection_info(connection_id)
        records = await self.storage.get_messages(connection_id, chat_id, message_ids)
        await self.storage.mark_deleted(connection_id, chat_id, message_ids)
        remaining = await self.storage.count_alive_in_chat(connection_id, chat_id)

        if not info:
            logger.warning(
                "Удаление в неизвестном подключении %s — некому отправлять отчёт",
                connection_id,
            )
            return

        settings = await self.settings_for(int(info["owner_user_id"]))
        if not settings.get("notify_deletes"):
            return

        unknown_count = max(len(message_ids) - len(records), 0)
        chat_deleted = (
            len(message_ids) >= self.config.chat_delete_threshold and remaining == 0
        )

        if settings.get("include_own"):
            shown, hidden_own = records, 0
        else:
            shown = [record for record in records if not record.outgoing]
            hidden_own = len(records) - len(shown)

        if not shown and not unknown_count and not chat_deleted:
            # Удалены только собственные сообщения — скорее всего, вы сами.
            return

        title, username = self._chat_meta.get(
            (connection_id, chat_id),
            (records[0].chat_title if records else f"чат {chat_id}", None),
        )
        if not username and records:
            username = records[0].chat_username

        texts = fmt.deletion_report(
            chat_title=title,
            chat_username=username,
            records=shown,
            unknown_count=unknown_count,
            hidden_own=hidden_own,
            chat_deleted=chat_deleted,
            tz_name=self.config.timezone,
            preview_limit=self.config.preview_limit,
            max_messages=self.config.max_messages_in_report,
        )

        owner_chat_id = int(info["owner_chat_id"])
        silent = bool(settings.get("silent"))
        for text in texts:
            await self.send(owner_chat_id, text, silent=silent)
            await asyncio.sleep(0.05)

        await self._resend_media(owner_chat_id, shown, silent)

    async def _resend_media(
        self, owner_chat_id: int, records: list[StoredMessage], silent: bool
    ) -> None:
        sent = 0
        for record in records:
            if sent >= self.config.max_media_items:
                break
            if not record.media_type or not (record.file_id or record.local_path):
                continue
            caption = (
                f"🗑 Удалённое вложение от <b>{fmt.sender_label(record)}</b>\n"
                f"💬 {fmt.chat_label(record.chat_title, record.chat_username)}"
            )
            ok = await self.vault.resend(owner_chat_id, record, caption, silent)
            if ok:
                sent += 1
                await asyncio.sleep(0.1)
            else:
                await self.send(
                    owner_chat_id,
                    "⚠️ Вложение удалённого сообщения больше недоступно "
                    f"(сообщение {record.message_id}).",
                    silent=True,
                )
