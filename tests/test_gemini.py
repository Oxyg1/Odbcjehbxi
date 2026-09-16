"""Gemini provider tests with a fake SDK client — no API key, no network.

Covers the parts that break in production: response parsing, schema shape,
malformed JSON, timeouts, and the streaming adapter's two calling
conventions across google-genai versions.

Run with:  python tests/test_gemini.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptexbot.services.gemini import (  # noqa: E402
    GeminiQuestProvider,
    GeminiRewardProvider,
    _aiter,
    _parse_json,
    _quest_schema,
    _solver_schema,
)
from cryptexbot.services.quests import (  # noqa: E402
    DIGIT_CLUES,
    FallbackQuestProvider,
    QuestContext,
    StaticQuestProvider,
    leaks_digit,
)
from cryptexbot.services.rewards import RewardContext  # noqa: E402

CTX = QuestContext(user_id=1, user_name="Player", chat_id=1, dial_count=3)


@contextmanager
def pinned_code(code):
    """Force random_code() to return a known combination.

    The verification cases compare a solver answer against the code, so the
    code cannot be random: with a random one, "the solver disagrees" is only
    true for the digits that happen not to match.
    """
    import cryptexbot.services.gemini as gemini_mod

    original = gemini_mod.random_code
    gemini_mod.random_code = lambda dial_count: list(code)
    try:
        yield list(code)
    finally:
        gemini_mod.random_code = original
RCTX = RewardContext(
    user_id=1, user_name="Player", chat_id=1, message_id=2,
    code="732", attempts=9, theme="a drowned observatory",
)


def fake_models(*, content=None, chunks=None, error=None, delay=0.0, as_coro=True):
    """A stand-in for ``client.aio.models`` with recorded call kwargs.

    ``content`` may be a list, in which case successive calls return successive
    entries — the quest call first, then the verification call.
    """
    seen: dict = {}
    calls: list[dict] = []
    replies = list(content) if isinstance(content, list) else [content]

    async def generate_content(**kwargs):
        seen.update(kwargs)
        calls.append(dict(kwargs))
        if delay:
            await asyncio.sleep(delay)
        if error:
            raise error
        reply = replies[min(len(calls) - 1, len(replies) - 1)]
        return SimpleNamespace(text=reply, parsed=None)

    async def _agen():
        for chunk in chunks or []:
            yield SimpleNamespace(text=chunk)

    def generate_content_stream(**kwargs):
        seen.update(kwargs)
        return _agen()

    async def generate_content_stream_coro(**kwargs):
        seen.update(kwargs)
        return _agen()

    models = SimpleNamespace(
        generate_content=generate_content,
        generate_content_stream=(
            generate_content_stream_coro if as_coro else generate_content_stream
        ),
    )
    seen["calls"] = calls
    return SimpleNamespace(aio=SimpleNamespace(models=models)), seen


def quest_provider(verify=False, **kw):
    provider = GeminiQuestProvider.__new__(GeminiQuestProvider)
    client, seen = fake_models(**kw)
    provider._client = client
    provider._model = "gemini-2.5-flash"
    provider._verify = verify
    return provider, seen


GOOD_QUEST = json.dumps(
    {
        "theme": "a salt mine",
        "riddle": "The lift cable still swings.",
        "clues": [
            "Count the days the almanac gives a week.",
            "Count the oars a rower pulls.",
            "Count the legs of the milking stool.",
        ],
    }
)


def reward_provider(**kw):
    provider = GeminiRewardProvider.__new__(GeminiRewardProvider)
    client, seen = fake_models(**kw)
    provider._client = client
    provider._model = "gemini-2.5-flash"
    return provider, seen


async def main() -> None:
    # --- the schema pins the exact contract -------------------------------- #
    schema = _quest_schema(3)
    clues = schema.properties["clues"]
    assert schema.required == ["theme", "riddle", "clues"]
    assert "code" not in schema.properties, "the model is never asked for the code"
    assert (clues.min_items, clues.max_items) == (3, 3)
    solver = _solver_schema(3)
    digits = solver.properties["digits"]
    assert (digits.items.minimum, digits.items.maximum) == (0, 9)
    assert (digits.min_items, digits.max_items) == (3, 3)
    print("ok  quest schema asks for {theme, riddle, clues} — never the code")

    # --- happy path: the code is local, the digits reach the prompt --------- #
    provider, seen = quest_provider(content=GOOD_QUEST)
    quest = await provider.generate(CTX)
    assert len(quest.code) == 3 and all(0 <= d <= 9 for d in quest.code)
    assert quest.theme == "a salt mine"
    assert len(quest.clues) == 3
    prompt = seen["contents"]
    for ordinal, digit in zip(["First", "Second", "Third"], quest.code):
        assert f"{ordinal} dial: the answer is {digit}" in prompt
    cfg = seen["config"]
    assert cfg.response_mime_type == "application/json"
    assert cfg.thinking_config.thinking_budget == 0
    print("ok  code chosen in Python and handed to the model, dial by dial")

    # --- two vaults in a row are different --------------------------------- #
    seen_codes = set()
    for _ in range(50):
        provider, _ = quest_provider(content=GOOD_QUEST)
        seen_codes.add(tuple((await provider.generate(CTX)).code))
    assert len(seen_codes) > 10, seen_codes
    print("ok  the combination is fresh per vault")

    # --- `parsed` is preferred when the SDK supplies it -------------------- #
    assert _parse_json(SimpleNamespace(parsed={"theme": "t"}, text="{}")) == {"theme": "t"}
    print("ok  SDK-parsed payload preferred over raw text")

    # --- a leaking clue is repaired before the player ever sees it ---------- #
    leaky = json.dumps(
        {
            "theme": "a salt mine",
            "riddle": "Dust.",
            "clues": ["The tag reads 7.", "Count the two oars.", "Count the stool legs."],
        }
    )
    for _ in range(30):
        provider, _ = quest_provider(content=leaky)
        quest = await provider.generate(CTX)
        for clue, digit in zip(quest.clues, quest.code):
            assert not leaks_digit(clue, digit), (clue, digit)
    print("ok  clues that leak are cleaned or replaced before display")

    # --- garbage in, playable vault out ------------------------------------ #
    for bad in ("", "I'm afraid I can't do that", "[1, 2, 3]", '{"clues": []}'):
        provider, _ = quest_provider(content=bad)
        guarded = FallbackQuestProvider(provider, StaticQuestProvider())
        quest = await guarded.generate(CTX)
        assert len(quest.code) == 3 and len(quest.clues) == 3, bad
        assert quest.theme and quest.riddle and all(quest.clues), bad
    print("ok  empty / prose / wrong-shape responses still yield a playable vault")

    # --- verification: a clue that does not solve back is swapped out ------- #
    provider, seen = quest_provider(
        verify=True,
        content=[GOOD_QUEST, json.dumps({"digits": [5, 5, 5]})],
    )
    with pinned_code([7, 3, 2]) as code:  # no digit matches the solver's answer
        quest = await provider.generate(CTX)
    assert quest.code == code
    assert len(seen["calls"]) == 2, "verification must be a second call"
    solver_prompt = seen["calls"][1]["contents"]
    assert "almanac gives a week" in solver_prompt, "the solver reads the clue text"
    assert "732" not in solver_prompt, "the solver must not see the combination"
    assert not any(ch.isdigit() for ch in solver_prompt), "no digits in the solver prompt"
    assert seen["calls"][1]["config"].temperature == 0.0
    for clue, digit in zip(quest.clues, code):
        assert clue in DIGIT_CLUES[digit], "mismatched clues fall back to known-good"
    print("ok  clues are solved cold and replaced when the answer disagrees")

    # --- verification: agreement keeps the model's prose -------------------- #
    provider, seen = quest_provider(
        verify=True, content=[GOOD_QUEST, json.dumps({"digits": [7, 3, 2]})]
    )
    with pinned_code([7, 3, 2]):
        quest = await provider.generate(CTX)
    assert quest.clues[0] == "Count the days the almanac gives a week."
    assert quest.clues[2] == "Count the legs of the milking stool."
    print("ok  clues that solve correctly are kept as the model wrote them")

    # --- verification: only the wrong clue is replaced ---------------------- #
    provider, _ = quest_provider(
        verify=True, content=[GOOD_QUEST, json.dumps({"digits": [7, 3, 5]})]
    )
    with pinned_code([7, 3, 2]):
        quest = await provider.generate(CTX)
    assert quest.clues[0] == "Count the days the almanac gives a week."
    assert quest.clues[2] in DIGIT_CLUES[2], "only the disagreeing clue is swapped"
    print("ok  verification replaces only the clue that failed")

    # --- verification failure is not fatal ---------------------------------- #
    provider, _ = quest_provider(verify=True, content=[GOOD_QUEST, "not json"])
    quest = await provider.generate(CTX)
    assert quest.clues[0] == "Count the days the almanac gives a week."
    print("ok  a failed verification keeps the leak-scanned clues")

    # --- a hanging API does not hang the player ---------------------------- #
    import cryptexbot.services.gemini as gemini_mod

    original = gemini_mod.QUEST_TIMEOUT
    gemini_mod.QUEST_TIMEOUT = 0.05
    try:
        provider, _ = quest_provider(content="{}", delay=5)
        guarded = FallbackQuestProvider(provider, StaticQuestProvider())
        quest = await asyncio.wait_for(guarded.generate(CTX), timeout=2)
        assert len(quest.code) == 3 and len(quest.clues) == 3
    finally:
        gemini_mod.QUEST_TIMEOUT = original
    print("ok  a hung quest call times out and falls back locally")

    # --- streaming yields cumulative text, both SDK conventions ------------ #
    for as_coro in (True, False):
        provider, seen = reward_provider(
            chunks=["You step ", "into the ", "dark."], as_coro=as_coro
        )
        seq = [partial async for partial in provider.stream(RCTX)]
        assert seq == ["You step ", "You step into the ", "You step into the dark."], seq
        assert "drowned observatory" in seen["contents"], "theme must reach the prompt"
    print("ok  streaming yields cumulative text (awaitable and direct iterators)")

    # --- the adapter tolerates both shapes directly ------------------------ #
    async def agen():
        yield 1
        yield 2

    async def coro():
        return agen()

    assert [x async for x in _aiter(agen())] == [1, 2]
    assert [x async for x in _aiter(coro())] == [1, 2]
    print("ok  _aiter normalises awaitable and plain async iterators")

    print("\nall checks passed")


if __name__ == "__main__":
    asyncio.run(main())
