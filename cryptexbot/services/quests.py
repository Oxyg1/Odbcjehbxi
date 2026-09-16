"""The puzzle itself: a combination, a theme, and a riddle to set the mood.

A quest is generated per vault, so the bot is infinitely replayable and the
secret code exists nowhere in the source. Providers are interchangeable:
Gemini in production, a local generator when there is no API key and in tests.
"""

from __future__ import annotations

import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoids importing settings at runtime
    from ..config import Settings

log = logging.getLogger(__name__)

# Fallback flavour, used when no LLM is configured or the call fails. Keeping
# several keeps even the offline mode from feeling canned.
FALLBACK_THEMES = [
    ("a drowned observatory", "Salt has eaten the brass, but the tide still keeps time."),
    ("a cartographer's estate", "Every map here agrees on one road, and it does not exist."),
    ("the last night train", "The timetable lists a station that burned down twice."),
    ("a watchmaker's cellar", "Ten thousand hands, and not one of them agrees."),
    ("an archive of forged letters", "The signatures are perfect. The people never were."),
]


@dataclass(slots=True)
class Quest:
    """One generated puzzle."""

    code: list[int]
    theme: str
    riddle: str


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
    return [random.randint(0, 9) for _ in range(dial_count)]


def coerce_quest(raw: object, dial_count: int) -> Quest:
    """Turn whatever the model returned into a Quest we can actually play.

    Structured output makes the *shape* reliable, not the *values*: a model can
    still hand back four digits, a 12, or a stray string. Repairing beats
    rejecting — the player gets a vault either way, and a bad digit would
    otherwise make the safe unopenable.
    """
    data = raw if isinstance(raw, dict) else {}

    digits: list[int] = []
    for value in data.get("code") or []:
        try:
            digits.append(int(value) % 10)
        except (TypeError, ValueError):
            continue
    if len(digits) != dial_count:
        log.warning("model returned %d digits, wanted %d; repairing", len(digits), dial_count)
        digits = (digits + random_code(dial_count))[:dial_count]

    theme = str(data.get("theme") or "").strip()
    riddle = str(data.get("riddle") or "").strip()
    if not theme or not riddle:
        spare_theme, spare_riddle = random.choice(FALLBACK_THEMES)
        theme = theme or spare_theme
        riddle = riddle or spare_riddle

    return Quest(code=digits, theme=theme[:120], riddle=riddle[:400])


class StaticQuestProvider(QuestProvider):
    """No API key, no network: a locally random code with canned flavour.

    The code is still random per vault, so the game stays replayable offline.
    """

    def __init__(self, fixed_code: str | None = None) -> None:
        self._fixed = [int(c) for c in fixed_code] if fixed_code else None

    async def generate(self, ctx: QuestContext) -> Quest:
        theme, riddle = random.choice(FALLBACK_THEMES)
        code = self._fixed if self._fixed else random_code(ctx.dial_count)
        return Quest(code=list(code), theme=theme, riddle=riddle)


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
        log.warning("no GEMINI_API_KEY: vaults will use locally generated codes")
        return local

    from .gemini import GeminiQuestProvider

    return FallbackQuestProvider(
        GeminiQuestProvider(settings.gemini_api_key, settings.gemini_model), local
    )
