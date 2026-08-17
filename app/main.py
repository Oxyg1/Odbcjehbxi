"""Точка входа: сборка бота и запуск long-polling."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from .config import Config
from .db import Storage
from .handlers import build_router
from .tracker import Tracker

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL = 6 * 3600

COMMANDS = [
    BotCommand(command="status", description="Состояние подключения"),
    BotCommand(command="settings", description="Настройки уведомлений"),
    BotCommand(command="stats", description="Статистика кэша"),
    BotCommand(command="purge", description="Стереть кэш"),
    BotCommand(command="help", description="Справка"),
]


async def cleanup_loop(tracker: Tracker) -> None:
    """Периодически чистит устаревший кэш сообщений и файлы."""

    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        try:
            removed, paths = await tracker.storage.cleanup(tracker.config.retention_days)
            files = tracker.vault.remove_files(paths)
            if removed or files:
                logger.info("Очистка кэша: записей %s, файлов %s", removed, files)
        except Exception:  # noqa: BLE001 - фоновая задача не должна ронять бота
            logger.exception("Ошибка при очистке кэша")


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def run() -> None:
    config = Config.load()
    setup_logging(config.log_level)
    config.media_dir.mkdir(parents=True, exist_ok=True)

    storage = await Storage(config.db_path).connect()
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    tracker = Tracker(bot, storage, config)

    dispatcher = Dispatcher()
    dispatcher["tracker"] = tracker
    dispatcher["config"] = config
    dispatcher.include_router(build_router())

    cleaner: asyncio.Task[None] | None = None

    @dispatcher.startup()
    async def on_startup() -> None:
        nonlocal cleaner
        me = await bot.get_me()
        logger.info("Бот @%s запущен", me.username)
        await bot.set_my_commands(COMMANDS)
        cleaner = asyncio.create_task(cleanup_loop(tracker))

    @dispatcher.shutdown()
    async def on_shutdown() -> None:
        if cleaner is not None:
            cleaner.cancel()
        await tracker.close()
        await storage.close()
        logger.info("Бот остановлен")

    allowed_updates = dispatcher.resolve_used_update_types()
    logger.info("Слушаю апдейты: %s", ", ".join(sorted(allowed_updates)))
    try:
        await dispatcher.start_polling(bot, allowed_updates=allowed_updates)
    finally:
        await bot.session.close()


def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Выход по сигналу")


if __name__ == "__main__":
    main()
