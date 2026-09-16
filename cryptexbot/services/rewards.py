"""What the vault reveals once it opens.

Every provider exposes the same streaming interface::

    async for partial in provider.stream(ctx):
        ...  # `partial` is the full text so far, not a delta

A static provider yields exactly once; the Gemini provider yields as chunks
land, which is what drives the typewriter effect in ``handlers/vault.py``.
Because the renderer only ever sees this interface, swapping models — or
dropping back to static text — is a config change, not a refactor.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..i18n import DEFAULT_LANG, t
from typing import AsyncIterator

if TYPE_CHECKING:  # avoids importing settings at runtime
    from ..config import Settings

log = logging.getLogger(__name__)


@dataclass(slots=True)
class RewardContext:
    """Everything a provider might want to personalise the reveal."""

    user_id: int
    user_name: str
    chat_id: int
    message_id: int
    code: str
    attempts: int
    # Carried over from the quest, so the reveal matches the vault the player
    # actually cracked rather than a generic safe.
    theme: str = ""
    riddle: str = ""
    # The language the player is reading in. The reveal is generated once, in
    # this language, at the moment the vault opens.
    lang: str = DEFAULT_LANG


class RewardProvider(ABC):
    @abstractmethod
    def stream(self, ctx: RewardContext) -> AsyncIterator[str]:
        """Yield the reward text, progressively. Each item is the full text."""


class StaticRewardProvider(RewardProvider):
    """The offline prize: one fixed string per language, yielded in one piece.

    ``override`` is the optional STATIC_REWARD from the environment. When it is
    unset the text comes from the translation table, so the fallback speaks the
    player's language too.
    """

    def __init__(self, override: str | None = None) -> None:
        self._override = override or None

    async def stream(self, ctx: RewardContext) -> AsyncIterator[str]:
        template = self._override or t(ctx.lang, "static_reward")
        yield template.format(
            user_name=ctx.user_name,
            code=ctx.code,
            attempts=ctx.attempts,
            theme=ctx.theme or "the vault",
        )


class FallbackRewardProvider(RewardProvider):
    """Wraps a provider so a failed generation never eats the player's prize."""

    def __init__(self, primary: RewardProvider, fallback: RewardProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    async def stream(self, ctx: RewardContext) -> AsyncIterator[str]:
        emitted = False
        try:
            async for partial in self._primary.stream(ctx):
                emitted = True
                yield partial
        except Exception:  # noqa: BLE001 - provider failures are never fatal
            log.exception("reward provider failed; falling back")
            if not emitted:
                async for partial in self._fallback.stream(ctx):
                    yield partial


def build_reward_provider(settings: "Settings") -> RewardProvider:
    """Gemini when a key is configured, static otherwise — always wrapped.

    The fallback is not defensive padding: a player who cracked the code has
    earned a prize, and a 500 from the API is not their problem.
    """
    static = StaticRewardProvider(settings.static_reward)
    if not settings.gemini_api_key:
        return static

    from .gemini import GeminiRewardProvider

    return FallbackRewardProvider(
        GeminiRewardProvider(settings.gemini_api_key, settings.gemini_model), static
    )
