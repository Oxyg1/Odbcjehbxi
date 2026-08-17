"""Склейка удалений: Telegram присылает удаление чата пачками апдейтов."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Iterable

logger = logging.getLogger(__name__)

FlushCallback = Callable[[str, int, list[int]], Awaitable[None]]


class DeletionBuffer:
    """Копит id удалённых сообщений по (подключение, чат) и отдаёт их одной пачкой.

    Каждое новое удаление продлевает паузу, но не дольше ``max_wait`` от первого,
    чтобы удаление большой переписки не откладывалось бесконечно.
    """

    def __init__(
        self,
        delay: float,
        flush: FlushCallback,
        max_wait: float | None = None,
        max_ids: int = 20_000,
    ) -> None:
        self._delay = max(delay, 0.0)
        self._flush = flush
        self._max_wait = max_wait if max_wait is not None else max(delay * 5, delay)
        self._max_ids = max_ids
        self._pending: dict[tuple[str, int], set[int]] = {}
        self._started: dict[tuple[str, int], float] = {}
        self._timers: dict[tuple[str, int], asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def add(
        self, connection_id: str, chat_id: int, message_ids: Iterable[int]
    ) -> None:
        key = (connection_id, chat_id)
        ids = set(message_ids)
        if not ids:
            return

        async with self._lock:
            bucket = self._pending.setdefault(key, set())
            if len(bucket) < self._max_ids:
                bucket.update(ids)
            self._started.setdefault(key, time.monotonic())
            timer = self._timers.pop(key, None)
            if timer is not None:
                timer.cancel()

            waited = time.monotonic() - self._started[key]
            delay = min(self._delay, max(self._max_wait - waited, 0.0))
            self._timers[key] = asyncio.create_task(self._schedule(key, delay))

    async def _schedule(self, key: tuple[str, int], delay: float) -> None:
        try:
            if delay > 0:
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        await self._fire(key)

    async def _fire(self, key: tuple[str, int]) -> None:
        async with self._lock:
            ids = self._pending.pop(key, set())
            self._started.pop(key, None)
            self._timers.pop(key, None)
        if not ids:
            return
        connection_id, chat_id = key
        try:
            await self._flush(connection_id, chat_id, sorted(ids))
        except Exception:  # noqa: BLE001 - фоновая задача не должна ронять бота
            logger.exception("Ошибка при отправке отчёта об удалении (чат %s)", chat_id)

    async def close(self) -> None:
        """Досылает всё накопленное — вызывается при остановке бота."""

        async with self._lock:
            keys = list(self._pending)
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
        for key in keys:
            await self._fire(key)
