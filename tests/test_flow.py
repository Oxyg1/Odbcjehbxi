"""Offline smoke test: drive the handlers with a stub Bot, no Telegram needed.

Run with:  python tests/test_flow.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("SECRET_CODE", "732")
os.environ.setdefault("STATE_BACKEND", "memory")

from aiogram.types import Chat, Message, PhotoSize, User  # noqa: E402

from cryptexbot.config import Settings  # noqa: E402
from cryptexbot.handlers import vault  # noqa: E402
from cryptexbot.keyboards import DialCD, vault_keyboard  # noqa: E402
from cryptexbot.services.artwork import ArtworkProvider, Frame  # noqa: E402
from cryptexbot.services.rewards import StaticRewardProvider  # noqa: E402
from cryptexbot.state import MemoryStateStore, VaultState  # noqa: E402

CHAT = Chat(id=4242, type="private")
USER = User(id=7, is_bot=False, first_name="Player")
PHOTO = [PhotoSize(file_id="fid", file_unique_id="u", width=800, height=800)]


def make_message(message_id: int = 100) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=CHAT,
        from_user=USER,
        photo=PHOTO,
    ).as_(None)


class StubBot:
    """Records API calls instead of making them."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def send_photo(self, **kwargs):
        self.calls.append(("send_photo", kwargs))
        return make_message()

    async def edit_message_reply_markup(self, **kwargs):
        self.calls.append(("edit_message_reply_markup", kwargs))
        return True

    async def edit_message_media(self, **kwargs):
        self.calls.append(("edit_message_media", kwargs))
        return make_message()

    async def edit_message_caption(self, **kwargs):
        self.calls.append(("edit_message_caption", kwargs))
        return make_message()

    def named(self, name: str) -> list[dict]:
        return [kwargs for call, kwargs in self.calls if call == name]


class StubQuery:
    """Minimal CallbackQuery stand-in: a message, a user, and an answer()."""

    def __init__(self, message: Message) -> None:
        self.message = message
        self.from_user = USER
        self.answers: list[dict] = []

    async def answer(self, text=None, show_alert=False, **kwargs):
        self.answers.append({"text": text, "alert": show_alert})
        return True


async def main() -> None:
    settings = Settings(BOT_TOKEN="test:token", SECRET_CODE="732", DIAL_COUNT=3)
    store = MemoryStateStore()
    artwork = ArtworkProvider()
    artwork.ensure_rendered()
    rewards = StaticRewardProvider("Promo code: CRYPTEX-732-OPEN")
    bot = StubBot()

    # --- artwork renders both frames -------------------------------------- #
    for frame in Frame:
        assert artwork._path(frame).exists(), f"missing artwork: {frame}"
    print("ok  artwork rendered for both frames")

    # --- /start spawns exactly one message --------------------------------- #
    await vault.spawn_vault(make_message(), bot, store, artwork, settings)
    assert len(bot.named("send_photo")) == 1
    state = await store.get((CHAT.id, 100))
    assert state is not None and state.dials == [0, 0, 0]
    print("ok  /vault sent one photo and stored [0, 0, 0]")

    # --- turning a dial edits markup only ---------------------------------- #
    query = StubQuery(make_message())
    await vault.turn_dial(
        query, DialCD(index=0), bot, store, artwork, rewards, settings
    )
    state = await store.get((CHAT.id, 100))
    assert state.dials == [1, 0, 0], state.dials
    assert len(bot.named("edit_message_reply_markup")) == 1
    assert not bot.named("edit_message_media"), "media must not reload on a dial turn"
    print("ok  dial turn edits markup only (no media reload)")

    # --- wrap-around 9 -> 0 ------------------------------------------------- #
    for _ in range(9):
        await vault.turn_dial(
            StubQuery(make_message()), DialCD(index=0), bot, store, artwork, rewards, settings
        )
    state = await store.get((CHAT.id, 100))
    assert state.dials == [0, 0, 0], state.dials
    print("ok  dial wraps 9 -> 0")

    # --- concurrent taps never lose a notch -------------------------------- #
    await asyncio.gather(
        *[
            vault.turn_dial(
                StubQuery(make_message()), DialCD(index=1), bot, store, artwork, rewards, settings
            )
            for _ in range(20)
        ]
    )
    state = await store.get((CHAT.id, 100))
    assert state.dials[1] == 0 and state.attempts == 30, (state.dials, state.attempts)
    print("ok  20 concurrent taps counted exactly 20 turns")

    # --- reach 7-3-2 and unlock -------------------------------------------- #
    for index, target in enumerate((7, 3, 2)):
        for _ in range(target):
            await vault.turn_dial(
                StubQuery(make_message()), DialCD(index=index), bot, store, artwork, rewards, settings
            )
    state = await store.get((CHAT.id, 100))
    assert state.opened, "vault should be open on 7-3-2"
    assert len(bot.named("edit_message_media")) == 1, "media swaps exactly once"
    captions = bot.named("edit_message_caption")
    assert captions, "reward must be written into the caption"
    assert "CRYPTEX-732-OPEN" in captions[-1]["caption"]
    assert len(captions[-1]["caption"]) <= vault.CAPTION_LIMIT
    print("ok  7-3-2 swapped media once and revealed the prize")

    # --- an opened vault ignores further taps ------------------------------ #
    before = len(bot.calls)
    closed = StubQuery(make_message())
    await vault.turn_dial(closed, DialCD(index=0), bot, store, artwork, rewards, settings)
    assert len(bot.calls) == before, "no API calls on an opened vault"
    assert closed.answers[-1]["text"] == "Already open."
    print("ok  taps on an open vault are answered, not re-rendered")

    # --- unknown vault (restart / expiry) ---------------------------------- #
    orphan = StubQuery(make_message(message_id=999))
    await vault.turn_dial(orphan, DialCD(index=0), bot, store, artwork, rewards, settings)
    assert orphan.answers[-1]["alert"] is True
    print("ok  unknown message_id gets an alert, not a crash")

    # --- keyboard reflects state ------------------------------------------- #
    kb = vault_keyboard(VaultState(dials=[7, 3, 2]))
    assert [b.text for b in kb.inline_keyboard[0]] == ["7️⃣", "3️⃣", "2️⃣"]
    print("ok  keyboard renders the current dials")

    print("\nall checks passed")


if __name__ == "__main__":
    asyncio.run(main())
