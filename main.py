"""Entrypoint: `python main.py`."""

from __future__ import annotations

import asyncio
import logging

from cryptexbot.bot import run


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


if __name__ == "__main__":
    configure_logging()
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        logging.info("CryptexBot stopped")
