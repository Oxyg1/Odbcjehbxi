"""The vault's inline keyboards — the combination lock and the language picker."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .i18n import LANG_NAMES, LANGS, other_lang, t
from .state import VaultState

# Digits rendered as dial faces. Plain digits also work; these read as a
# mechanical dial and keep the button width stable.
DIAL_FACES = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]


class DialCD(CallbackData, prefix="dial"):
    """Turn dial ``index`` one notch."""

    index: int


class ResetCD(CallbackData, prefix="reset"):
    """Spin every dial back to zero."""


class LangCD(CallbackData, prefix="lang"):
    """Set this vault's language to ``code``."""

    code: str


class NoopCD(CallbackData, prefix="noop"):
    """Decorative button; answered silently."""


def language_keyboard() -> InlineKeyboardMarkup:
    """The picker shown before a vault has a language."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=LANG_NAMES[lang], callback_data=LangCD(code=lang).pack()
                )
                for lang in LANGS
            ]
        ]
    )


def vault_keyboard(state: VaultState) -> InlineKeyboardMarkup:
    """Dials, reset, and a one-tap switch to the other language.

    The language button is labelled with the language it switches *to*, so it
    reads as an action rather than a status.
    """
    builder = InlineKeyboardBuilder()

    builder.row(
        *[
            InlineKeyboardButton(
                text=DIAL_FACES[value], callback_data=DialCD(index=i).pack()
            )
            for i, value in enumerate(state.dials)
        ]
    )
    builder.row(
        InlineKeyboardButton(
            text=t(state.lang, "reset_button"), callback_data=ResetCD().pack()
        ),
        InlineKeyboardButton(
            text=t(state.lang, "lang_button"),
            callback_data=LangCD(code=other_lang(state.lang)).pack(),
        ),
    )
    return builder.as_markup()


def opened_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    """Shown once the vault is open — no dials left to turn.

    No language button here on purpose: the reveal is generated once, in the
    language the player was reading at the moment it opened, and a toggle that
    switched the heading but not the prize would look broken.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "open_button"), callback_data=NoopCD().pack()
                )
            ]
        ]
    )
