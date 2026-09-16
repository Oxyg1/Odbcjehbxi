"""Vault state: the dial positions of every live puzzle message.

State is keyed by ``(chat_id, message_id)`` so a single chat can hold several
independent vaults, and so the same message keeps its dials across restarts
when the Redis backend is used.

Two backends ship here; both satisfy :class:`StateStore`. Swap them with the
``STATE_BACKEND`` env var — nothing else in the codebase knows the difference.
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Iterable

VaultKey = tuple[int, int]  # (chat_id, message_id)


@dataclass(slots=True)
class VaultState:
    """Everything a single puzzle message needs to re-render itself."""

    dials: list[int]
    attempts: int = 0
    opened: bool = False
    owner_id: int | None = None
    reward: str | None = None
    extra: dict = field(default_factory=dict)

    @classmethod
    def new(cls, dial_count: int, owner_id: int | None = None) -> "VaultState":
        return cls(dials=[0] * dial_count, owner_id=owner_id)

    def turn(self, index: int) -> int:
        """Advance one dial 0 -> 1 -> ... -> 9 -> 0 and return its new value."""
        self.dials[index] = (self.dials[index] + 1) % 10
        self.attempts += 1
        return self.dials[index]

    def matches(self, code: Iterable[int]) -> bool:
        return self.dials == list(code)

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> "VaultState":
        return cls(**json.loads(raw))


class StateStore(ABC):
    """Fast key/value store for vault state, plus a per-vault mutex.

    The lock matters: Telegram happily delivers several callback queries from
    the same user within a few milliseconds (impatient tapping). Without a
    mutex, two handlers can read the same dials, both increment, and one write
    silently loses a turn.
    """

    @abstractmethod
    async def get(self, key: VaultKey) -> VaultState | None: ...

    @abstractmethod
    async def set(self, key: VaultKey, state: VaultState) -> None: ...

    @abstractmethod
    async def delete(self, key: VaultKey) -> None: ...

    @abstractmethod
    def lock(self, key: VaultKey) -> asyncio.Lock: ...

    async def close(self) -> None:  # pragma: no cover - backend specific
        return None


class MemoryStateStore(StateStore):
    """Process-local store. Perfect for a single worker; state dies on restart.

    Bounded with an LRU so a long-running bot can't grow without limit.
    """

    def __init__(self, max_entries: int = 50_000) -> None:
        self._data: "OrderedDict[VaultKey, VaultState]" = OrderedDict()
        self._locks: dict[VaultKey, asyncio.Lock] = {}
        self._max_entries = max_entries

    async def get(self, key: VaultKey) -> VaultState | None:
        state = self._data.get(key)
        if state is not None:
            self._data.move_to_end(key)
        return state

    async def set(self, key: VaultKey, state: VaultState) -> None:
        self._data[key] = state
        self._data.move_to_end(key)
        while len(self._data) > self._max_entries:
            evicted, _ = self._data.popitem(last=False)
            self._locks.pop(evicted, None)

    async def delete(self, key: VaultKey) -> None:
        self._data.pop(key, None)
        self._locks.pop(key, None)

    def lock(self, key: VaultKey) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())


class RedisStateStore(StateStore):
    """Shared store, so several bot workers can serve the same vault.

    The asyncio lock here is still process-local. For a true multi-worker
    deployment, promote it to a Redis lock (``redis.asyncio.lock.Lock``);
    the interface does not change.
    """

    def __init__(self, url: str, ttl: int = 86_400, prefix: str = "cryptex:vault") -> None:
        from redis.asyncio import from_url  # imported lazily: optional dependency

        self._redis = from_url(url, decode_responses=True)
        self._ttl = ttl
        self._prefix = prefix
        self._locks: dict[VaultKey, asyncio.Lock] = {}

    def _key(self, key: VaultKey) -> str:
        chat_id, message_id = key
        return f"{self._prefix}:{chat_id}:{message_id}"

    async def get(self, key: VaultKey) -> VaultState | None:
        raw = await self._redis.get(self._key(key))
        return VaultState.from_json(raw) if raw else None

    async def set(self, key: VaultKey, state: VaultState) -> None:
        await self._redis.set(self._key(key), state.to_json(), ex=self._ttl)

    async def delete(self, key: VaultKey) -> None:
        await self._redis.delete(self._key(key))
        self._locks.pop(key, None)

    def lock(self, key: VaultKey) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    async def close(self) -> None:
        await self._redis.aclose()


def build_state_store(backend: str, redis_url: str, ttl: int) -> StateStore:
    if backend == "redis":
        return RedisStateStore(redis_url, ttl=ttl)
    return MemoryStateStore()
