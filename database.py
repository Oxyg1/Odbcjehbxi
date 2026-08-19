"""SQLite persistence for generation history and favorites."""

import os
import time

import aiosqlite

from config import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    style TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(user_id, username)
);

CREATE INDEX IF NOT EXISTS idx_history_user ON history(user_id);
CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id);
"""


class Database:
    def __init__(self, path: str):
        self._path = path

    async def init(self) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        async with aiosqlite.connect(self._path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    async def add_history(self, user_id: int, username: str, style: str, status: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO history (user_id, username, style, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, style, status, time.time()),
            )
            await db.commit()

    async def add_history_batch(self, user_id: int, entries: list[tuple[str, str, str]]) -> None:
        """entries: list of (username, style, status)."""
        now = time.time()
        rows = [(user_id, username, style, status, now) for username, style, status in entries]
        async with aiosqlite.connect(self._path) as db:
            await db.executemany(
                "INSERT INTO history (user_id, username, style, status, created_at) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            await db.commit()

    async def get_history(self, user_id: int, limit: int = 20) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT username, style, status, created_at FROM history "
                "WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def add_favorite(self, user_id: int, username: str) -> bool:
        async with aiosqlite.connect(self._path) as db:
            try:
                await db.execute(
                    "INSERT INTO favorites (user_id, username, created_at) VALUES (?, ?, ?)",
                    (user_id, username, time.time()),
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def remove_favorite(self, user_id: int, username: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "DELETE FROM favorites WHERE user_id = ? AND username = ?",
                (user_id, username),
            )
            await db.commit()

    async def get_favorites(self, user_id: int) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT username, created_at FROM favorites WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


db = Database(config.database_path)
