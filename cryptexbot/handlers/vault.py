"""The whole Zero-Spam interaction: one message, edited forever."""

from __future__ import annotations

import asyncio
import html
import logging
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from ..config import Settings
from ..keyboards import DialCD, NoopCD, ResetCD, opened_keyboard, vault_keyboard
from ..services.artwork import ArtworkProvider, Frame
from ..services.rewards import RewardContext, RewardProvider
from ..services.safe_calls import ack, safe_call
from ..state import StateStore, VaultKey, VaultState

log = logging.getLogger(__name__)

router = Router(name="vault")

CAPTION_LIMIT = 1024
# Telegram tolerates roughly one edit per second per chat. Streaming faster than
# this buys nothing but 429s.
STREAM_EDIT_INTERVAL = 1.2


# --------------------------------------------------------------------------- #
# Captions
# --------------------------------------------------------------------------- #

def locked_caption(state: VaultState) -> str:
    dials = " ".join(str(d) for d in state.dials)
    return (
        "🔒 <b>THE CRYPTEX VAULT</b>\n\n"
        "A steel door, three dials, and no key in sight.\n"
        "Tap a dial to turn it one notch. Line up the right combination "
        "and the vault opens.\n\n"
        f"<b>Dials:</b> <code>{dials}</code>\n"
        f"<b>Turns:</b> {state.attempts}"
    )


def opening_caption(state: VaultState) -> str:
    return (
        "🔓 <b>THE VAULT IS OPEN</b>\n\n"
        f"Combination <code>{'-'.join(str(d) for d in state.dials)}</code> "
        f"accepted after {state.attempts} turns.\n\n"
        "<i>Reaching inside…</i>"
    )


def opened_caption(state: VaultState, reward: str) -> str:
    head = (
        "🔓 <b>THE VAULT IS OPEN</b>\n\n"
        f"Combination <code>{'-'.join(str(d) for d in state.dials)}</code> "
        f"accepted after {state.attempts} turns.\n\n"
    )
    body = html.escape(reward.strip())
    caption = head + body
    if len(caption) > CAPTION_LIMIT:
        caption = caption[: CAPTION_LIMIT - 1] + "…"
    return caption


def key_of(event: Message | CallbackQuery) -> VaultKey | None:
    """Identity of a vault: the message it lives in.

    Returns ``None`` when Telegram gives us no message to edit (a callback on
    an inline-mode message, or one the bot can no longer access).
    """
    msg = event if isinstance(event, Message) else event.message
    if msg is None:
        return None
    return (msg.chat.id, msg.message_id)


# --------------------------------------------------------------------------- #
# /start — the one and only message this bot ever sends
# --------------------------------------------------------------------------- #

@router.message(CommandStart())
@router.message(Command("vault"))
async def spawn_vault(
    message: Message,
    bot: Bot,
    store: StateStore,
    artwork: ArtworkProvider,
    settings: Settings,
) -> None:
    state = VaultState.new(settings.dial_count, owner_id=message.from_user.id)

    sent = await safe_call(
        bot.send_photo,
        chat_id=message.chat.id,
        photo=artwork.input_for(Frame.LOCKED),
        caption=locked_caption(state),
        reply_markup=vault_keyboard(state),
    )
    if sent is None:
        return

    # First send returns a file_id; every later vault reuses it instead of
    # re-uploading the PNG.
    if sent.photo:
        artwork.remember(Frame.LOCKED, sent.photo[-1].file_id)

    await store.set((sent.chat.id, sent.message_id), state)


# --------------------------------------------------------------------------- #
# Dial turns
# --------------------------------------------------------------------------- #

@router.callback_query(DialCD.filter())
async def turn_dial(
    query: CallbackQuery,
    callback_data: DialCD,
    bot: Bot,
    store: StateStore,
    artwork: ArtworkProvider,
    rewards: RewardProvider,
    settings: Settings,
) -> None:
    key = key_of(query)
    if key is None:
        await ack(query)
        return

    # One vault, one turn at a time: rapid taps would otherwise interleave
    # read-modify-write and lose notches. The critical section is kept to the
    # state mutation only — the unlock sequence below can stream for seconds
    # and must not hold the mutex while it does.
    async with store.lock(key):
        state = await store.get(key)
        if state is None:
            await ack(
                query,
                "This vault has rusted shut. Send /vault for a new one.",
                alert=True,
            )
            return
        if state.opened:
            await ack(query, "Already open.")
            return
        if not 0 <= callback_data.index < len(state.dials):
            await ack(query)
            return

        state.turn(callback_data.index)
        unlocked = state.matches(settings.secret_dials)
        state.opened = unlocked
        await store.set(key, state)

    if unlocked:
        await ack(query, "🔓 Click.")
        await _unlock(query, bot, store, artwork, rewards, settings, key, state)
        return

    # Markup-only edit: the dial face flips in place, no media reload, no flash.
    await safe_call(
        bot.edit_message_reply_markup,
        chat_id=key[0],
        message_id=key[1],
        reply_markup=vault_keyboard(state),
    )
    await ack(query)


@router.callback_query(ResetCD.filter())
async def reset_dials(
    query: CallbackQuery, bot: Bot, store: StateStore, settings: Settings
) -> None:
    key = key_of(query)
    if key is None:
        await ack(query)
        return
    async with store.lock(key):
        state = await store.get(key)
        if state is None or state.opened:
            await ack(query)
            return
        state.dials = [0] * settings.dial_count
        await store.set(key, state)

    await safe_call(
        bot.edit_message_reply_markup,
        chat_id=key[0],
        message_id=key[1],
        reply_markup=vault_keyboard(state),
    )
    await ack(query, "Dials spun back to zero.")


@router.callback_query(NoopCD.filter())
async def noop(query: CallbackQuery) -> None:
    await ack(query)


# --------------------------------------------------------------------------- #
# The unlock event
# --------------------------------------------------------------------------- #

async def _unlock(
    query: CallbackQuery,
    bot: Bot,
    store: StateStore,
    artwork: ArtworkProvider,
    rewards: RewardProvider,
    settings: Settings,
    key: VaultKey,
    state: VaultState,
) -> None:
    """Swap the media to the open safe, then reveal the prize in its caption."""
    chat_id, message_id = key

    swapped = await safe_call(
        bot.edit_message_media,
        chat_id=chat_id,
        message_id=message_id,
        media=InputMediaPhoto(
            media=artwork.input_for(Frame.OPEN),
            caption=opening_caption(state),
            parse_mode="HTML",
        ),
        reply_markup=opened_keyboard(),
    )
    if swapped is None:
        # A stale cached file_id is the usual suspect; drop it and retry once
        # with a real upload.
        artwork.forget(Frame.OPEN)
        swapped = await safe_call(
            bot.edit_message_media,
            chat_id=chat_id,
            message_id=message_id,
            media=InputMediaPhoto(
                media=artwork.input_for(Frame.OPEN),
                caption=opening_caption(state),
                parse_mode="HTML",
            ),
            reply_markup=opened_keyboard(),
        )
    if swapped is not None and getattr(swapped, "photo", None):
        artwork.remember(Frame.OPEN, swapped.photo[-1].file_id)

    ctx = RewardContext(
        user_id=query.from_user.id,
        user_name=query.from_user.full_name,
        chat_id=chat_id,
        message_id=message_id,
        code=settings.secret_code,
        attempts=state.attempts,
    )

    final = await _stream_reward(bot, rewards, ctx, key, state)

    state.reward = final
    await store.set(key, state)


async def _stream_reward(
    bot: Bot,
    rewards: RewardProvider,
    ctx: RewardContext,
    key: VaultKey,
    state: VaultState,
) -> str:
    """Push the reward into the caption as it is produced.

    The static provider yields once, so this is a single edit. An LLM provider
    yields continuously and the same loop becomes native text streaming — the
    throttle below is the only thing standing between you and flood control.
    """
    chat_id, message_id = key
    latest = ""
    rendered = ""
    last_edit = 0.0

    async def push(text: str) -> None:
        nonlocal rendered, last_edit
        caption = opened_caption(state, text)
        if caption == rendered:
            return
        rendered = caption
        last_edit = time.monotonic()
        await safe_call(
            bot.edit_message_caption,
            chat_id=chat_id,
            message_id=message_id,
            caption=caption,
            parse_mode="HTML",
            reply_markup=opened_keyboard(),
        )

    try:
        async for partial in rewards.stream(ctx):
            latest = partial
            if time.monotonic() - last_edit >= STREAM_EDIT_INTERVAL:
                await push(latest)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - a broken reveal must not break the vault
        log.exception("reward stream failed")

    if not latest:
        latest = "The vault is empty. Whatever was here, someone got to it first."

    await push(latest)  # always flush the final text
    return latest
