"""Хранилище: бизнес-подключения, кэш сообщений, история правок, настройки."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

import aiosqlite

from .models import StoredMessage

SCHEMA = """
CREATE TABLE IF NOT EXISTS connections (
    connection_id  TEXT PRIMARY KEY,
    owner_user_id  INTEGER NOT NULL,
    owner_chat_id  INTEGER NOT NULL,
    owner_name     TEXT NOT NULL DEFAULT '',
    is_enabled     INTEGER NOT NULL DEFAULT 1,
    can_reply      INTEGER NOT NULL DEFAULT 0,
    created_at     INTEGER NOT NULL,
    updated_at     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    connection_id   TEXT NOT NULL,
    chat_id         INTEGER NOT NULL,
    message_id      INTEGER NOT NULL,
    chat_title      TEXT NOT NULL DEFAULT '',
    chat_username   TEXT,
    sender_id       INTEGER,
    sender_name     TEXT NOT NULL DEFAULT '',
    sender_username TEXT,
    outgoing        INTEGER NOT NULL DEFAULT 0,
    text            TEXT NOT NULL DEFAULT '',
    media_type      TEXT,
    file_id         TEXT,
    file_unique_id  TEXT,
    file_size       INTEGER,
    local_path      TEXT,
    date            INTEGER NOT NULL DEFAULT 0,
    edited_at       INTEGER,
    edits           INTEGER NOT NULL DEFAULT 0,
    deleted_at      INTEGER,
    extra           TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (connection_id, chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages (connection_id, chat_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_messages_date ON messages (date);

CREATE TABLE IF NOT EXISTS edits (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id TEXT NOT NULL,
    chat_id       INTEGER NOT NULL,
    message_id    INTEGER NOT NULL,
    old_text      TEXT NOT NULL DEFAULT '',
    new_text      TEXT NOT NULL DEFAULT '',
    edited_at     INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_edits_message ON edits (connection_id, chat_id, message_id);

CREATE TABLE IF NOT EXISTS settings (
    owner_user_id INTEGER NOT NULL,
    key           TEXT NOT NULL,
    value         TEXT NOT NULL,
    PRIMARY KEY (owner_user_id, key)
);
"""

_MESSAGE_COLUMNS = (
    "connection_id, chat_id, message_id, chat_title, chat_username, sender_id, "
    "sender_name, sender_username, outgoing, text, media_type, file_id, "
    "file_unique_id, file_size, local_path, date, edited_at, edits, deleted_at, extra"
)


def _row_to_message(row: aiosqlite.Row) -> StoredMessage:
    return StoredMessage(
        connection_id=row["connection_id"],
        chat_id=row["chat_id"],
        message_id=row["message_id"],
        chat_title=row["chat_title"],
        chat_username=row["chat_username"],
        sender_id=row["sender_id"],
        sender_name=row["sender_name"],
        sender_username=row["sender_username"],
        outgoing=bool(row["outgoing"]),
        text=row["text"],
        media_type=row["media_type"],
        file_id=row["file_id"],
        file_unique_id=row["file_unique_id"],
        file_size=row["file_size"],
        local_path=row["local_path"],
        date=row["date"],
        edited_at=row["edited_at"],
        edits=row["edits"],
        deleted_at=row["deleted_at"],
        extra=json.loads(row["extra"] or "{}"),
    )


class Storage:
    """Тонкая обёртка над SQLite. Все методы — корутины."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._db: aiosqlite.Connection | None = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:  # pragma: no cover - защита от неправильного порядка вызовов
            raise RuntimeError("Storage.connect() не был вызван")
        return self._db

    async def connect(self) -> "Storage":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        return self

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def __aenter__(self) -> "Storage":
        return await self.connect()

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    # ------------------------------------------------------------------ связи

    async def save_connection(
        self,
        connection_id: str,
        owner_user_id: int,
        owner_chat_id: int,
        owner_name: str,
        is_enabled: bool,
        can_reply: bool,
    ) -> None:
        now = int(time.time())
        await self.db.execute(
            """
            INSERT INTO connections (connection_id, owner_user_id, owner_chat_id,
                                     owner_name, is_enabled, can_reply, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(connection_id) DO UPDATE SET
                owner_user_id = excluded.owner_user_id,
                owner_chat_id = excluded.owner_chat_id,
                owner_name    = excluded.owner_name,
                is_enabled    = excluded.is_enabled,
                can_reply     = excluded.can_reply,
                updated_at    = excluded.updated_at
            """,
            (
                connection_id,
                owner_user_id,
                owner_chat_id,
                owner_name,
                int(is_enabled),
                int(can_reply),
                now,
                now,
            ),
        )
        await self.db.commit()

    async def get_connection(self, connection_id: str) -> dict[str, Any] | None:
        async with self.db.execute(
            "SELECT * FROM connections WHERE connection_id = ?", (connection_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_connections_for_owner(self, owner_user_id: int) -> list[dict[str, Any]]:
        async with self.db.execute(
            "SELECT * FROM connections WHERE owner_user_id = ? ORDER BY updated_at DESC",
            (owner_user_id,),
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    # -------------------------------------------------------------- сообщения

    async def save_message(self, message: StoredMessage) -> None:
        await self.db.execute(
            f"""
            INSERT INTO messages ({_MESSAGE_COLUMNS})
            VALUES ({", ".join("?" * 20)})
            ON CONFLICT(connection_id, chat_id, message_id) DO UPDATE SET
                text        = excluded.text,
                media_type  = excluded.media_type,
                file_id     = excluded.file_id,
                file_unique_id = excluded.file_unique_id,
                file_size   = excluded.file_size,
                local_path  = COALESCE(excluded.local_path, messages.local_path),
                extra       = excluded.extra
            """,
            (
                message.connection_id,
                message.chat_id,
                message.message_id,
                message.chat_title,
                message.chat_username,
                message.sender_id,
                message.sender_name,
                message.sender_username,
                int(message.outgoing),
                message.text,
                message.media_type,
                message.file_id,
                message.file_unique_id,
                message.file_size,
                message.local_path,
                message.date,
                message.edited_at,
                message.edits,
                message.deleted_at,
                json.dumps(message.extra, ensure_ascii=False),
            ),
        )
        await self.db.commit()

    async def set_local_path(
        self, connection_id: str, chat_id: int, message_id: int, path: str
    ) -> None:
        await self.db.execute(
            "UPDATE messages SET local_path = ? WHERE connection_id = ? AND chat_id = ? AND message_id = ?",
            (path, connection_id, chat_id, message_id),
        )
        await self.db.commit()

    async def get_message(
        self, connection_id: str, chat_id: int, message_id: int
    ) -> StoredMessage | None:
        async with self.db.execute(
            "SELECT * FROM messages WHERE connection_id = ? AND chat_id = ? AND message_id = ?",
            (connection_id, chat_id, message_id),
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_message(row) if row else None

    async def get_messages(
        self, connection_id: str, chat_id: int, message_ids: Sequence[int]
    ) -> list[StoredMessage]:
        if not message_ids:
            return []
        placeholders = ", ".join("?" * len(message_ids))
        async with self.db.execute(
            f"""
            SELECT * FROM messages
            WHERE connection_id = ? AND chat_id = ? AND message_id IN ({placeholders})
            ORDER BY message_id
            """,
            (connection_id, chat_id, *message_ids),
        ) as cursor:
            return [_row_to_message(row) for row in await cursor.fetchall()]

    async def mark_deleted(
        self, connection_id: str, chat_id: int, message_ids: Iterable[int]
    ) -> None:
        ids = list(message_ids)
        if not ids:
            return
        now = int(time.time())
        placeholders = ", ".join("?" * len(ids))
        await self.db.execute(
            f"""
            UPDATE messages SET deleted_at = ?
            WHERE connection_id = ? AND chat_id = ? AND message_id IN ({placeholders})
              AND deleted_at IS NULL
            """,
            (now, connection_id, chat_id, *ids),
        )
        await self.db.commit()

    async def apply_edit(
        self,
        connection_id: str,
        chat_id: int,
        message_id: int,
        old_text: str,
        new_text: str,
        edited_at: int,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO edits (connection_id, chat_id, message_id, old_text, new_text, edited_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (connection_id, chat_id, message_id, old_text, new_text, edited_at),
        )
        await self.db.execute(
            """
            UPDATE messages SET text = ?, edited_at = ?, edits = edits + 1
            WHERE connection_id = ? AND chat_id = ? AND message_id = ?
            """,
            (new_text, edited_at, connection_id, chat_id, message_id),
        )
        await self.db.commit()

    async def count_alive_in_chat(self, connection_id: str, chat_id: int) -> int:
        async with self.db.execute(
            """
            SELECT COUNT(*) AS n FROM messages
            WHERE connection_id = ? AND chat_id = ? AND deleted_at IS NULL
            """,
            (connection_id, chat_id),
        ) as cursor:
            row = await cursor.fetchone()
        return int(row["n"]) if row else 0

    async def stats(self, owner_user_id: int) -> dict[str, int]:
        async with self.db.execute(
            """
            SELECT
                COUNT(*)                                        AS total,
                COALESCE(SUM(m.deleted_at IS NOT NULL), 0)      AS deleted,
                COALESCE(SUM(m.edits > 0), 0)                   AS edited,
                COUNT(DISTINCT m.chat_id)                       AS chats
            FROM messages m
            JOIN connections c ON c.connection_id = m.connection_id
            WHERE c.owner_user_id = ?
            """,
            (owner_user_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return {
            "total": int(row["total"]) if row else 0,
            "deleted": int(row["deleted"]) if row else 0,
            "edited": int(row["edited"]) if row else 0,
            "chats": int(row["chats"]) if row else 0,
        }

    # --------------------------------------------------------------- настройки

    async def get_settings(
        self, owner_user_id: int, defaults: dict[str, bool]
    ) -> dict[str, bool]:
        async with self.db.execute(
            "SELECT key, value FROM settings WHERE owner_user_id = ?", (owner_user_id,)
        ) as cursor:
            stored = {row["key"]: row["value"] == "1" for row in await cursor.fetchall()}
        return {**defaults, **{k: v for k, v in stored.items() if k in defaults}}

    async def set_setting(self, owner_user_id: int, key: str, value: bool) -> None:
        await self.db.execute(
            """
            INSERT INTO settings (owner_user_id, key, value) VALUES (?, ?, ?)
            ON CONFLICT(owner_user_id, key) DO UPDATE SET value = excluded.value
            """,
            (owner_user_id, key, "1" if value else "0"),
        )
        await self.db.commit()

    # --------------------------------------------------------------- обслуживание

    async def cleanup(self, retention_days: int) -> tuple[int, list[str]]:
        """Удаляет старые записи. Возвращает (сколько удалено, пути файлов на диске)."""

        if retention_days <= 0:
            return 0, []
        threshold = int(time.time()) - retention_days * 86400
        async with self.db.execute(
            "SELECT local_path FROM messages WHERE date < ? AND local_path IS NOT NULL",
            (threshold,),
        ) as cursor:
            paths = [row["local_path"] for row in await cursor.fetchall()]
        cursor = await self.db.execute("DELETE FROM messages WHERE date < ?", (threshold,))
        removed = cursor.rowcount or 0
        await self.db.execute("DELETE FROM edits WHERE edited_at < ?", (threshold,))
        await self.db.commit()
        return removed, paths

    async def purge_owner(self, owner_user_id: int) -> tuple[int, list[str]]:
        """Полностью стирает кэш сообщений владельца."""

        async with self.db.execute(
            """
            SELECT m.local_path FROM messages m
            JOIN connections c ON c.connection_id = m.connection_id
            WHERE c.owner_user_id = ? AND m.local_path IS NOT NULL
            """,
            (owner_user_id,),
        ) as cursor:
            paths = [row["local_path"] for row in await cursor.fetchall()]
        cursor = await self.db.execute(
            """
            DELETE FROM messages WHERE connection_id IN (
                SELECT connection_id FROM connections WHERE owner_user_id = ?
            )
            """,
            (owner_user_id,),
        )
        removed = cursor.rowcount or 0
        await self.db.execute(
            """
            DELETE FROM edits WHERE connection_id IN (
                SELECT connection_id FROM connections WHERE owner_user_id = ?
            )
            """,
            (owner_user_id,),
        )
        await self.db.commit()
        return removed, paths
