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

from ..i18n import LANGS
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

# Google retires model ids and closes old ones to new API keys, so this is a
# moving target rather than a constant. Override with GEMINI_MODEL, and run
# `python -m cryptexbot.models` to see what the key in your .env can actually
# reach.
DEFAULT_MODEL = "gemini-3.6-flash"
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
    """Response contract: theme, riddle and clues, in every language at once.

    Note what is *absent*: the code. The model is not asked for it and cannot
    supply it — the combination is already fixed in Python before this call.

    Both languages come back from one call so that switching language later is
    a caption edit rather than a regeneration. A regenerated riddle would be a
    different puzzle.
    """
    from google.genai import types

    properties = {}
    for lang in LANGS:
        properties[f"theme_{lang}"] = types.Schema(type=types.Type.STRING)
        properties[f"riddle_{lang}"] = types.Schema(type=types.Type.STRING)
        properties[f"clues_{lang}"] = types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            min_items=dial_count,
            max_items=dial_count,
        )

    ordering = [f"{field}_{lang}" for lang in LANGS for field in ("theme", "riddle", "clues")]
    return types.Schema(
        type=types.Type.OBJECT,
        properties=properties,
        required=list(properties),
        property_ordering=ordering,
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


def _describe_failure(error: Exception, model: str) -> str | None:
    """Turn an opaque SDK error into something a person can act on."""
    text = str(error)
    if "404" in text and "model" in text.lower():
        return (
            f"Gemini model {model!r} is not available to this API key. "
            "Set GEMINI_MODEL in .env to one that is — run "
            "`python -m cryptexbot.models` to list them."
        )
    if "API key" in text or "API_KEY_INVALID" in text or "401" in text:
        return "Gemini rejected the API key. Check GEMINI_API_KEY in .env."
    if "429" in text or "RESOURCE_EXHAUSTED" in text:
        return "Gemini quota exhausted for this key; falling back to local generation."
    return None


def _is_unsupported_parameter(error: Exception) -> bool:
    """True when the model rejected a knob rather than the request itself.

    Newer models drop or rename configuration fields — `thinking_config` is the
    one this bot sets that a future model is most likely to refuse. Rather than
    pinning ourselves to one generation of the API, we retry once without the
    optional knobs.
    """
    text = str(error).lower()
    if "400" not in text and "invalid_argument" not in text:
        return False
    return any(
        hint in text
        for hint in ("thinking", "unknown name", "unsupported", "not supported", "invalid json payload")
    )


# Knobs that are nice to have but never worth failing a request over.
_OPTIONAL_CONFIG = ("thinking_config",)


class _ModelCaller:
    """Shared call path: timeouts, readable errors, and one degrading retry."""

    _client: Any
    _model: str
    _drop_optional: bool = False

    async def _generate(self, contents: str, config: dict, timeout: float):
        from google.genai import types

        attempt = dict(config)
        if self._drop_optional:
            for knob in _OPTIONAL_CONFIG:
                attempt.pop(knob, None)

        try:
            return await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=types.GenerateContentConfig(**attempt),
                ),
                timeout=timeout,
            )
        except Exception as error:  # noqa: BLE001 - re-raised after diagnosis
            if _is_unsupported_parameter(error) and not self._drop_optional:
                log.warning(
                    "model %s rejected an optional config field; retrying without %s",
                    self._model,
                    ", ".join(_OPTIONAL_CONFIG),
                )
                # Remember, so every later call skips straight to the plain form.
                self._drop_optional = True
                return await self._generate(contents, config, timeout)
            hint = _describe_failure(error, self._model)
            if hint:
                log.error("%s", hint)
            raise

    def _stream_call(self, contents: str, config: dict):
        from google.genai import types

        attempt = dict(config)
        if self._drop_optional:
            for knob in _OPTIONAL_CONFIG:
                attempt.pop(knob, None)
        return self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(**attempt),
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

class GeminiQuestProvider(_ModelCaller, QuestProvider):
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
            "Return the same vault in English and in Russian: theme_en, "
            "riddle_en, clues_en, theme_ru, riddle_ru, clues_ru.\n\n"
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
            "a word. In English that means never 'seven' or 'seventh'; in "
            "Russian never 'семь', 'семи' or 'седьмой', in any case form. Name "
            "the countable set and let the reader do the counting.\n\n"
            "A clue for zero names a set that is empty or destroyed. Two dials "
            "with the same digit must use different sets.\n\n"
            "The Russian version is not a word-for-word translation: it is the "
            "same scene and the same counted sets, written as natural, idiomatic "
            "Russian. Clue N in both languages must resolve to the same digit."
        )

    async def generate(self, ctx: QuestContext) -> Quest:
        from google.genai import types

        # The answer is decided here, in Python, before the model is involved.
        code = random_code(ctx.dial_count)

        config = dict(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=_quest_schema(ctx.dial_count),
            # High enough that repeated vaults do not converge on the same
            # scene, low enough that the clues stay disciplined.
            temperature=1.15,
            max_output_tokens=700,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        response = await self._generate(self._prompt(ctx, code), config, QUEST_TIMEOUT)

        # coerce_quest runs the leak scan per language: numerals stripped, any
        # clue that names its own digit swapped for a local one.
        quest = coerce_quest(_parse_json(response), code)

        if self._verify:
            quest.clues = await self.verify_clues(quest.clues, code)

        log.info(
            "generated quest: theme=%r dials=%d langs=%s",
            quest.theme.get("en"), len(quest.code), ",".join(quest.clues),
        )
        return quest

    # ----------------------------------------------------------------- #
    # 2. Verification: solve the riddle cold and compare
    # ----------------------------------------------------------------- #

    async def verify_clues(
        self, clues: dict[str, list[str]], code: list[int]
    ) -> dict[str, list[str]]:
        """Round-trip the clues through a solver that has not seen the code.

        A leak scan proves a clue does not *state* the answer; it says nothing
        about whether the clue *reaches* it. This does: the model is shown the
        clue text alone and asked what each resolves to. Anything that comes
        back wrong is replaced with a clue from the local bank, which is known
        to be correct.

        Every language goes in one call — the clues are independent lines, so
        checking six costs barely more than three, and the English version
        being sound tells us nothing about the Russian one.

        Never raises. A failed verification leaves the clues as they are —
        they have still passed the leak scan, so the worst case is the puzzle
        we would have shipped anyway.
        """
        from google.genai import types

        langs = [lang for lang in clues if clues[lang]]
        flat: list[tuple[str, int, str]] = [
            (lang, index, clue)
            for lang in langs
            for index, clue in enumerate(clues[lang])
        ]
        if not flat:
            return clues

        try:
            # Bulleted, not numbered: a numbered list would put digit
            # characters next to clues whose answers are digits, which is both
            # a needless hint and a needless source of confusion. Nothing in
            # this prompt names the combination.
            listed = "\n".join(f"- {clue}" for _, _, clue in flat)
            prompt = (
                "Each line below is a riddle clue, in English or Russian, that "
                "resolves to exactly one digit by counting a well-known set. "
                "Answer with the digit each line resolves to, in order. Do not "
                "explain.\n\n"
                f"{listed}"
            )
            config = dict(
                response_mime_type="application/json",
                response_schema=_solver_schema(len(flat)),
                temperature=0.0,  # verification is not a creative act
                max_output_tokens=300,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )
            response = await self._generate(prompt, config, VERIFY_TIMEOUT)
            solved = _parse_json(response).get("digits")
            if not isinstance(solved, list) or len(solved) != len(flat):
                log.warning("solver returned an unusable answer; keeping clues as-is")
                return clues
        except Exception:  # noqa: BLE001 - verification is best-effort
            log.exception("clue verification failed; keeping clues as-is")
            return clues

        checked = {lang: list(items) for lang, items in clues.items()}
        wrong = 0
        for (lang, index, clue), guess in zip(flat, solved):
            digit = code[index]
            try:
                ok = int(guess) == digit
            except (TypeError, ValueError):
                ok = False
            if not ok:
                checked[lang][index] = local_clue(digit, lang, avoid=clue)
                wrong += 1

        if wrong:
            log.warning(
                "%d of %d clues did not solve back to their digit; replaced",
                wrong,
                len(flat),
            )
        return checked


# --------------------------------------------------------------------------- #
# 3. Cinematic victory streaming
# --------------------------------------------------------------------------- #

class GeminiRewardProvider(_ModelCaller, RewardProvider):
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
        language = {"ru": "Russian", "en": "English"}.get(ctx.lang, "English")
        return (
            f"The vault of {theme} has just swung open for {ctx.user_name}, "
            f"who found the combination after {ctx.attempts} turns of the "
            "dials.\n\n"
            "Write 2-3 sentences, present tense, second person, describing what "
            "they see inside. Be specific and cinematic: name one object, one "
            "detail of light or sound, and one thing that suggests someone left "
            "in a hurry. End on the single object worth taking.\n\n"
            f"Write in {language}, and in {language} only."
        )

    async def stream(self, ctx: RewardContext) -> AsyncIterator[str]:
        from google.genai import types

        config = dict(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=1.15,
            max_output_tokens=300,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        buffer = ""
        deadline = asyncio.get_running_loop().time() + REVEAL_TIMEOUT

        stream = self._stream_call(self._prompt(ctx), config)
        async for chunk in _aiter(stream):
            delta = getattr(chunk, "text", None)
            if delta:
                buffer += delta
                yield buffer
            if asyncio.get_running_loop().time() > deadline:
                log.warning("reveal stream exceeded %ss; cutting it short", REVEAL_TIMEOUT)
                break
