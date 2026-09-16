"""The whole Zero-Spam interaction: one message, edited forever.

The lifecycle of that single message:

1. ``/vault`` sends the locked safe with a "sealing" caption and **no
   keyboard** — the vault has no combination yet, so there is nothing to tap.
2. Gemini returns a quest; the same message is edited to show the riddle and
   the dials appear. (:func:`spawn_vault`)
3. Each tap edits the markup only. (:func:`turn_dial`)
4. The correct combination swaps the media once, then streams the reveal into
   the caption. (:func:`_unlock`)
"""

from __future__ import annotations

import asyncio
import html
import logging
import time

from aiogram import Bot, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from ..config import Settings
from ..keyboards import DialCD, NoopCD, ResetCD, opened_keyboard, vault_keyboard
from ..services.artwork import ArtworkProvider, Frame
from ..services.quests import QuestContext, QuestProvider
from ..services.rewards import RewardContext, RewardProvider
from ..services.safe_calls import ack, safe_call
from ..state import StateStore, VaultKey, VaultState

log = logging.getLogger(__name__)

router = Router(name="vault")

CAPTION_LIMIT = 1024
# Telegram tolerates roughly one edit per second per chat. Streaming faster
# than this earns 429s and buys no extra smoothness.
STREAM_EDIT_INTERVAL = 1.2
# Trailing block while the reveal is still arriving — the typewriter's cursor.
CURSOR = "▌"


# --------------------------------------------------------------------------- #
# Captions
# --------------------------------------------------------------------------- #

def sealing_caption() -> str:
    """Shown for the second or two while Gemini forges the quest."""
    return (
        "🔒 <b>THE CRYPTEX VAULT</b>\n\n"
        "<i>Steel is cooling, tumblers are being set…</i>\n\n"
        "A new vault is being sealed for you. Its combination does not exist "
        "yet — not even the bot knows it."
    )


def locked_caption(state: VaultState) -> str:
    dials = " ".join(str(d) for d in state.dials)
    return (
        f"🔒 <b>{html.escape(state.theme.upper())}</b>\n\n"
        f"<i>{html.escape(state.riddle)}</i>\n\n"
        "Tap a dial to turn it one notch. Line up the right combination "
        "and the vault opens.\n\n"
        f"<b>Dials:</b> <code>{dials}</code>\n"
        f"<b>Turns:</b> {state.attempts}"
    )


def _unlock_header(state: VaultState) -> str:
    return (
        f"🔓 <b>{html.escape(state.theme.upper())}</b>\n\n"
        f"Combination <code>{'-'.join(str(d) for d in state.code)}</code> "
        f"accepted after {state.attempts} turns.\n\n"
    )


def opening_caption(state: VaultState) -> str:
    return _unlock_header(state) + "<i>Reaching inside…</i>"


def opened_caption(state: VaultState, reward: str, streaming: bool = False) -> str:
    """Header plus the reveal so far; truncated to fit Telegram's caption cap.

    Truncating from the *front* of the body would drop the header, so the body
    is what gives — a mid-stream cut is invisible once the next chunk lands.
    """
    head = _unlock_header(state)
    body = html.escape(reward.strip()) + (CURSOR if streaming else "")
    budget = CAPTION_LIMIT - len(head)
    if len(body) > budget:
        body = body[: budget - 1] + "…"
    return head + body


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
# 1. /vault — send the shell, then fill it with a generated quest
# --------------------------------------------------------------------------- #

@router.message(CommandStart())
@router.message(Command("vault"))
async def spawn_vault(
    message: Message,
    bot: Bot,
    store: StateStore,
    artwork: ArtworkProvider,
    quests: QuestProvider,
    settings: Settings,
) -> None:
    state = VaultState.new(settings.dial_count, owner_id=message.from_user.id)

    # Send first, generate second. The API call takes a second or two, and an
    # immediate message beats a silent bot — it also keeps the Zero-Spam rule
    # intact, because this is still the only message this vault will ever have.
    sent = await safe_call(
        bot.send_photo,
        chat_id=message.chat.id,
        photo=artwork.input_for(Frame.LOCKED),
        caption=sealing_caption(),
        reply_markup=None,  # no dials until there is a combination behind them
    )
    if sent is None:
        return

    # First send returns a file_id; every later vault reuses it instead of
    # re-uploading the PNG.
    if sent.photo:
        artwork.remember(Frame.LOCKED, sent.photo[-1].file_id)

    key: VaultKey = (sent.chat.id, sent.message_id)
    await store.set(key, state)

    quest = await quests.generate(
        QuestContext(
            user_id=message.from_user.id,
            user_name=message.from_user.full_name,
            chat_id=message.chat.id,
            dial_count=settings.dial_count,
        )
    )

    async with store.lock(key):
        state = await store.get(key) or state
        state.code = quest.code
        state.theme = quest.theme
        state.riddle = quest.riddle
        state.ready = True
        await store.set(key, state)

    # The reveal of the puzzle itself: same message, now with dials.
    await safe_call(
        bot.edit_message_caption,
        chat_id=key[0],
        message_id=key[1],
        caption=locked_caption(state),
        reply_markup=vault_keyboard(state),
    )


# --------------------------------------------------------------------------- #
# 2. Dial turns
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
        if not state.ready:
            await ack(query, "The vault is still being sealed. One moment.")
            return
        if state.opened:
            await ack(query, "Already open.")
            return
        if not 0 <= callback_data.index < len(state.dials):
            await ack(query)
            return

        state.turn(callback_data.index)
        unlocked = state.matches()  # against this vault's own generated code
        state.opened = unlocked
        await store.set(key, state)

    if unlocked:
        await ack(query, "🔓 Click.")
        await _unlock(query, bot, store, artwork, rewards, key, state)
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
        if state is None or state.opened or not state.ready:
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
# 3. The unlock event
# --------------------------------------------------------------------------- #

async def _unlock(
    query: CallbackQuery,
    bot: Bot,
    store: StateStore,
    artwork: ArtworkProvider,
    rewards: RewardProvider,
    key: VaultKey,
    state: VaultState,
) -> None:
    """Swap the media to the open safe, then type the reveal into its caption."""
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
        code=state.code_str,
        attempts=state.attempts,
        theme=state.theme,
        riddle=state.riddle,
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
    """Type the reward into the caption as Gemini produces it.

    This is the buffering layer, and it belongs here rather than in the
    provider: only the renderer knows Telegram's limits. Chunks accumulate
    freely, but a caption edit goes out at most once every
    ``STREAM_EDIT_INTERVAL`` seconds, so a fast stream costs a handful of edits
    instead of dozens of 429s. The final text is always flushed, throttle or
    not.
    """
    chat_id, message_id = key
    latest = ""
    rendered = ""
    last_edit = 0.0

    async def push(text: str, streaming: bool) -> None:
        nonlocal rendered, last_edit
        caption = opened_caption(state, text, streaming=streaming)
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
                await push(latest, streaming=True)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - a broken reveal must not break the vault
        log.exception("reward stream failed")

    if not latest:
        latest = "The vault is empty. Whatever was here, someone got to it first."

    await push(latest, streaming=False)  # always flush the final text
    return latest
