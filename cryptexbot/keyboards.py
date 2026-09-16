"""The vault's inline keyboard — the combination lock itself."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .state import VaultState

# Digits rendered as dial faces. Plain digits also work; these read as a
# mechanical dial and keep the button width stable.
DIAL_FACES = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]


class DialCD(CallbackData, prefix="dial"):
    """Turn dial ``index`` one notch."""

    index: int


class ResetCD(CallbackData, prefix="reset"):
    """Spin every dial back to zero."""


class NoopCD(CallbackData, prefix="noop"):
    """Decorative button; answered silently."""


def vault_keyboard(state: VaultState) -> InlineKeyboardMarkup:
    """Row of dials + a reset button, rendered from the current state."""
    builder = InlineKeyboardBuilder()

    dial_row = [
        InlineKeyboardButton(
            text=DIAL_FACES[value], callback_data=DialCD(index=i).pack()
        )
        for i, value in enumerate(state.dials)
    ]
    builder.row(*dial_row)
    builder.row(
        InlineKeyboardButton(text="🔄 Reset dials", callback_data=ResetCD().pack())
    )
    return builder.as_markup()


def opened_keyboard() -> InlineKeyboardMarkup:
    """Shown once the vault is open — no dials left to turn."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔓 VAULT OPEN", callback_data=NoopCD().pack())]
        ]
    )
