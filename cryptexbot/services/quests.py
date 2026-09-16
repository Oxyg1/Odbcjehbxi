"""The puzzle itself: a locally chosen combination, dressed in a solvable riddle.

The division of labour matters. **Python owns the code**: `random.randint` picks
the digits, so the answer is never something a model decided and never
something a prompt injection can talk its way into. **Gemini owns the prose**:
it writes one clue per dial, each pointing at a digit the code already fixed.

Every quest is authored in **both languages at once**, in a single call. The
alternative — translating on demand when a player switches language — would
mean regenerating the riddle mid-game, and a regenerated riddle is a different
puzzle. Carrying both means the switch is instant and the combination never
moves.
"""

from __future__ import annotations

import logging
import random
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..i18n import DEFAULT_LANG, LANGS, normalize

if TYPE_CHECKING:  # avoids importing settings at runtime
    from ..config import Settings

log = logging.getLogger(__name__)

# Deterministic clues, one bank per digit per language. Every line resolves by
# counting a set whose size is fixed by common knowledge, and none contains a
# numeral or the digit's own name in either language — they pass the same leak
# scan the model's output has to pass. These are the safety net: any clue that
# leaks or fails the solver round-trip is replaced by one of these, which is
# *known* to be correct.
DIGIT_CLUES: dict[str, dict[int, tuple[str, ...]]] = {
    "en": {
        0: (
            "Count the windows in the sealed cellar; the walls are unbroken.",
            "Count the coins left in the offering box after the fire; it is bare.",
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
            "Count the walls of a cell in the honeycomb.",
            "Count the strings on the pawned guitar.",
        ),
        7: (
            "Count the days the almanac gives a week.",
            "Count the colours the rain leaves across the sky.",
        ),
        8: (
            "Count the legs of the spider on the sill.",
            "Count the arms of the octopus on the cannery's sign.",
        ),
        9: (
            "Count the lives a cat is said to spend.",
            "Count the months a child waits to be born.",
        ),
    },
    "ru": {
        0: (
            "Сосчитайте окна в замурованном подвале: стена цела.",
            "Сосчитайте монеты в ящике для пожертвований: ящик пуст.",
        ),
        1: (
            "Сосчитайте луны над двором.",
            "Сосчитайте солнца, что восходят здесь по утрам.",
        ),
        2: (
            "Сосчитайте вёсла в руках гребца.",
            "Сосчитайте глаза на портрете над столом.",
        ),
        3: (
            "Сосчитайте ножки доильного табурета у двери.",
            "Сосчитайте стороны железного треугольника землемера.",
        ),
        4: (
            "Сосчитайте времена года, которые называет альманах.",
            "Сосчитайте колёса под почтовой каретой.",
        ),
        5: (
            "Сосчитайте пальцы в левой перчатке.",
            "Сосчитайте лучи звезды, высеченной над притолокой.",
        ),
        6: (
            "Сосчитайте стенки ячейки в пчелиных сотах.",
            "Сосчитайте струны заложенной гитары.",
        ),
        7: (
            "Сосчитайте дни, которые альманах отводит неделе.",
            "Сосчитайте цвета, что дождь оставляет в небе.",
        ),
        8: (
            "Сосчитайте ноги паука на подоконнике.",
            "Сосчитайте руки осьминога на вывеске консервной фабрики.",
        ),
        9: (
            "Сосчитайте жизни, которые молва отводит кошке.",
            "Сосчитайте месяцы, что дитя ждёт своего рождения.",
        ),
    },
}

# Flavour used when there is no API key at all, or the call fails outright.
# Index-aligned across languages so a fallback quest reads the same in both.
FALLBACK_THEMES: list[dict[str, tuple[str, str]]] = [
    {
        "en": ("a drowned observatory", "Salt has eaten the brass, but the tide still keeps time."),
        "ru": ("затонувшая обсерватория", "Соль съела латунь, но прилив всё ещё считает часы."),
    },
    {
        "en": ("a cartographer's estate", "Every map here agrees on a road that does not exist."),
        "ru": ("усадьба картографа", "Все карты здесь сходятся на дороге, которой не существует."),
    },
    {
        "en": ("the last night train", "The timetable lists a station that burned down twice."),
        "ru": ("последний ночной поезд", "В расписании значится станция, что сгорела дважды."),
    },
    {
        "en": ("a watchmaker's cellar", "Ten thousand hands, and they all disagree."),
        "ru": ("подвал часовщика", "Тысячи стрелок, и все они спорят друг с другом."),
    },
    {
        "en": ("an archive of forged letters", "The signatures are perfect. The people never were."),
        "ru": ("архив поддельных писем", "Подписи безупречны. Люди — никогда."),
    },
]


@dataclass(slots=True)
class Quest:
    """One generated puzzle: the answer, plus framing and clues per language.

    ``theme`` and ``riddle`` map language -> text; ``clues`` maps language ->
    one clue per dial. Both languages describe the *same* combination.
    """

    code: list[int]
    theme: dict[str, str] = field(default_factory=dict)
    riddle: dict[str, str] = field(default_factory=dict)
    clues: dict[str, list[str]] = field(default_factory=dict)

    def theme_in(self, lang: str | None) -> str:
        return self.theme.get(normalize(lang)) or self.theme.get(DEFAULT_LANG, "")


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


def local_clue(digit: int, lang: str = DEFAULT_LANG, avoid: str | None = None) -> str:
    """A known-correct clue for one digit, ideally not one already in use."""
    bank = DIGIT_CLUES[normalize(lang)][digit]
    options = [c for c in bank if c != avoid] or list(bank)
    return random.choice(options)


# --------------------------------------------------------------------------- #
# Leak scanning
# --------------------------------------------------------------------------- #

NUMERAL_RE = re.compile(r"\d")

# Number names per digit. Russian inflects, so these are matched by stem with
# the case endings spelled out — "семь", "семи", "седьмой", "седьмая" all give
# the answer away as plainly as the numeral would.
_CARDINALS: dict[int, tuple[str, ...]] = {
    0: ("zero", "nought", "naught", "none", "nil",
        "ноль", "нуль", "нуля", "нулю", "нулём", "нулем"),
    1: ("one", "один", "одна", "одно", "одну", "одного", "одной", "одним",
        "первый", "первая", "первое", "первого", "первых"),
    2: ("two", "два", "две", "двух", "двум", "двумя",
        "второй", "вторая", "второе", "второго"),
    3: ("three", "third", "три", "трёх", "трех", "трём", "трем", "тремя",
        "третий", "третья", "третье", "третьего"),
    4: ("four", "четыре", "четырёх", "четырех", "четырём", "четырем", "четырьмя",
        "четвёртый", "четвертый", "четвёртая", "четвертая"),
    5: ("five", "fifth", "пять", "пяти", "пятью",
        "пятый", "пятая", "пятое", "пятого"),
    6: ("six", "шесть", "шести", "шестью",
        "шестой", "шестая", "шестое"),
    7: ("seven", "семь", "семи", "семью",
        "седьмой", "седьмая", "седьмое"),
    8: ("eight", "eighth", "восемь", "восьми", "восемью", "восьмью",
        "восьмой", "восьмая"),
    9: ("nine", "ninth", "девять", "девяти", "девятью",
        "девятый", "девятая", "девятое"),
}
# English suffixes turn cardinals into ordinals and teens, so "the seventh
# lamp" is caught as readily as "seven lamps". Russian forms are listed in full
# above, since its endings do not compose that way.
_WORD_RE = {
    digit: re.compile(r"\b(" + "|".join(words) + r")(th|ty|teen|s)?\b", re.IGNORECASE)
    for digit, words in _CARDINALS.items()
}


def leaks_digit(text: str, digit: int) -> bool:
    """True if ``text`` gives its digit away outright.

    Two ways that happens, both of which ruin the puzzle:

    * **any numeral at all** — `7`, `"7"`, `07`. A clue has no legitimate use
      for a digit character, so this is checked regardless of which digit.
    * **the digit's own name, in either language** — "seven lamps", "the
      seventh lamp", "семь ламп", "седьмая лампа". Counting devices like "a
      pair of gloves" are the intended mechanism and are left alone; only
      naming the answer counts as a leak.

    Both languages are always scanned. An English clue cannot contain Russian
    words and vice versa, so there is nothing to gain from asking the caller to
    track which language a string is in.
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


def sanitize_clues(
    clues: list[str], code: list[int], lang: str = DEFAULT_LANG
) -> tuple[list[str], list[int]]:
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
            repaired.append(local_clue(digit, lang))
            replaced.append(index)
            continue

        if leaks_digit(clue, digit):
            # Try cleaning first: a numeral can often just be deleted. If the
            # digit's *name* is in there, the sentence is built around saying
            # it and there is nothing to salvage.
            cleaned = strip_numerals(clue)
            if cleaned and not leaks_digit(cleaned, digit):
                log.info("clue %d (%s) leaked a numeral; cleaned it", index, lang)
                repaired.append(cleaned)
                continue
            log.info("clue %d (%s) named its digit; replaced locally", index, lang)
            repaired.append(local_clue(digit, lang))
            replaced.append(index)
            continue

        repaired.append(clue)

    return repaired, replaced


def _clean_framing(riddle: str, code: list[int], spare: str) -> str:
    """Scrub the framing line, which must not give the game away either."""
    if NUMERAL_RE.search(riddle):
        riddle = strip_numerals(riddle)
    if any(_WORD_RE[digit].search(riddle) for digit in set(code)):
        log.info("framing riddle named a digit; using local flavour instead")
        return spare
    return riddle


def coerce_quest(raw: object, code: list[int]) -> Quest:
    """Turn whatever the model returned into a Quest we can actually play.

    ``code`` is passed in, not read out: the combination was decided before the
    model was ever called. Structured output makes the *shape* reliable, never
    the *values*, so every field is repaired rather than trusted — in every
    language independently, since the model can get one right and the other
    wrong.
    """
    data = raw if isinstance(raw, dict) else {}
    spare = random.choice(FALLBACK_THEMES)

    quest = Quest(code=list(code))
    for lang in LANGS:
        spare_theme, spare_riddle = spare[lang]

        theme = " ".join(str(data.get(f"theme_{lang}") or "").split()) or spare_theme
        riddle = " ".join(str(data.get(f"riddle_{lang}") or "").split()) or spare_riddle

        raw_clues = data.get(f"clues_{lang}")
        clues, replaced = sanitize_clues(
            list(raw_clues) if isinstance(raw_clues, list) else [], code, lang
        )
        if replaced:
            log.warning(
                "replaced %d of %d %s clues after leak scan",
                len(replaced), len(code), lang,
            )

        quest.theme[lang] = theme[:120]
        quest.riddle[lang] = _clean_framing(riddle, code, spare_riddle)[:400]
        quest.clues[lang] = clues

    return quest


def local_quest(code: list[int]) -> Quest:
    """A complete, guaranteed-solvable quest in both languages, no model."""
    spare = random.choice(FALLBACK_THEMES)
    quest = Quest(code=list(code))
    for lang in LANGS:
        theme, riddle = spare[lang]
        quest.theme[lang] = theme
        quest.riddle[lang] = riddle
        quest.clues[lang] = [local_clue(d, lang) for d in code]
    return quest


class StaticQuestProvider(QuestProvider):
    """No API key, no network: local code, local clues, canned flavour.

    The code is still random per vault and the clues still resolve, so the game
    is fully playable offline in both languages — just less atmospheric.
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
