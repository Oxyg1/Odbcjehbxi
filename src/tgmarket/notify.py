"""Out-of-band notifications through a plain Bot API bot.

An autonomous process on a VPS is a black box: without this you find out it
died a week later.  Notifications go through a *separate* bot token rather than
the userbot account, so a limited account still reports its own state.

Delivery never raises — a broken notifier must not take the bot down with it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from typing import Optional

from .config import NotifyConfig

log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/sendMessage"
_TIMEOUT = 15


class Notifier:
    """Sends short status messages; falls back to logging when disabled."""

    def __init__(self, config: NotifyConfig) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled and self.config.bot_token and self.config.chat_id)

    async def send(self, text: str, *, level: str = "info") -> bool:
        prefix = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}.get(level, "")
        body = f"{prefix} {text}".strip()
        if not self.enabled:
            log.debug("notification (disabled, not sent): %s", text)
            return False
        try:
            return await asyncio.to_thread(self._post, body)
        except Exception as exc:  # noqa: BLE001 - notifications are best-effort
            log.warning("notification failed: %s: %s", type(exc).__name__, exc)
            return False

    async def info(self, text: str) -> bool:
        return await self.send(text, level="info")

    async def success(self, text: str) -> bool:
        return await self.send(text, level="success")

    async def warning(self, text: str) -> bool:
        return await self.send(text, level="warning")

    async def error(self, text: str) -> bool:
        return await self.send(text, level="error")

    def _post(self, text: str) -> bool:
        payload = json.dumps(
            {
                "chat_id": self.config.chat_id,
                "text": text[:4096],
                "disable_web_page_preview": True,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            _API.format(token=self.config.bot_token),
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                return 200 <= response.status < 300
        except urllib.error.HTTPError as exc:
            log.warning("notification rejected by Bot API: %s %s", exc.code, exc.reason)
            return False


class NullNotifier(Notifier):
    """No-op notifier for tests and for ``--no-notify`` runs."""

    def __init__(self) -> None:
        super().__init__(NotifyConfig(enabled=False))

    async def send(self, text: str, *, level: str = "info") -> bool:
        log.debug("notification suppressed: %s", text)
        return False


def build_notifier(config: Optional[NotifyConfig]) -> Notifier:
    if config is None or not config.enabled:
        return NullNotifier()
    return Notifier(config)
