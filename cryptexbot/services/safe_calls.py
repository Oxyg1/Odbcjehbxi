"""Defensive wrappers around the Bot API calls this bot leans on.

Three failure modes show up constantly in a callback-driven, single-message bot
and none of them deserve a traceback:

* ``query is too old`` / ``query ID is invalid`` — the user tapped, then the
  network (or a slow handler) burned the 15s window Telegram gives us to answer
  a callback query. The tap is already lost; the edit still went through.
* ``message is not modified`` — we rendered markup identical to what is already
  on screen. Harmless and expected whenever two taps race.
* ``TelegramRetryAfter`` — flood control. Wait exactly as long as we are told,
  then try once more.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, TypeVar

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import CallbackQuery

log = logging.getLogger(__name__)

T = TypeVar("T")

# Substrings of BadRequest descriptions that are safe to swallow.
_IGNORABLE = (
    "message is not modified",
    "query is too old",
    "query id is invalid",
    "response timeout expired",
    "message to edit not found",
    "message can't be edited",
)


def _is_ignorable(error: TelegramBadRequest) -> bool:
    text = str(error).lower()
    return any(fragment in text for fragment in _IGNORABLE)


async def safe_call(
    func: Callable[..., Awaitable[T]], *args: Any, retries: int = 1, **kwargs: Any
) -> T | None:
    """Run a Bot API call, absorbing the noise. Returns ``None`` if it was lost.

    Real errors (bad token, malformed payload, ...) still propagate — this is a
    filter for expected races, not a blanket ``except Exception``.
    """
    attempt = 0
    while True:
        try:
            return await func(*args, **kwargs)
        except TelegramRetryAfter as error:
            if attempt >= retries:
                log.warning("flood control, giving up after %s retries", attempt)
                return None
            log.info("flood control: sleeping %ss", error.retry_after)
            await asyncio.sleep(error.retry_after)
            attempt += 1
        except TelegramBadRequest as error:
            if _is_ignorable(error):
                log.debug("ignored bad request: %s", error)
                return None
            raise
        except TelegramForbiddenError as error:
            # User blocked the bot or left the chat; nothing to recover.
            log.info("forbidden, dropping update: %s", error)
            return None
        except TelegramNetworkError as error:
            if attempt >= retries:
                log.warning("network error, giving up: %s", error)
                return None
            await asyncio.sleep(0.5 * (attempt + 1))
            attempt += 1


async def ack(query: CallbackQuery, text: str | None = None, alert: bool = False) -> None:
    """Acknowledge a callback query; never raise if the window already closed.

    Always call this *after* the edit, not before: the visible dial turn is
    worth more than the spinner, and answering first wastes part of the
    15-second window on a round trip.
    """
    await safe_call(query.answer, text=text, show_alert=alert, retries=0)
