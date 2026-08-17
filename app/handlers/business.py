"""Апдейты бизнес-режима: подключение, новые/изменённые/удалённые сообщения."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import BusinessConnection, BusinessMessagesDeleted, Message

from ..tracker import Tracker

logger = logging.getLogger(__name__)


def create_router() -> Router:
    """Новый роутер на каждый вызов — aiogram не даёт подключать один и тот же дважды."""

    router = Router(name="business")

    @router.business_connection()
    async def on_business_connection(event: BusinessConnection, tracker: Tracker) -> None:
        logger.info(
            "Подключение %s пользователя %s: enabled=%s",
            event.id,
            event.user.id,
            event.is_enabled,
        )
        await tracker.on_connection(event)

    @router.business_message()
    async def on_business_message(message: Message, tracker: Tracker) -> None:
        await tracker.on_message(message)

    @router.edited_business_message()
    async def on_edited_business_message(message: Message, tracker: Tracker) -> None:
        await tracker.on_edited_message(message)

    @router.deleted_business_messages()
    async def on_deleted_business_messages(
        event: BusinessMessagesDeleted, tracker: Tracker
    ) -> None:
        logger.info(
            "Удалено %s сообщ. в чате %s (подключение %s)",
            len(event.message_ids),
            event.chat.id,
            event.business_connection_id,
        )
        await tracker.on_deleted_messages(event)

    return router
