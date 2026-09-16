"""The puzzle itself: a locally chosen combination, dressed in a solvable riddle.

The division of labour matters. **Python owns the code**: `random.randint` picks
the digits, so the answer is never something a model decided and never
something a prompt injection can talk its way into. **Gemini owns the prose**:
it writes one clue per dial, each pointing at a digit the code already fixed.

That ordering is what makes the riddle solvable. When the model invented the
code and the riddle in a single pass, nothing tied the two together and the
"clues" were decoration. Now the digits are an input, and a clue that fails to
resolve is a detectable defect — see `LeakScanner` for the text check and
`gemini.verify_clues` for the round-trip solve.
"""

from __future__ import annotations

import logging
import random
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoids importing settings at runtime
    from ..config import Settings

log = logging.getLogger(__name__)

# Words for the dials, so the caption can label clues without printing numerals
# next to a puzzle whose answer is numerals.
ORDINALS = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth"]

# Deterministic clues, one bank per digit. Every line resolves by counting a set
# whose size is fixed by common knowledge, and none of them contains a numeral
# or the digit's own name — they pass the same leak scan the model's output has
# to pass. These are the safety net: any clue that leaks or fails the solver
# round-trip is replaced by one of these, which is *known* to be correct.
DIGIT_CLUES: dict[int, tuple[str, ...]] = {
    0: (
        "Count the windows in the sealed cellar; the walls are unbroken.",
        "Count the coins left in the offering box after the fire.",
    ),
    1: (
        "Count the moons over the courtyard.",
        "Count the suns that rise on any morning here.",
    ),
    2: (
        "Count the oars a rower pulls.",
        "Count the eyes in the portrait above the desk.",
    ),
    3: (
        "Count the legs of the milking stool by the door.",
        "Count the sides of the surveyor's iron triangle.",
    ),
    4: (
        "Count the seasons the almanac names.",
        "Count the wheels beneath the mail coach.",
    ),
    5: (
        "Count the fingers inside the left glove.",
        "Count the points on the star cut into the lintel.",
    ),
    6: (
        "Count the walls of a single cell in the honeycomb.",
        "Count the strings on the pawned guitar.",
    ),
    7: (
        "Count the days the almanac gives a week.",
        "Count the colours the rain leaves across the sky.",
    ),
    8: (
        "Count the legs of the spider on the sill.",
        "Count the arms of the octopus in the cannery's sign.",
    ),
    9: (
        "Count the lives a cat is said to spend.",
        "Count the months a child waits to be born.",
    ),
}

# Flavour used when there is no API key at all, or the call fails outright.
FALLBACK_THEMES = [
    ("a drowned observatory", "Salt has eaten the brass, but the tide still keeps time."),
    ("a cartographer's estate", "Every map here agrees on one road, and it does not exist."),
    ("the last night train", "The timetable lists a station that burned down twice."),
    ("a watchmaker's cellar", "Ten thousand hands, and not one of them agrees."),
    ("an archive of forged letters", "The signatures are perfect. The people never were."),
]


@dataclass(slots=True)
class Quest:
    """One generated puzzle: the answer, the framing, and a clue per dial."""

    code: list[int]
    theme: str
    riddle: str
    clues: list[str] = field(default_factory=list)


@dataclass(slots=True)
class QuestContext:
    """Who is asking for a vault, and how big it is."""

    user_id: int
    user_name: str
    chat_id: int
    dial_count: int


class QuestProvider(ABC):
    @abstractmethod
    async def generate(self, ctx: QuestContext) -> Quest:
        """Produce a fresh quest. Must never raise — see FallbackQuestProvider."""


def random_code(dial_count: int) -> list[int]:
    """The combination. Chosen here, in Python, and never by a model."""
    return [random.randint(0, 9) for _ in range(dial_count)]


def local_clue(digit: int, avoid: str | None = None) -> str:
    """A known-correct clue for one digit, ideally not one already in use."""
    options = [c for c in DIGIT_CLUES[digit] if c != avoid] or list(DIGIT_CLUES[digit])
    return random.choice(options)


# --------------------------------------------------------------------------- #
# Leak scanning
# --------------------------------------------------------------------------- #

NUMERAL_RE = re.compile(r"\d")

# Cardinal names, plus the suffixes that turn them into ordinals and teens, so
# "the seventh lamp" is caught as readily as "seven lamps".
_CARDINALS = {
    0: ("zero", "nought", "naught", "none", "nil"),
    1: ("one",),
    2: ("two",),
    3: ("three", "third"),
    4: ("four",),
    5: ("five", "fifth"),
    6: ("six",),
    7: ("seven",),
    8: ("eight", "eighth"),
    9: ("nine", "ninth"),
}
_WORD_RE = {
    digit: re.compile(
        r"\b(" + "|".join(words) + r")(th|ty|teen|s)?\b",
        re.IGNORECASE,
    )
    for digit, words in _CARDINALS.items()
}


def leaks_digit(text: str, digit: int) -> bool:
    """True if ``text`` gives its digit away outright.

    Two ways that happens, both of which ruin the puzzle:

    * **any numeral at all** — `7`, `"7"`, `07`. A clue has no legitimate use
      for a digit character, so this is checked regardless of which digit.
    * **the digit's own name** — "seven lamps", "the seventh lamp". Counting
      devices like "a pair of gloves" are the intended mechanism and are left
      alone; only naming the answer counts as a leak.
    """
    if NUMERAL_RE.search(text):
        return True
    return bool(_WORD_RE[digit].search(text))


def strip_numerals(text: str) -> str:
    """Remove digit characters and tidy the wreckage.

    Used on the framing riddle, where a stray numeral is usually incidental
    ("Room 12") rather than the whole point of the sentence.
    """
    cleaned = NUMERAL_RE.sub("", text)
    cleaned = re.sub(r"[\"'“”‘’]\s*[\"'“”‘’]", "", cleaned)  # emptied quotes
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    return cleaned.strip()


def sanitize_clues(clues: list[str], code: list[int]) -> tuple[list[str], list[int]]:
    """Force the clue list to be the right length and free of leaks.

    Returns the repaired clues and the indices that had to be replaced. A
    replaced clue is a *correct* clue from `DIGIT_CLUES`, so repairing never
    makes a vault unsolvable — it only makes it less atmospheric.
    """
    repaired: list[str] = []
    replaced: list[int] = []

    for index, digit in enumerate(code):
        raw = (clues[index] if index < len(clues) else "") or ""
        clue = " ".join(str(raw).split())[:220]

        if not clue:
            repaired.append(local_clue(digit))
            replaced.append(index)
            continue

        if leaks_digit(clue, digit):
            # Try cleaning first: a numeral can often just be deleted. If the
            # digit's *name* is in there, the sentence is built around saying
            # it and there is nothing to salvage.
            cleaned = strip_numerals(clue)
            if cleaned and not leaks_digit(cleaned, digit):
                log.info("clue %d leaked a numeral; cleaned it", index)
                repaired.append(cleaned)
                continue
            log.info("clue %d named its digit; replaced with a local clue", index)
            repaired.append(local_clue(digit))
            replaced.append(index)
            continue

        repaired.append(clue)

    return repaired, replaced


def coerce_quest(raw: object, code: list[int]) -> Quest:
    """Turn whatever the model returned into a Quest we can actually play.

    ``code`` is passed in, not read out: the combination was decided before the
    model was ever called. Structured output makes the *shape* reliable, never
    the *values*, so every field is repaired rather than trusted.
    """
    data = raw if isinstance(raw, dict) else {}

    theme = " ".join(str(data.get("theme") or "").split())
    riddle = " ".join(str(data.get("riddle") or "").split())
    if not theme or not riddle:
        spare_theme, spare_riddle = random.choice(FALLBACK_THEMES)
        theme = theme or spare_theme
        riddle = riddle or spare_riddle

    # The framing line must not give the game away either.
    if NUMERAL_RE.search(riddle):
        riddle = strip_numerals(riddle)
    if any(_WORD_RE[digit].search(riddle) for digit in set(code)):
        log.info("framing riddle named a digit; using local flavour instead")
        riddle = random.choice(FALLBACK_THEMES)[1]

    raw_clues = data.get("clues")
    clues, replaced = sanitize_clues(
        list(raw_clues) if isinstance(raw_clues, list) else [], code
    )
    if replaced:
        log.warning("replaced %d of %d clues after leak scan", len(replaced), len(code))

    return Quest(code=list(code), theme=theme[:120], riddle=riddle[:400], clues=clues)


def local_quest(code: list[int]) -> Quest:
    """A complete, guaranteed-solvable quest with no model involved."""
    theme, riddle = random.choice(FALLBACK_THEMES)
    return Quest(
        code=list(code),
        theme=theme,
        riddle=riddle,
        clues=[local_clue(d) for d in code],
    )


class StaticQuestProvider(QuestProvider):
    """No API key, no network: local code, local clues, canned flavour.

    The code is still random per vault and the clues still resolve, so the game
    is fully playable offline — just less atmospheric.
    """

    def __init__(self, fixed_code: str | None = None) -> None:
        self._fixed = [int(c) for c in fixed_code] if fixed_code else None

    async def generate(self, ctx: QuestContext) -> Quest:
        code = list(self._fixed) if self._fixed else random_code(ctx.dial_count)
        return local_quest(code)


class FallbackQuestProvider(QuestProvider):
    """Wraps a provider so a dead API never blocks a player from starting."""

    def __init__(self, primary: QuestProvider, fallback: QuestProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    async def generate(self, ctx: QuestContext) -> Quest:
        try:
            return await self._primary.generate(ctx)
        except Exception:  # noqa: BLE001 - a failed quest must not kill the game
            log.exception("quest provider failed; falling back to local generation")
            return await self._fallback.generate(ctx)


def build_quest_provider(settings: "Settings") -> QuestProvider:
    """Gemini when a key is configured, local generation otherwise."""
    local = StaticQuestProvider(settings.secret_code)
    if not settings.gemini_api_key:
        log.warning("no GEMINI_API_KEY: vaults will use locally generated clues")
        return local

    from .gemini import GeminiQuestProvider

    return FallbackQuestProvider(
        GeminiQuestProvider(
            settings.gemini_api_key,
            settings.gemini_model,
            verify=settings.quest_verify,
        ),
        local,
    )
