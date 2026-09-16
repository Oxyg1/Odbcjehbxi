"""Google Gemini integration: riddle authoring, clue verification, and the reveal.

Three calls, three shapes:

* **Quest** (:class:`GeminiQuestProvider`) — one blocking call in JSON mode.
  Python has already chosen the combination; the model is asked to dress those
  exact digits in clues. It never picks the answer.
* **Verify** (:meth:`GeminiQuestProvider.verify_clues`) — a second, cheap JSON
  call that reads the clues *cold*, with no knowledge of the code, and says
  what each one resolves to. Any clue that does not solve back to its digit is
  swapped for a known-correct local one. This is the difference between a
  riddle that looks solvable and one that is.
* **Reveal** (:class:`GeminiRewardProvider`) — a streaming call whose chunks are
  pushed into the Telegram caption as they land.

All of them disable thinking (``thinking_budget=0``). These are short
generations where a thinking pass buys nothing and costs the player seconds of
staring at a sealed vault.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any, AsyncIterator

from .quests import (
    Quest,
    QuestContext,
    QuestProvider,
    coerce_quest,
    local_clue,
    random_code,
)
from .rewards import RewardContext, RewardProvider

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"
QUEST_TIMEOUT = 15.0  # a player is staring at a sealed vault while this runs
VERIFY_TIMEOUT = 12.0
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
    """Response contract: ``{"theme": str, "riddle": str, "clues": [str, ...]}``.

    Note what is *absent*: the code. The model is not asked for it and cannot
    supply it — the combination is already fixed in Python before this call.
    """
    from google.genai import types

    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "theme": types.Schema(type=types.Type.STRING),
            "riddle": types.Schema(type=types.Type.STRING),
            "clues": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
                min_items=dial_count,
                max_items=dial_count,
            ),
        },
        required=["theme", "riddle", "clues"],
        property_ordering=["theme", "riddle", "clues"],
    )


def _solver_schema(count: int):
    """Response contract for the verification pass: ``{"digits": [int, ...]}``."""
    from google.genai import types

    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "digits": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.INTEGER, minimum=0, maximum=9),
                min_items=count,
                max_items=count,
            )
        },
        required=["digits"],
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


def _parse_json(response: Any) -> dict:
    """Read the JSON body, preferring ``parsed`` when the SDK supplies it."""
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, dict):
        return parsed

    text = (getattr(response, "text", None) or "").strip()
    if not text:
        raise ValueError("Gemini returned an empty response")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Gemini returned non-JSON: {text[:200]!r}") from error
    if not isinstance(data, dict):
        raise ValueError(f"Gemini returned a {type(data).__name__}, expected an object")
    return data


# --------------------------------------------------------------------------- #
# 1. Riddle authoring (JSON mode) — the code is an input, never an output
# --------------------------------------------------------------------------- #

class GeminiQuestProvider(QuestProvider):
    """Dresses a locally chosen combination in a solvable riddle."""

    def __init__(
        self, api_key: str, model: str = DEFAULT_MODEL, verify: bool = True
    ) -> None:
        self._client = _client(api_key)
        self._model = model
        self._verify = verify

    def _prompt(self, ctx: QuestContext, code: list[int]) -> str:
        lines = "\n".join(
            f"  - {ordinal} dial: the answer is {digit}"
            for ordinal, digit in zip(
                ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth"],
                code,
            )
        )
        return (
            f"Write the riddle for a vault belonging to {ctx.user_name}.\n\n"
            f"The combination is already fixed. Your clues must point to these "
            f"digits, in this order:\n{lines}\n\n"
            "Return three fields.\n\n"
            "theme: 2 to 5 words naming the place or collection this vault "
            "belongs to, for example 'a drowned observatory'.\n\n"
            "riddle: one or two sentences setting the scene. It introduces the "
            "place. It must contain no clue and no number.\n\n"
            f"clues: exactly {ctx.dial_count} sentences, one per dial, in dial "
            "order. Each clue must:\n"
            "  - name a set of things the reader can count, where the size of "
            "that set is common knowledge and is exactly that dial's digit "
            "(days in a week, legs of a spider, seasons in a year, moons over "
            "the earth, and so on);\n"
            "  - resolve to one and only one number, with no arithmetic and no "
            "ambiguity;\n"
            "  - belong to the theme, so the clues read as one scene;\n"
            "  - never contain a digit character, and never write the answer as "
            "a word ('seven', 'seventh'). Name the countable set and let the "
            "reader do the counting.\n\n"
            "A clue for zero names a set that is empty or destroyed. Two dials "
            "with the same digit must use different sets."
        )

    async def generate(self, ctx: QuestContext) -> Quest:
        from google.genai import types

        # The answer is decided here, in Python, before the model is involved.
        code = random_code(ctx.dial_count)

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=_quest_schema(ctx.dial_count),
            # High enough that repeated vaults do not converge on the same
            # scene, low enough that the clues stay disciplined.
            temperature=1.15,
            max_output_tokens=700,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        response = await asyncio.wait_for(
            self._client.aio.models.generate_content(
                model=self._model, contents=self._prompt(ctx, code), config=config
            ),
            timeout=QUEST_TIMEOUT,
        )

        # coerce_quest runs the leak scan: numerals stripped, any clue that
        # names its own digit swapped for a local one.
        quest = coerce_quest(_parse_json(response), code)

        if self._verify:
            quest.clues = await self.verify_clues(quest.clues, code)

        log.info("generated quest: theme=%r dials=%d", quest.theme, len(quest.code))
        return quest

    # ----------------------------------------------------------------- #
    # 2. Verification: solve the riddle cold and compare
    # ----------------------------------------------------------------- #

    async def verify_clues(self, clues: list[str], code: list[int]) -> list[str]:
        """Round-trip the clues through a solver that has not seen the code.

        A leak scan proves a clue does not *state* the answer; it says nothing
        about whether the clue *reaches* it. This does: the model is shown the
        clue text alone and asked what each resolves to. Anything that comes
        back wrong is replaced with a clue from the local bank, which is known
        to be correct.

        Never raises. A failed verification leaves the clues as they are —
        they have still passed the leak scan, so the worst case is the puzzle
        we would have shipped anyway.
        """
        from google.genai import types

        try:
            numbered = "\n".join(f"{i + 1}. {clue}" for i, clue in enumerate(clues))
            prompt = (
                "Each line below is a riddle clue that resolves to exactly one "
                "digit from 0 to 9 by counting a well-known set. Answer with "
                "the digit each line resolves to, in order. Do not explain.\n\n"
                f"{numbered}"
            )
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_solver_schema(len(clues)),
                temperature=0.0,  # verification is not a creative act
                max_output_tokens=200,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model, contents=prompt, config=config
                ),
                timeout=VERIFY_TIMEOUT,
            )
            solved = _parse_json(response).get("digits")
            if not isinstance(solved, list) or len(solved) != len(clues):
                log.warning("solver returned an unusable answer; keeping clues as-is")
                return clues
        except Exception:  # noqa: BLE001 - verification is best-effort
            log.exception("clue verification failed; keeping clues as-is")
            return clues

        checked = list(clues)
        wrong = 0
        for index, (guess, digit) in enumerate(zip(solved, code)):
            try:
                ok = int(guess) == digit
            except (TypeError, ValueError):
                ok = False
            if not ok:
                checked[index] = local_clue(digit, avoid=clues[index])
                wrong += 1

        if wrong:
            log.warning(
                "%d of %d clues did not solve back to their digit; replaced",
                wrong,
                len(code),
            )
        return checked


# --------------------------------------------------------------------------- #
# 3. Cinematic victory streaming
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
            f"who found the combination after {ctx.attempts} turns of the "
            "dials.\n\n"
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
