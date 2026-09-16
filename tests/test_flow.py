"""Offline smoke test: drive the handlers with a stub Bot, no Telegram needed.

Run with:  python tests/test_flow.py
"""

from __future__ import annotations

import asyncio
import html
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("STATE_BACKEND", "memory")

from aiogram.types import Chat, Message, PhotoSize, User  # noqa: E402

from cryptexbot.config import Settings  # noqa: E402
from cryptexbot.handlers import vault  # noqa: E402
from cryptexbot.keyboards import DialCD, LangCD, vault_keyboard  # noqa: E402
from cryptexbot.services.artwork import ArtworkProvider, Frame  # noqa: E402
from cryptexbot.services.quests import (  # noqa: E402
    Quest,
    QuestContext,
    QuestProvider,
    StaticQuestProvider,
)
from cryptexbot.services.rewards import (  # noqa: E402
    RewardContext,
    RewardProvider,
    StaticRewardProvider,
)
from cryptexbot.state import MemoryStateStore, VaultState  # noqa: E402

CHAT = Chat(id=4242, type="private")
USER = User(id=7, is_bot=False, first_name="Player")
PHOTO = [PhotoSize(file_id="fid", file_unique_id="u", width=800, height=800)]

QUEST = Quest(
    code=[7, 3, 2],
    theme={"en": "a drowned observatory", "ru": "затонувшая обсерватория"},
    riddle={"en": "Salt keeps time.", "ru": "Соль считает часы."},
    clues={
        "en": [
            "Count the days the almanac gives a week.",
            "Count the legs of the milking stool.",
            "Count the oars a rower pulls.",
        ],
        "ru": [
            "Сосчитайте дни, которые альманах отводит неделе.",
            "Сосчитайте ножки доильного табурета.",
            "Сосчитайте вёсла в руках гребца.",
        ],
    },
)


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


class ScriptedQuestProvider(QuestProvider):
    """Stands in for Gemini: a fixed bilingual quest, no network."""

    def __init__(self, quest: Quest, delay: float = 0.0) -> None:
        self.quest = quest
        self.delay = delay
        self.calls = 0

    async def generate(self, ctx: QuestContext) -> Quest:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        import copy

        return copy.deepcopy(self.quest)


class ChunkedRewardProvider(RewardProvider):
    """Stands in for Gemini streaming: yields cumulative text, chunk by chunk."""

    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks

    async def stream(self, ctx: RewardContext):
        buffer = ""
        for chunk in self.chunks:
            buffer += chunk
            yield buffer


async def drain() -> None:
    """Wait for the background quest generations spawned by /vault."""
    while vault._PENDING:
        await asyncio.gather(*list(vault._PENDING))


async def main() -> None:
    settings = Settings(BOT_TOKEN="test:token", DIAL_COUNT=3)
    store = MemoryStateStore()
    artwork = ArtworkProvider()
    artwork.ensure_rendered()
    quests = ScriptedQuestProvider(QUEST)
    rewards = StaticRewardProvider("Promo code: CRYPTEX-732-OPEN")
    bot = StubBot()
    key = (CHAT.id, 100)

    # --- artwork renders both frames -------------------------------------- #
    for frame in Frame:
        assert artwork._path(frame).exists(), f"missing artwork: {frame}"
    print("ok  artwork rendered for both frames")

    # --- /vault opens with the language picker and no dials ---------------- #
    await vault.spawn_vault(make_message(), bot, store, artwork, quests, settings)
    assert len(bot.named("send_photo")) == 1, "Zero-Spam: exactly one message"
    sent = bot.named("send_photo")[0]
    assert "Choose your language" in sent["caption"]
    assert "Выберите язык" in sent["caption"], "the picker must read in both languages"
    buttons = [b.text for row in sent["reply_markup"].inline_keyboard for b in row]
    assert any("English" in b for b in buttons) and any("Русский" in b for b in buttons)
    print("ok  /vault shows a bilingual language picker, no dials yet")

    # --- generation runs in the background while the player chooses -------- #
    await drain()
    assert quests.calls == 1, "the quest generates without waiting for the choice"
    state = await store.get(key)
    assert state.ready and state.code == [7, 3, 2]
    assert state.lang is None
    assert not bot.named("edit_message_caption"), "nothing rendered before a language"
    print("ok  the quest generates in the background, held back until a language")

    # --- picking Russian renders the puzzle in Russian --------------------- #
    query = StubQuery(make_message())
    await vault.set_language(query, LangCD(code="ru"), bot, store)
    edit = bot.named("edit_message_caption")[-1]
    assert "ЗАТОНУВШАЯ ОБСЕРВАТОРИЯ" in edit["caption"]
    assert "альманах отводит неделе" in edit["caption"], "Russian clues"
    assert "Первый" in edit["caption"] and "Диски" in edit["caption"]
    assert edit["reply_markup"] is not None, "dials appear with the puzzle"
    assert len(edit["caption"]) <= vault.CAPTION_LIMIT
    labels = [b.text for row in edit["reply_markup"].inline_keyboard for b in row]
    assert "🔄 Сбросить диски" in labels and "🌐 English" in labels
    print("ok  choosing Russian renders riddle, clues and buttons in Russian")

    # --- the choice is remembered for next time ---------------------------- #
    assert await store.get_user_lang(USER.id) == "ru"
    bot2 = StubBot()
    await vault.spawn_vault(make_message(), bot2, store, artwork, quests, settings)
    assert "Сталь остывает" in bot2.named("send_photo")[0]["caption"]
    assert bot2.named("send_photo")[0]["reply_markup"] is None, "no picker second time"
    await drain()
    print("ok  a saved language skips the picker on the next vault")

    # --- turning a dial edits markup only ---------------------------------- #
    before = len(bot.named("edit_message_caption"))
    await vault.turn_dial(
        StubQuery(make_message()), DialCD(index=0), bot, store, artwork, rewards, settings
    )
    state = await store.get(key)
    assert state.dials == [1, 0, 0], state.dials
    assert len(bot.named("edit_message_reply_markup")) == 1
    assert not bot.named("edit_message_media"), "media must not reload on a dial turn"
    assert len(bot.named("edit_message_caption")) == before, "no caption edit on a turn"
    print("ok  dial turn edits markup only (no media reload)")

    # --- switching language mid-game keeps the dials and the code ---------- #
    switch = StubQuery(make_message())
    await vault.set_language(switch, LangCD(code="en"), bot, store)
    state = await store.get(key)
    assert state.dials == [1, 0, 0], "a language switch is not a restart"
    assert state.code == [7, 3, 2], "the combination never moves"
    assert state.attempts == 1, "the turn count survives"
    edit = bot.named("edit_message_caption")[-1]
    assert "A DROWNED OBSERVATORY" in edit["caption"]
    assert "almanac gives a week" in edit["caption"]
    assert "Dials" in edit["caption"] and "First" in edit["caption"]
    assert quests.calls == 2, "switching language must not regenerate the quest"
    print("ok  switching language re-renders the same vault, dials and code intact")

    # --- wrap-around 9 -> 0 ------------------------------------------------- #
    for _ in range(9):
        await vault.turn_dial(
            StubQuery(make_message()), DialCD(index=0), bot, store, artwork, rewards, settings
        )
    state = await store.get(key)
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
    state = await store.get(key)
    assert state.dials[1] == 0 and state.attempts == 30, (state.dials, state.attempts)
    print("ok  20 concurrent taps counted exactly 20 turns")

    # --- reach 7-3-2 and unlock -------------------------------------------- #
    for index, target in enumerate((7, 3, 2)):
        for _ in range(target):
            await vault.turn_dial(
                StubQuery(make_message()), DialCD(index=index), bot, store, artwork, rewards, settings
            )
    state = await store.get(key)
    assert state.opened, "vault should be open on 7-3-2"
    assert len(bot.named("edit_message_media")) == 1, "media swaps exactly once"
    captions = bot.named("edit_message_caption")
    assert "CRYPTEX-732-OPEN" in captions[-1]["caption"]
    assert vault.CURSOR not in captions[-1]["caption"], "cursor must not survive"
    print("ok  7-3-2 swapped media once and revealed the prize")

    # --- an opened vault ignores further taps ------------------------------ #
    before = len(bot.calls)
    closed = StubQuery(make_message())
    await vault.turn_dial(closed, DialCD(index=0), bot, store, artwork, rewards, settings)
    assert len(bot.calls) == before, "no API calls on an opened vault"
    lang_after = StubQuery(make_message())
    await vault.set_language(lang_after, LangCD(code="ru"), bot, store)
    assert len(bot.calls) == before, "language cannot change once the prize is written"
    print("ok  taps and language switches on an open vault are answered, not re-rendered")

    # --- unknown vault (restart / expiry) ---------------------------------- #
    orphan = StubQuery(make_message(message_id=999))
    await vault.turn_dial(orphan, DialCD(index=0), bot, store, artwork, rewards, settings)
    assert orphan.answers[-1]["alert"] is True
    print("ok  unknown message_id gets an alert, not a crash")

    # --- choosing a language before generation finishes -------------------- #
    slow_bot = StubBot()
    slow_store = MemoryStateStore()
    slow = ScriptedQuestProvider(QUEST, delay=0.15)
    slow_settings = Settings(BOT_TOKEN="test:token", DIAL_COUNT=3)
    await vault.spawn_vault(make_message(), slow_bot, slow_store, artwork, slow, slow_settings)
    early = StubQuery(make_message())
    await vault.set_language(early, LangCD(code="ru"), slow_bot, slow_store)
    assert "Сталь остывает" in slow_bot.named("edit_message_caption")[-1]["caption"]
    assert slow_bot.named("edit_message_caption")[-1]["reply_markup"] is None
    await drain()
    final = slow_bot.named("edit_message_caption")[-1]
    assert "ЗАТОНУВШАЯ ОБСЕРВАТОРИЯ" in final["caption"], "the quest renders when it lands"
    assert final["reply_markup"] is not None
    print("ok  picking a language early shows 'sealing', then the puzzle when ready")

    # --- keyboard reflects state ------------------------------------------- #
    kb = vault_keyboard(VaultState(dials=[7, 3, 2], lang="ru"))
    assert [b.text for b in kb.inline_keyboard[0]] == ["7️⃣", "3️⃣", "2️⃣"]
    print("ok  keyboard renders the current dials")

    # --- local quest provider stays random --------------------------------- #
    local = StaticQuestProvider()
    qctx = QuestContext(user_id=1, user_name="P", chat_id=1, dial_count=3)
    codes = {tuple((await local.generate(qctx)).code) for _ in range(40)}
    assert len(codes) > 1, "offline codes must vary between vaults"
    print("ok  offline provider still generates a fresh code per vault")

    # --- streaming is buffered, not one edit per chunk ---------------------- #
    stream_bot = StubBot()
    stream_state = VaultState(
        dials=[7, 3, 2], code=[7, 3, 2], theme={"en": "a cold archive"},
        lang="en", ready=True, attempts=12,
    )
    chunky = ChunkedRewardProvider(["You step in. " for _ in range(60)])
    text = await vault._stream_reward(
        stream_bot,
        chunky,
        RewardContext(
            user_id=1, user_name="P", chat_id=CHAT.id, message_id=100,
            code="732", attempts=12, theme="a cold archive", lang="en",
        ),
        key,
        stream_state,
    )
    edits = stream_bot.named("edit_message_caption")
    assert len(edits) <= 3, f"60 chunks should buffer into a few edits, got {len(edits)}"
    assert text.strip() in html.unescape(edits[-1]["caption"])
    assert vault.CURSOR not in edits[-1]["caption"]
    assert all(len(e["caption"]) <= vault.CAPTION_LIMIT for e in edits)
    print(f"ok  60 stream chunks buffered into {len(edits)} caption edit(s)")

    # --- the offline prize speaks the player's language --------------------- #
    for lang, expect in (("ru", "Дверь поддаётся"), ("en", "The door gives")):
        out = [
            partial
            async for partial in StaticRewardProvider().stream(
                RewardContext(
                    user_id=1, user_name="P", chat_id=1, message_id=1,
                    code="732", attempts=1, theme="хранилище", lang=lang,
                )
            )
        ]
        assert expect in out[-1], (lang, out)
    print("ok  the offline fallback prize is localised too")

    # --- a failing stream still pays out ------------------------------------ #
    class Exploding(RewardProvider):
        async def stream(self, ctx):
            raise RuntimeError("Gemini is down")
            yield ""  # pragma: no cover

    from cryptexbot.services.rewards import FallbackRewardProvider

    guarded = FallbackRewardProvider(Exploding(), StaticRewardProvider("Backup prize"))
    out = await vault._stream_reward(
        StubBot(), guarded,
        RewardContext(user_id=1, user_name="P", chat_id=CHAT.id, message_id=100,
                      code="732", attempts=3, theme="t", lang="en"),
        key, stream_state,
    )
    assert out == "Backup prize", out
    print("ok  a dead Gemini still pays the player")

    print("\nall checks passed")


if __name__ == "__main__":
    asyncio.run(main())
