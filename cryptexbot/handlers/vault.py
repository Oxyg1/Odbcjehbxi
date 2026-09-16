"""The whole Zero-Spam interaction: one message, edited forever.

The lifecycle of that single message:

1. ``/vault`` sends the locked safe. If the player has no saved language it
   shows the picker and no dials; otherwise it goes straight to "sealing".
   Either way the quest starts generating **immediately, in the background**,
   so choosing a language costs no waiting. (:func:`spawn_vault`)
2. The quest lands and the same message is edited to show the riddle, the
   clues and the dials. (:func:`_apply_quest`)
3. Each tap edits the markup only. (:func:`turn_dial`)
4. The language button re-renders the same puzzle in the other language — no
   regeneration, because both were authored up front. (:func:`set_language`)
5. The correct combination swaps the media once, then streams the reveal into
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
from ..i18n import normalize, ordinal, t
from ..keyboards import (
    DialCD,
    LangCD,
    NoopCD,
    ResetCD,
    language_keyboard,
    opened_keyboard,
    vault_keyboard,
)
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

# Background quest generations. asyncio only holds a weak reference to a task,
# so without this set a generation can be garbage collected mid-flight.
_PENDING: set[asyncio.Task] = set()


# --------------------------------------------------------------------------- #
# Captions
# --------------------------------------------------------------------------- #

def picker_caption() -> str:
    """Bilingual by design: the player cannot read the wrong half."""
    return t(None, "choose_language")


def sealing_caption(lang: str | None) -> str:
    """Shown while Gemini forges the quest."""
    return f"{t(lang, 'sealing_title')}\n\n{t(lang, 'sealing_body')}"


def locked_caption(state: VaultState) -> str:
    """Theme, framing, one clue per dial, and the dial read-out.

    Clues are labelled with ordinal words rather than "1." — printing numerals
    beside a puzzle whose answer is numerals is asking to be misread.

    Assembly is budgeted, not hoped for: a caption over 1024 characters is
    rejected outright by Telegram, and with eight dials the full text would run
    past it. The framing line goes first, then clue text is trimmed evenly —
    the clues are the puzzle, so they are the last thing to give.
    """
    lang = state.lang
    head = f"🔒 <b>{html.escape(state.theme_in().upper())}</b>\n\n"
    tail = (
        f"\n\n<b>{t(lang, 'dials')}:</b> "
        f"<code>{' '.join(str(d) for d in state.dials)}</code>"
        f"\n<b>{t(lang, 'turns')}:</b> {state.attempts}"
    )
    riddle = state.riddle_in()
    framing = f"<i>{html.escape(riddle)}</i>\n\n" if riddle else ""
    clues = state.clues_in()

    def render(items: list[str]) -> list[str]:
        return [
            f"<b>{ordinal(lang, i)}</b> — {html.escape(clue)}"
            for i, clue in enumerate(items)
        ]

    lines = render(clues)
    caption = head + framing + "\n".join(lines) + tail
    if len(caption) <= CAPTION_LIMIT:
        return caption

    # Too long: drop the framing line first.
    caption = head + "\n".join(lines) + tail
    if len(caption) <= CAPTION_LIMIT:
        return caption

    # Still too long: trim every clue to an equal share of what is left.
    overhead = len(head) + len(tail) + sum(len(line) for line in render([""] * len(clues)))
    budget = max(40, (CAPTION_LIMIT - overhead - len(clues)) // max(1, len(clues)))
    trimmed = [c[: budget - 1] + "…" if len(c) > budget else c for c in clues]
    return (head + "\n".join(render(trimmed)) + tail)[:CAPTION_LIMIT]


def _unlock_header(state: VaultState) -> str:
    return (
        f"🔓 <b>{html.escape(state.theme_in().upper())}</b>\n\n"
        + t(
            state.lang,
            "accepted",
            code="-".join(str(d) for d in state.code),
            turns=state.attempts,
        )
        + "\n\n"
    )


def opening_caption(state: VaultState) -> str:
    return _unlock_header(state) + t(state.lang, "reaching_inside")


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
# 1. /vault and /lang — send the shell, generate in the background
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
    await _spawn(message, bot, store, artwork, quests, settings, force_picker=False)


@router.message(Command("lang"))
@router.message(Command("language"))
async def spawn_with_picker(
    message: Message,
    bot: Bot,
    store: StateStore,
    artwork: ArtworkProvider,
    quests: QuestProvider,
    settings: Settings,
) -> None:
    """A fresh vault that always asks which language to play in.

    Changing language is otherwise a button on the vault itself; this exists
    for players who want to switch before starting, or who saved a choice they
    now regret.
    """
    await _spawn(message, bot, store, artwork, quests, settings, force_picker=True)


async def _spawn(
    message: Message,
    bot: Bot,
    store: StateStore,
    artwork: ArtworkProvider,
    quests: QuestProvider,
    settings: Settings,
    force_picker: bool,
) -> None:
    user = message.from_user
    state = VaultState.new(settings.dial_count, owner_id=user.id)

    # A player who has chosen before is not asked again — the vault button and
    # /lang are there if they change their mind.
    if force_picker or not settings.ask_language:
        saved = None if force_picker else settings.default_lang
    else:
        saved = await store.get_user_lang(user.id)
    state.lang = normalize(saved) if saved else None

    caption = picker_caption() if state.lang is None else sealing_caption(state.lang)
    markup = language_keyboard() if state.lang is None else None

    # Send first, generate second. The API call takes a second or two, and an
    # immediate message beats a silent bot — it also keeps the Zero-Spam rule
    # intact, because this is still the only message this vault will ever have.
    sent = await safe_call(
        bot.send_photo,
        chat_id=message.chat.id,
        photo=artwork.input_for(Frame.LOCKED),
        caption=caption,
        reply_markup=markup,
    )
    if sent is None:
        return

    # First send returns a file_id; every later vault reuses it instead of
    # re-uploading the PNG.
    if sent.photo:
        artwork.remember(Frame.LOCKED, sent.photo[-1].file_id)

    key: VaultKey = (sent.chat.id, sent.message_id)
    await store.set(key, state)

    # Generation runs while the player reads the picker, so picking a language
    # usually costs nothing at all.
    ctx = QuestContext(
        user_id=user.id,
        user_name=user.full_name,
        chat_id=message.chat.id,
        dial_count=settings.dial_count,
    )
    task = asyncio.create_task(_apply_quest(bot, store, quests, ctx, key))
    _PENDING.add(task)
    task.add_done_callback(_PENDING.discard)


async def _apply_quest(
    bot: Bot,
    store: StateStore,
    quests: QuestProvider,
    ctx: QuestContext,
    key: VaultKey,
) -> None:
    """Generate the quest, store it, and reveal it if the player is ready."""
    quest = await quests.generate(ctx)

    async with store.lock(key):
        state = await store.get(key)
        if state is None or state.opened:
            return  # the vault went away while we were generating
        state.apply(quest)
        await store.set(key, state)

    await _render_puzzle(bot, key, state)


async def _render_puzzle(bot: Bot, key: VaultKey, state: VaultState) -> None:
    """Show the riddle and the dials — the one edit that turns shell into game.

    A no-op until both halves are in place: the quest has landed *and* the
    player has picked a language. Whichever arrives second triggers the render,
    so the two can race freely.
    """
    if not state.ready or state.lang is None or state.opened:
        return
    await safe_call(
        bot.edit_message_caption,
        chat_id=key[0],
        message_id=key[1],
        caption=locked_caption(state),
        reply_markup=vault_keyboard(state),
    )


# --------------------------------------------------------------------------- #
# 2. Language
# --------------------------------------------------------------------------- #

@router.callback_query(LangCD.filter())
async def set_language(
    query: CallbackQuery,
    callback_data: LangCD,
    bot: Bot,
    store: StateStore,
) -> None:
    """Pick a language, or switch to the other one mid-game.

    No regeneration: both languages were authored in the same call, so this is
    a caption edit over the same combination. The dials keep their positions
    and the turn count is untouched — switching language is not a restart.
    """
    key = key_of(query)
    if key is None:
        await ack(query)
        return

    lang = normalize(callback_data.code)

    async with store.lock(key):
        state = await store.get(key)
        if state is None:
            await ack(query, t(lang, "rusted_shut"), alert=True)
            return
        if state.opened:
            await ack(query, t(state.lang, "already_open"))
            return
        first_choice = state.lang is None
        state.lang = lang
        await store.set(key, state)

    await store.set_user_lang(query.from_user.id, lang)

    if state.ready:
        await _render_puzzle(bot, key, state)
    else:
        # Still generating: acknowledge the choice in the new language so the
        # player sees something happen immediately.
        await safe_call(
            bot.edit_message_caption,
            chat_id=key[0],
            message_id=key[1],
            caption=sealing_caption(lang),
            reply_markup=None,
        )

    await ack(query, t(lang, "lang_prompt_done" if first_choice else "lang_switched"))


# --------------------------------------------------------------------------- #
# 3. Dial turns
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
            await ack(query, t(None, "rusted_shut"), alert=True)
            return
        if not state.ready:
            await ack(query, t(state.lang, "still_sealing"))
            return
        if state.opened:
            await ack(query, t(state.lang, "already_open"))
            return
        if not 0 <= callback_data.index < len(state.dials):
            await ack(query)
            return

        state.turn(callback_data.index)
        unlocked = state.matches()  # against this vault's own generated code
        state.opened = unlocked
        await store.set(key, state)

    if unlocked:
        await ack(query, t(state.lang, "click"))
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
    await ack(query, t(state.lang, "reset_done"))


@router.callback_query(NoopCD.filter())
async def noop(query: CallbackQuery) -> None:
    await ack(query)


# --------------------------------------------------------------------------- #
# 4. The unlock event
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
        reply_markup=opened_keyboard(state.lang),
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
            reply_markup=opened_keyboard(state.lang),
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
        theme=state.theme_in(),
        riddle=state.riddle_in(),
        lang=normalize(state.lang),
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
            reply_markup=opened_keyboard(state.lang),
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
        latest = t(state.lang, "empty_vault")

    await push(latest, streaming=False)  # always flush the final text
    return latest
