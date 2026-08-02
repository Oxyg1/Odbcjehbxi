"""API pacing and FLOOD_WAIT handling.

Mishandled ``FLOOD_WAIT`` is the single most common way a userbot gets its
account limited: the process crashes, a supervisor restarts it, it immediately
re-issues the same request, and the server raises the penalty each round.  Every
MTProto call in this project therefore goes through :class:`ApiGuard`, which

* paces calls so bursts never leave the client,
* sleeps for exactly the number of seconds the server asked for, and
* refuses to wait out absurd penalties, surfacing them instead of looping.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Awaitable, Callable, Optional, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

#: Exceptions that mean "Telegram is unhappy right now, try again shortly".
_TRANSIENT_NAMES = {
    "ServerError",
    "TimedOutError",
    "TimeoutError",
    "ConnectionError",
    "InternalServerError",
    "ServiceUnavailableError",
    "RpcCallFailError",
    "RpcMcgetFailError",
}


class FloodWaitTooLong(RuntimeError):
    """Raised when Telegram demands a longer pause than we are willing to take."""

    def __init__(self, seconds: int, limit: int, label: str) -> None:
        super().__init__(
            f"{label}: FLOOD_WAIT of {seconds}s exceeds max_flood_wait={limit}s — "
            "stopping instead of hammering the API"
        )
        self.seconds = seconds
        self.limit = limit
        self.label = label


def flood_wait_seconds(exc: BaseException) -> Optional[int]:
    """Return the requested cooldown if ``exc`` is a flood error, else ``None``.

    Duck-typed on purpose: Telethon, its forks and MadelineProto-style wrappers
    all expose ``seconds``, and the exception class moves between library
    versions.
    """
    name = type(exc).__name__
    if "Flood" not in name and "FLOOD" not in str(exc).upper():
        return None
    seconds = getattr(exc, "seconds", None)
    if seconds is None:
        seconds = getattr(exc, "value", None)
    try:
        return max(0, int(seconds))
    except (TypeError, ValueError):
        return None


def is_transient(exc: BaseException) -> bool:
    """True for errors worth retrying with backoff (network blips, DC moves)."""
    if type(exc).__name__ in _TRANSIENT_NAMES:
        return True
    return isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError))


class RateLimiter:
    """Minimum-interval limiter shared by every outgoing request."""

    def __init__(self, min_interval: float = 0.0, *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self.min_interval = max(0.0, min_interval)
        self._clock = clock
        self._sleep = sleep
        self._next_at = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if not self.min_interval:
            return
        async with self._lock:
            now = self._clock()
            wait = self._next_at - now
            if wait > 0:
                await self._sleep(wait)
                now = self._clock()
            self._next_at = now + self.min_interval

    def pause_for(self, seconds: float) -> None:
        """Hold back every caller for ``seconds`` (used after a flood wait)."""
        self._next_at = max(self._next_at, self._clock() + max(0.0, seconds))


class ApiGuard:
    """Executes MTProto calls with pacing, flood handling and bounded retries."""

    def __init__(
        self,
        limiter: Optional[RateLimiter] = None,
        *,
        max_flood_wait: int = 600,
        max_retries: int = 3,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        on_flood: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        self.limiter = limiter or RateLimiter()
        self.max_flood_wait = max_flood_wait
        self.max_retries = max_retries
        self._sleep = sleep
        self._on_flood = on_flood
        self.flood_waits = 0
        self.total_flood_seconds = 0

    async def call(self, func: Callable[[], Awaitable[T]], *, label: str = "request") -> T:
        """Run ``func`` (a zero-argument coroutine factory) under the guard."""
        attempt = 0
        while True:
            await self.limiter.acquire()
            try:
                return await func()
            except Exception as exc:  # noqa: BLE001 - re-raised below unless handled
                seconds = flood_wait_seconds(exc)
                if seconds is not None:
                    await self._handle_flood(label, seconds)
                    continue
                if is_transient(exc) and attempt < self.max_retries:
                    delay = self._backoff(attempt)
                    attempt += 1
                    log.warning("%s: %s (%s) — retry %d/%d in %.1fs",
                                label, type(exc).__name__, exc, attempt, self.max_retries, delay)
                    await self._sleep(delay)
                    continue
                raise

    async def _handle_flood(self, label: str, seconds: int) -> None:
        if seconds > self.max_flood_wait:
            raise FloodWaitTooLong(seconds, self.max_flood_wait, label)
        self.flood_waits += 1
        self.total_flood_seconds += seconds
        # +1s of slack: sleeping the exact value occasionally races the server
        # clock and earns a second, longer penalty.
        delay = seconds + 1
        log.warning("%s: FLOOD_WAIT — pausing for %ds as instructed by Telegram", label, seconds)
        if self._on_flood is not None:
            self._on_flood(label, seconds)
        self.limiter.pause_for(delay)
        await self._sleep(delay)

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with jitter, capped so restarts stay bounded."""
        base = min(2.0 ** attempt, 30.0)
        return base + random.uniform(0, base / 2)
