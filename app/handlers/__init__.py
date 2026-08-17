"""Роутеры aiogram."""

from aiogram import Router

from . import business, commands


def build_router() -> Router:
    """Собирает дерево роутеров. Каждый вызов возвращает новые объекты."""

    root = Router(name="root")
    root.include_router(commands.create_router())
    root.include_router(business.create_router())
    return root


__all__ = ["build_router", "business", "commands"]
