from aiogram import Router

from . import errors, vault


def build_router() -> Router:
    root = Router(name="root")
    root.include_router(vault.router)
    root.include_router(errors.router)
    return root


__all__ = ["build_router"]
