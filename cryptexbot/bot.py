"""Wiring: build the bot, the dispatcher, and the services handlers depend on."""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from .config import Settings, get_settings
from .handlers import build_router
from .services.artwork import ArtworkProvider
from .services.quests import build_quest_provider
from .services.rewards import build_reward_provider
from .state import build_state_store

log = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="vault", description="Open a fresh vault"),
    BotCommand(command="start", description="Open a fresh vault"),
]


def create_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(settings: Settings) -> Dispatcher:
    store = build_state_store(
        settings.state_backend, settings.redis_url, settings.state_ttl
    )
    artwork = ArtworkProvider()
    artwork.ensure_rendered()
    quests = build_quest_provider(settings)
    rewards = build_reward_provider(settings)

    # Anything passed here is injected into handlers by parameter name.
    dp = Dispatcher(
        settings=settings,
        store=store,
        artwork=artwork,
        quests=quests,
        rewards=rewards,
    )
    dp.include_router(build_router())
    dp.shutdown.register(_on_shutdown)
    return dp


async def _on_shutdown(store) -> None:  # noqa: ANN001 - injected by aiogram
    await store.close()


async def run() -> None:
    settings = get_settings()
    bot = create_bot(settings)
    dp = create_dispatcher(settings)

    # Everything that touches the network lives inside the try: a bad token or
    # an unreachable API during startup would otherwise leak the HTTP session.
    try:
        await bot.set_my_commands(COMMANDS)
        me = await bot.get_me()
        log.info("CryptexBot online as @%s", me.username)

        # Zero-Spam means we only ever care about fresh taps: stale updates from
        # a downtime window would edit messages whose state no longer exists.
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
        )
    finally:
        await bot.session.close()
