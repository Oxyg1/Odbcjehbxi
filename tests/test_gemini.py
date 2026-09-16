"""Gemini provider tests with a fake SDK client — no API key, no network.

Covers the parts that break in production: response parsing, schema shape,
malformed JSON, timeouts, and the streaming adapter's two calling
conventions across google-genai versions.

Run with:  python tests/test_gemini.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptexbot.services.gemini import (  # noqa: E402
    GeminiQuestProvider,
    GeminiRewardProvider,
    _aiter,
    _parse_json,
    _quest_schema,
)
from cryptexbot.services.quests import (  # noqa: E402
    FallbackQuestProvider,
    QuestContext,
    StaticQuestProvider,
)
from cryptexbot.services.rewards import RewardContext  # noqa: E402

CTX = QuestContext(user_id=1, user_name="Player", chat_id=1, dial_count=3)
RCTX = RewardContext(
    user_id=1, user_name="Player", chat_id=1, message_id=2,
    code="732", attempts=9, theme="a drowned observatory",
)


def fake_models(*, content=None, chunks=None, error=None, delay=0.0, as_coro=True):
    """A stand-in for ``client.aio.models`` with recorded call kwargs."""
    seen: dict = {}

    async def generate_content(**kwargs):
        seen.update(kwargs)
        if delay:
            await asyncio.sleep(delay)
        if error:
            raise error
        return SimpleNamespace(text=content, parsed=None)

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
    return SimpleNamespace(aio=SimpleNamespace(models=models)), seen


def quest_provider(**kw):
    provider = GeminiQuestProvider.__new__(GeminiQuestProvider)
    client, seen = fake_models(**kw)
    provider._client = client
    provider._model = "gemini-2.5-flash"
    return provider, seen


def reward_provider(**kw):
    provider = GeminiRewardProvider.__new__(GeminiRewardProvider)
    client, seen = fake_models(**kw)
    provider._client = client
    provider._model = "gemini-2.5-flash"
    return provider, seen


async def main() -> None:
    # --- the schema pins the exact contract -------------------------------- #
    schema = _quest_schema(3)
    code = schema.properties["code"]
    assert schema.required == ["code", "theme", "riddle"]
    assert schema.property_ordering == ["code", "theme", "riddle"]
    assert (code.min_items, code.max_items) == (3, 3)
    assert (code.items.minimum, code.items.maximum) == (0, 9)
    print("ok  response schema is {code: [x, y, z], theme, riddle}, digits 0-9")

    # --- happy path -------------------------------------------------------- #
    provider, seen = quest_provider(
        content='{"code": [4, 0, 8], "theme": "a salt mine", "riddle": "It hums."}'
    )
    quest = await provider.generate(CTX)
    assert quest.code == [4, 0, 8]
    assert quest.theme == "a salt mine" and quest.riddle == "It hums."
    assert seen["model"] == "gemini-2.5-flash"
    cfg = seen["config"]
    assert cfg.response_mime_type == "application/json"
    assert cfg.response_schema is not None
    assert cfg.thinking_config.thinking_budget == 0
    print("ok  JSON mode parsed; request sends schema + mime type, thinking off")

    # --- `parsed` is preferred when the SDK supplies it -------------------- #
    assert _parse_json(SimpleNamespace(parsed={"code": [1]}, text="{}")) == {"code": [1]}
    print("ok  SDK-parsed payload preferred over raw text")

    # --- garbage in, playable vault out ------------------------------------ #
    for bad in ("", "I'm afraid I can't do that", "[1, 2, 3]", '{"code": [1, 2]}'):
        provider, _ = quest_provider(content=bad)
        guarded = FallbackQuestProvider(provider, StaticQuestProvider())
        quest = await guarded.generate(CTX)
        assert len(quest.code) == 3 and all(0 <= d <= 9 for d in quest.code), bad
        assert quest.theme and quest.riddle, bad
    print("ok  empty / prose / wrong-shape responses still yield a playable vault")

    # --- a hanging API does not hang the player ---------------------------- #
    import cryptexbot.services.gemini as gemini_mod

    original = gemini_mod.QUEST_TIMEOUT
    gemini_mod.QUEST_TIMEOUT = 0.05
    try:
        provider, _ = quest_provider(content="{}", delay=5)
        guarded = FallbackQuestProvider(provider, StaticQuestProvider())
        quest = await asyncio.wait_for(guarded.generate(CTX), timeout=2)
        assert len(quest.code) == 3
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
