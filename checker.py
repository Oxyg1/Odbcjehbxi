"""Async availability checking for Telegram usernames via t.me and fragment.com.

Notes on scope: this module does real HTTP checks against the public, unauthenticated
pages of t.me and fragment.com (the same pages a browser loads when you visit them
manually). It does not attempt to defeat Cloudflare challenges or headless-render JS --
if fragment.com serves a JS challenge instead of the price page, we fall back to
"unknown" for that source rather than pretending to know the answer.
"""

import asyncio
import itertools
import logging
import random
import time
from dataclasses import dataclass
from enum import Enum

import aiohttp
from selectolax.parser import HTMLParser

from config import config

logger = logging.getLogger("checker")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
]


class Availability(str, Enum):
    FREE = "free"
    TAKEN = "taken"
    FRAGMENT_FOR_SALE = "fragment_for_sale"
    UNKNOWN = "unknown"


@dataclass
class SourceResult:
    availability: Availability
    detail: str = ""


@dataclass
class CheckResult:
    username: str
    telegram: SourceResult
    fragment: SourceResult
    checked_at: float

    @property
    def is_free_everywhere(self) -> bool:
        return self.telegram.availability == Availability.FREE and self.fragment.availability in (
            Availability.FREE,
            Availability.UNKNOWN,
        )


class _TTLCache:
    def __init__(self, ttl_seconds: int):
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, CheckResult]] = {}

    def get(self, key: str) -> CheckResult | None:
        entry = self._store.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: CheckResult) -> None:
        self._store[key] = (time.monotonic() + self._ttl, value)


class _RateLimiter:
    """Simple token-bucket limiter shared per domain."""

    def __init__(self, rate_per_second: float):
        self._interval = 1.0 / rate_per_second if rate_per_second > 0 else 0
        self._lock = asyncio.Lock()
        self._next_slot = 0.0

    async def wait(self) -> None:
        if self._interval == 0:
            return
        async with self._lock:
            now = time.monotonic()
            start = max(now, self._next_slot)
            self._next_slot = start + self._interval
            delay = start - now
        if delay > 0:
            await asyncio.sleep(delay)


class UsernameChecker:
    def __init__(self):
        self._cache = _TTLCache(config.cache_ttl_seconds)
        self._telegram_limiter = _RateLimiter(config.rate_limit_per_second)
        self._fragment_limiter = _RateLimiter(config.rate_limit_per_second)
        self._proxy_cycle = itertools.cycle(config.proxies) if config.proxies else None

    def _next_proxy(self) -> str | None:
        return next(self._proxy_cycle) if self._proxy_cycle else None

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> tuple[int, str] | None:
        timeout = aiohttp.ClientTimeout(total=config.request_timeout_seconds)
        last_error: Exception | None = None

        for attempt in range(config.max_retries):
            try:
                async with session.get(
                    url,
                    headers=self._headers(),
                    timeout=timeout,
                    proxy=self._next_proxy(),
                    allow_redirects=True,
                ) as resp:
                    text = await resp.text(errors="ignore")
                    return resp.status, text
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
                backoff = (2**attempt) + random.uniform(0, 0.5)
                logger.warning("Fetch failed for %s (attempt %d/%d): %s", url, attempt + 1, config.max_retries, exc)
                if attempt < config.max_retries - 1:
                    await asyncio.sleep(backoff)

        logger.error("Giving up on %s after %d attempts: %s", url, config.max_retries, last_error)
        return None

    async def _check_telegram(self, session: aiohttp.ClientSession, username: str) -> SourceResult:
        await self._telegram_limiter.wait()
        result = await self._fetch(session, f"https://t.me/{username}")
        if result is None:
            return SourceResult(Availability.UNKNOWN, "network error")

        status, html = result
        if status == 404:
            return SourceResult(Availability.FREE, "404")

        # Check the free-username landing page marker *before* looking for profile
        # elements: t.me renders a ".tgme_page_title" header on that landing page too
        # (it's just the generic page title, showing the requested handle regardless
        # of whether it's registered), so treating it as a "taken" signal on its own
        # flags almost every free username as taken. ".tgme_page_extra_info" (bio /
        # subscriber count / online status) is specific to an actual profile page and
        # is a reliable taken signal on its own.
        if "If you have Telegram" in html:
            return SourceResult(Availability.FREE, "no profile card")

        tree = HTMLParser(html)
        if tree.css_first(".tgme_page_extra_info"):
            return SourceResult(Availability.TAKEN, "profile page present")

        return SourceResult(Availability.UNKNOWN, f"unrecognized response (status {status})")

    async def _check_fragment(self, session: aiohttp.ClientSession, username: str) -> SourceResult:
        await self._fragment_limiter.wait()
        result = await self._fetch(session, f"https://fragment.com/username/{username}")
        if result is None:
            return SourceResult(Availability.UNKNOWN, "network error")

        status, html = result

        if status == 403 or "cf-browser-verification" in html or "Just a moment" in html:
            return SourceResult(Availability.UNKNOWN, "blocked by anti-bot challenge")

        if "Username not found" in html or status == 404:
            return SourceResult(Availability.FREE, "not found on fragment")

        if "already taken" in html.lower() or "is unavailable" in html.lower():
            return SourceResult(Availability.TAKEN, "already taken")

        tree = HTMLParser(html)
        price_node = tree.css_first(".tm-value") or tree.css_first("[class*='price']")
        if price_node and price_node.text(strip=True):
            return SourceResult(Availability.FRAGMENT_FOR_SALE, price_node.text(strip=True))

        return SourceResult(Availability.UNKNOWN, f"unrecognized response (status {status})")

    async def check(self, session: aiohttp.ClientSession, username: str) -> CheckResult:
        cached = self._cache.get(username)
        if cached is not None:
            return cached

        telegram_result = await self._check_telegram(session, username)
        if telegram_result.availability == Availability.TAKEN:
            # Already registered directly on Telegram -- Fragment can't sell it, so
            # there's no point spending a request (and rate-limit budget) on it.
            fragment_result = SourceResult(Availability.TAKEN, "skipped: t.me already taken")
        else:
            fragment_result = await self._check_fragment(session, username)

        result = CheckResult(
            username=username,
            telegram=telegram_result,
            fragment=fragment_result,
            checked_at=time.time(),
        )
        self._cache.set(username, result)
        return result

    async def check_many(self, usernames: list[str]) -> list[CheckResult]:
        connector = aiohttp.TCPConnector(limit=20)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [self.check(session, name) for name in usernames]
            return await asyncio.gather(*tasks)


checker = UsernameChecker()
