from __future__ import annotations

import asyncio

import pytest

from tgmarket.ratelimit import (
    ApiGuard,
    FloodWaitTooLong,
    RateLimiter,
    flood_wait_seconds,
    is_transient,
)


class FakeFloodWaitError(Exception):
    """Mirrors Telethon's FloodWaitError shape without needing a request object."""

    def __init__(self, seconds: int) -> None:
        super().__init__(f"A wait of {seconds} seconds is required")
        self.seconds = seconds


class ServerError(Exception):
    pass


def test_flood_wait_seconds_extraction():
    assert flood_wait_seconds(FakeFloodWaitError(42)) == 42
    assert flood_wait_seconds(ValueError("nope")) is None


def test_flood_wait_seconds_from_real_telethon_error():
    from telethon.errors import FloodWaitError

    exc = FloodWaitError(request=None, capture=17)
    assert flood_wait_seconds(exc) == 17


def test_is_transient():
    assert is_transient(ServerError("500"))
    assert is_transient(ConnectionResetError())
    assert not is_transient(ValueError("bad input"))


async def test_rate_limiter_enforces_min_interval(fake_sleep):
    now = [0.0]
    limiter = RateLimiter(2.0, clock=lambda: now[0], sleep=fake_sleep)

    await limiter.acquire()
    assert fake_sleep.calls == [], "the first call goes straight through"
    await limiter.acquire()
    assert fake_sleep.calls == [2.0]


async def test_guard_sleeps_exactly_what_telegram_asked(fake_sleep):
    guard = ApiGuard(RateLimiter(), max_flood_wait=600, sleep=fake_sleep)
    attempts = []

    async def call():
        attempts.append(1)
        if len(attempts) == 1:
            raise FakeFloodWaitError(30)
        return "ok"

    assert await guard.call(call, label="test") == "ok"
    # 30s as instructed, plus one second of slack to avoid racing the server.
    assert fake_sleep.calls == [31]
    assert guard.flood_waits == 1
    assert guard.total_flood_seconds == 30


async def test_guard_refuses_absurd_flood_waits(fake_sleep):
    guard = ApiGuard(RateLimiter(), max_flood_wait=60, sleep=fake_sleep)

    async def call():
        raise FakeFloodWaitError(86400)

    with pytest.raises(FloodWaitTooLong) as excinfo:
        await guard.call(call, label="payments.getStarGifts")
    assert excinfo.value.seconds == 86400
    assert fake_sleep.calls == [], "never sleep out a penalty we refuse to accept"


async def test_guard_retries_transient_errors_then_gives_up(fake_sleep):
    guard = ApiGuard(RateLimiter(), max_retries=2, sleep=fake_sleep)
    calls = []

    async def always_failing():
        calls.append(1)
        raise ServerError("500")

    with pytest.raises(ServerError):
        await guard.call(always_failing, label="test")
    assert len(calls) == 3, "initial attempt plus max_retries"
    assert len(fake_sleep.calls) == 2
    assert fake_sleep.calls[1] > fake_sleep.calls[0], "backoff grows"


async def test_guard_does_not_retry_logic_errors(fake_sleep):
    guard = ApiGuard(RateLimiter(), sleep=fake_sleep)
    calls = []

    async def bad_request():
        calls.append(1)
        raise ValueError("GIFT_ID_INVALID")

    with pytest.raises(ValueError):
        await guard.call(bad_request, label="test")
    assert len(calls) == 1
    assert fake_sleep.calls == []


async def test_flood_pause_blocks_other_callers():
    """A flood wait must hold back every caller, not just the one that hit it."""
    now = [0.0]
    slept: list[float] = []

    async def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(0.5, clock=lambda: now[0], sleep=sleep)
    guard = ApiGuard(limiter, sleep=sleep)

    state = {"raised": False}

    async def flaky():
        if not state["raised"]:
            state["raised"] = True
            raise FakeFloodWaitError(10)
        return "ok"

    await guard.call(flaky, label="a")
    assert 11 in slept
    # The limiter's next slot is in the future for everyone else too.
    assert limiter._next_at >= now[0]


async def test_guard_is_concurrency_safe(fake_sleep):
    guard = ApiGuard(RateLimiter(), sleep=fake_sleep)

    async def ok(value):
        await asyncio.sleep(0)
        return value

    results = await asyncio.gather(*(guard.call(lambda v=i: ok(v)) for i in range(5)))
    assert results == [0, 1, 2, 3, 4]
