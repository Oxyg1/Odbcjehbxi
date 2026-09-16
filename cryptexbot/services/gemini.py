"""Google Gemini integration: quest generation (JSON mode) + victory streaming.

Two calls, two very different shapes:

* **Quest** — one blocking call with ``response_schema``, so the model returns
  parseable JSON instead of prose we would have to regex. Structured output
  guarantees the shape, never the values, so everything is still validated in
  ``quests.coerce_quest``.
* **Reveal** — a streaming call whose chunks are pushed into the Telegram
  caption as they land, which is what produces the typewriter effect.

Both disable thinking (``thinking_budget=0``). These are short creative
generations where a thinking pass buys nothing and costs the player one to
several seconds of staring at a sealed vault.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any, AsyncIterator

from .quests import Quest, QuestContext, QuestProvider, coerce_quest
from .rewards import RewardContext, RewardProvider

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"
QUEST_TIMEOUT = 15.0  # a player is staring at a sealed vault while this runs
REVEAL_TIMEOUT = 45.0

SYSTEM_INSTRUCTION = (
    "You write for CryptexBot, a Telegram puzzle game about cracking a safe. "
    "Your register is tight, atmospheric heist-noir. Never use emoji, markdown, "
    "headings, or preamble. Never mention that you are an AI or a model."
)


def _client(api_key: str):
    """Build a genai client. Imported lazily so the SDK stays optional."""
    from google import genai

    return genai.Client(api_key=api_key)


def _quest_schema(dial_count: int):
    """Exact response contract: {"code": [x, y, z], "theme": str, "riddle": str}."""
    from google.genai import types

    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "code": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.INTEGER, minimum=0, maximum=9),
                min_items=dial_count,
                max_items=dial_count,
            ),
            "theme": types.Schema(type=types.Type.STRING),
            "riddle": types.Schema(type=types.Type.STRING),
        },
        required=["code", "theme", "riddle"],
        property_ordering=["code", "theme", "riddle"],
    )


async def _aiter(stream_or_coro: Any) -> AsyncIterator[Any]:
    """Normalise the streaming call across google-genai versions.

    Some releases return the async iterator directly; others return a coroutine
    that resolves to one.
    """
    stream = stream_or_coro
    if inspect.isawaitable(stream):
        stream = await stream
    async for chunk in stream:
        yield chunk


# --------------------------------------------------------------------------- #
# 1. Dynamic quest generation (JSON mode)
# --------------------------------------------------------------------------- #

class GeminiQuestProvider(QuestProvider):
    """Asks Gemini for a fresh combination, theme, and riddle as strict JSON."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self._client = _client(api_key)
        self._model = model

    def _prompt(self, ctx: QuestContext) -> str:
        return (
            f"Invent a brand new vault for a player named {ctx.user_name}.\n\n"
            f"1. code: {ctx.dial_count} digits, each 0-9, chosen unpredictably. "
            "Avoid obvious patterns such as 000, 123, 111 or 777.\n"
            "2. theme: 2 to 5 words naming the place or collection this vault "
            "belongs to, e.g. 'a drowned observatory'.\n"
            "3. riddle: one or two sentences, at most 200 characters, that set "
            "the scene and hint at the digits obliquely — through counted "
            "objects, hours, or floors. Never state the digits outright and "
            "never mention the word 'code'.\n\n"
            "Make this vault unlike a typical one: vary the century, the trade, "
            "and the mood."
        )

    async def generate(self, ctx: QuestContext) -> Quest:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=_quest_schema(ctx.dial_count),
            # High temperature is the whole point here: repeated vaults should
            # not converge on the same safe.
            temperature=1.4,
            max_output_tokens=400,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        response = await asyncio.wait_for(
            self._client.aio.models.generate_content(
                model=self._model, contents=self._prompt(ctx), config=config
            ),
            timeout=QUEST_TIMEOUT,
        )

        payload = _parse_json(response)
        quest = coerce_quest(payload, ctx.dial_count)
        log.info("generated quest: theme=%r digits=%d", quest.theme, len(quest.code))
        return quest


def _parse_json(response: Any) -> dict:
    """Read the JSON body, preferring ``parsed`` when the SDK supplies it."""
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, dict):
        return parsed

    text = (getattr(response, "text", None) or "").strip()
    if not text:
        raise ValueError("Gemini returned an empty quest response")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Gemini returned non-JSON quest: {text[:200]!r}") from error
    if not isinstance(data, dict):
        raise ValueError(f"Gemini returned a {type(data).__name__}, expected an object")
    return data


# --------------------------------------------------------------------------- #
# 2. Cinematic victory streaming
# --------------------------------------------------------------------------- #

class GeminiRewardProvider(RewardProvider):
    """Streams the reveal, themed on the quest the player just solved.

    Yields the *cumulative* text so the caller can drop it straight into
    ``editMessageCaption``. Deliberately un-throttled: buffering belongs in the
    renderer, which is the only layer that knows Telegram's edit limits.
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self._client = _client(api_key)
        self._model = model

    def _prompt(self, ctx: RewardContext) -> str:
        theme = ctx.theme or "a forgotten private vault"
        return (
            f"The vault of {theme} has just swung open for {ctx.user_name}, "
            f"who found the combination {ctx.code} after {ctx.attempts} turns "
            "of the dials.\n\n"
            "Write 2-3 sentences, present tense, second person, describing what "
            "they see inside. Be specific and cinematic: name one object, one "
            "detail of light or sound, and one thing that suggests someone left "
            "in a hurry. End on the single object worth taking."
        )

    async def stream(self, ctx: RewardContext) -> AsyncIterator[str]:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=1.15,
            max_output_tokens=300,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        buffer = ""
        deadline = asyncio.get_running_loop().time() + REVEAL_TIMEOUT

        stream = self._client.aio.models.generate_content_stream(
            model=self._model, contents=self._prompt(ctx), config=config
        )
        async for chunk in _aiter(stream):
            delta = getattr(chunk, "text", None)
            if delta:
                buffer += delta
                yield buffer
            if asyncio.get_running_loop().time() > deadline:
                log.warning("reveal stream exceeded %ss; cutting it short", REVEAL_TIMEOUT)
                break


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #

def build_gemini_providers(
    api_key: str, model: str
) -> tuple[GeminiQuestProvider, GeminiRewardProvider]:
    """Both providers share nothing but the key; separate clients keep them
    independently swappable."""
    return GeminiQuestProvider(api_key, model), GeminiRewardProvider(api_key, model)
