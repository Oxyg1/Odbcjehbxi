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
    DEFAULT_MODEL,
    GeminiQuestProvider,
    GeminiRewardProvider,
    _aiter,
    _describe_failure,
    _is_unsupported_parameter,
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
        if isinstance(reply, Exception):
            raise reply
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
    provider._model = DEFAULT_MODEL
    provider._verify = verify
    provider._drop_optional = False
    return provider, seen


EN_CLUES = [
    "Count the days the almanac gives a week.",
    "Count the oars a rower pulls.",
    "Count the legs of the milking stool.",
]
RU_CLUES = [
    "Сосчитайте дни, которые альманах отводит неделе.",
    "Сосчитайте вёсла в руках гребца.",
    "Сосчитайте ножки доильного табурета.",
]
GOOD_QUEST = json.dumps(
    {
        "theme_en": "a salt mine",
        "riddle_en": "The lift cable still swings.",
        "clues_en": EN_CLUES,
        "theme_ru": "соляная шахта",
        "riddle_ru": "Трос подъёмника всё ещё качается.",
        "clues_ru": RU_CLUES,
    },
    ensure_ascii=False,
)


def reward_provider(**kw):
    provider = GeminiRewardProvider.__new__(GeminiRewardProvider)
    client, seen = fake_models(**kw)
    provider._client = client
    provider._model = DEFAULT_MODEL
    provider._drop_optional = False
    return provider, seen


async def main() -> None:
    # --- the schema pins the exact contract -------------------------------- #
    schema = _quest_schema(3)
    assert "code" not in schema.properties, "the model is never asked for the code"
    for lang in ("en", "ru"):
        assert f"theme_{lang}" in schema.properties
        assert f"riddle_{lang}" in schema.properties
        clues = schema.properties[f"clues_{lang}"]
        assert (clues.min_items, clues.max_items) == (3, 3), lang
    assert set(schema.required) == set(schema.properties)
    solver = _solver_schema(3)
    digits = solver.properties["digits"]
    assert (digits.items.minimum, digits.items.maximum) == (0, 9)
    assert (digits.min_items, digits.max_items) == (3, 3)
    print("ok  quest schema asks for both languages at once — never the code")

    # --- happy path: the code is local, the digits reach the prompt --------- #
    provider, seen = quest_provider(content=GOOD_QUEST)
    quest = await provider.generate(CTX)
    assert len(quest.code) == 3 and all(0 <= d <= 9 for d in quest.code)
    assert quest.theme["en"] == "a salt mine"
    assert quest.theme["ru"] == "соляная шахта"
    assert len(quest.clues["en"]) == 3 and len(quest.clues["ru"]) == 3
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
            "theme_en": "a salt mine",
            "riddle_en": "Dust.",
            "clues_en": ["The tag reads 7.", "Count the two oars.", "Count the stool legs."],
            "theme_ru": "соляная шахта",
            "riddle_ru": "Пыль.",
            "clues_ru": ["На бирке 7.", "Сосчитайте два весла.", "Сосчитайте ножки."],
        },
        ensure_ascii=False,
    )
    for _ in range(30):
        provider, _ = quest_provider(content=leaky)
        quest = await provider.generate(CTX)
        for lang in ("en", "ru"):
            for clue, digit in zip(quest.clues[lang], quest.code):
                assert not leaks_digit(clue, digit), (lang, clue, digit)
    print("ok  clues that leak are cleaned or replaced before display")

    # --- garbage in, playable vault out ------------------------------------ #
    for bad in ("", "I'm afraid I can't do that", "[1, 2, 3]", '{"clues_en": []}'):
        provider, _ = quest_provider(content=bad)
        guarded = FallbackQuestProvider(provider, StaticQuestProvider())
        quest = await guarded.generate(CTX)
        assert len(quest.code) == 3, bad
        for lang in ("en", "ru"):
            assert len(quest.clues[lang]) == 3, (bad, lang)
            assert quest.theme[lang] and quest.riddle[lang], (bad, lang)
    print("ok  empty / prose / wrong-shape responses still yield a playable vault")

    # --- verification: a clue that does not solve back is swapped out ------- #
    provider, seen = quest_provider(
        verify=True,
        content=[GOOD_QUEST, json.dumps({"digits": [5, 5, 5, 5, 5, 5]})],
    )
    with pinned_code([7, 3, 2]) as code:  # no digit matches the solver's answer
        quest = await provider.generate(CTX)
    assert quest.code == code
    assert len(seen["calls"]) == 2, "verification must be a second call"
    solver_prompt = seen["calls"][1]["contents"]
    assert "almanac gives a week" in solver_prompt, "the solver reads the clue text"
    assert "альманах отводит неделе" in solver_prompt, "both languages in one call"
    assert "732" not in solver_prompt, "the solver must not see the combination"
    assert not any(ch.isdigit() for ch in solver_prompt), "no digits in the solver prompt"
    assert seen["calls"][1]["config"].temperature == 0.0
    for lang in ("en", "ru"):
        for clue, digit in zip(quest.clues[lang], code):
            assert clue in DIGIT_CLUES[lang][digit], "mismatched clues fall back locally"
    print("ok  clues in both languages are solved cold and replaced when wrong")

    # --- verification: agreement keeps the model's prose -------------------- #
    provider, seen = quest_provider(
        verify=True, content=[GOOD_QUEST, json.dumps({"digits": [7, 3, 2, 7, 3, 2]})]
    )
    with pinned_code([7, 3, 2]):
        quest = await provider.generate(CTX)
    assert quest.clues["en"][0] == EN_CLUES[0]
    assert quest.clues["ru"][0] == RU_CLUES[0]
    print("ok  clues that solve correctly are kept as the model wrote them")

    # --- verification: one bad Russian clue does not touch the English ------ #
    provider, _ = quest_provider(
        verify=True, content=[GOOD_QUEST, json.dumps({"digits": [7, 3, 2, 7, 3, 5]})]
    )
    with pinned_code([7, 3, 2]):
        quest = await provider.generate(CTX)
    assert quest.clues["en"] == EN_CLUES, "English untouched"
    assert quest.clues["ru"][0] == RU_CLUES[0] and quest.clues["ru"][1] == RU_CLUES[1]
    assert quest.clues["ru"][2] in DIGIT_CLUES["ru"][2], "only the failing clue is swapped"
    print("ok  verification replaces only the clue that failed, per language")

    # --- verification failure is not fatal ---------------------------------- #
    provider, _ = quest_provider(verify=True, content=[GOOD_QUEST, "not json"])
    quest = await provider.generate(CTX)
    assert quest.clues["en"][0] == EN_CLUES[0]
    assert quest.clues["ru"][0] == RU_CLUES[0]
    print("ok  a failed verification keeps the leak-scanned clues")

    # --- a model that refuses an optional knob is retried without it -------- #
    thinking_rejected = RuntimeError(
        '400 INVALID_ARGUMENT. {"error": {"message": "Unknown name \\"thinking_config\\""}}'
    )
    provider, seen = quest_provider(content=[thinking_rejected, GOOD_QUEST])
    quest = await provider.generate(CTX)
    assert len(seen["calls"]) == 2, "one retry, not a failure"
    assert seen["calls"][0]["config"].thinking_config is not None
    assert seen["calls"][1]["config"].thinking_config is None, "the knob is dropped"
    assert quest.theme["en"] == "a salt mine", "the retry produced a real quest"
    assert provider._drop_optional, "later calls skip straight to the plain form"
    print("ok  a model that rejects thinking_config is retried without it")

    # --- an ordinary 400 is not swallowed as a config problem --------------- #
    assert not _is_unsupported_parameter(RuntimeError("400 INVALID_ARGUMENT: bad prompt"))
    assert not _is_unsupported_parameter(RuntimeError("500 INTERNAL"))
    provider, seen = quest_provider(content=[RuntimeError("500 INTERNAL"), GOOD_QUEST])
    guarded = FallbackQuestProvider(provider, StaticQuestProvider())
    quest = await guarded.generate(CTX)
    assert len(seen["calls"]) == 1, "a real error is not retried into a second call"
    assert len(quest.clues["ru"]) == 3, "it falls back locally instead"
    print("ok  a genuine API error falls back instead of retrying blindly")

    # --- opaque SDK errors become actionable messages ----------------------- #
    retired = RuntimeError(
        "404 NOT_FOUND. {'error': {'code': 404, 'message': 'This model "
        "models/gemini-2.5-flash is no longer available to new users.'}}"
    )
    hint = _describe_failure(retired, "gemini-2.5-flash")
    assert hint and "GEMINI_MODEL" in hint and "cryptexbot.models" in hint
    assert "API key" in (_describe_failure(RuntimeError("401 API_KEY_INVALID"), "m") or "")
    assert "quota" in (_describe_failure(RuntimeError("429 RESOURCE_EXHAUSTED"), "m") or "")
    assert _describe_failure(RuntimeError("something else"), "m") is None
    print("ok  retired-model, bad-key and quota errors get actionable messages")

    # --- a hanging API does not hang the player ---------------------------- #
    import cryptexbot.services.gemini as gemini_mod

    original = gemini_mod.QUEST_TIMEOUT
    gemini_mod.QUEST_TIMEOUT = 0.05
    try:
        provider, _ = quest_provider(content="{}", delay=5)
        guarded = FallbackQuestProvider(provider, StaticQuestProvider())
        quest = await asyncio.wait_for(guarded.generate(CTX), timeout=2)
        assert len(quest.code) == 3 and len(quest.clues["ru"]) == 3
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
        assert "English" in seen["contents"], "the reveal is asked for in one language"
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
