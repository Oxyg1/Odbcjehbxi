"""Last-resort handler: log, and never let one bad update kill the poller."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import ErrorEvent

from ..services.safe_calls import ack

log = logging.getLogger(__name__)

router = Router(name="errors")


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    log.exception("unhandled error while processing update", exc_info=event.exception)

    # If the update was a tap, release the user's spinner instead of leaving it
    # turning until it times out.
    query = event.update.callback_query
    if query is not None:
        await ack(query, "Something jammed. Try again.")

    return True  # handled: keep polling
