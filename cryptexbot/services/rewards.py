"""What the vault reveals once it opens.

The swap point for "static text -> LLM call" lives here and nowhere else.
Every provider exposes the same streaming interface::

    async for partial in provider.stream(ctx):
        ...  # `partial` is the full text so far, not a delta

A static provider yields exactly once; an LLM provider yields as tokens land.
The handler that renders the reward is written against the streaming shape, so
turning on real streaming later is a config change, not a refactor.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

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


class RewardProvider(ABC):
    @abstractmethod
    def stream(self, ctx: RewardContext) -> AsyncIterator[str]:
        """Yield the reward text, progressively. Each item is the full text."""


class StaticRewardProvider(RewardProvider):
    """Ships the boilerplate: one fixed prize string, yielded in one piece."""

    def __init__(self, text: str) -> None:
        self._text = text

    async def stream(self, ctx: RewardContext) -> AsyncIterator[str]:
        yield self._text.format(
            user_name=ctx.user_name, code=ctx.code, attempts=ctx.attempts
        )


class LLMRewardProvider(RewardProvider):
    """Generates the reveal with Claude, streaming as tokens arrive.

    Kept deliberately thin — the only contract that matters is that it yields
    the growing text. Telegram rate-limits ``editMessageCaption``, so the
    renderer (see ``handlers/vault.py``) throttles how often it pushes an
    update; do not throttle here.
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-5") -> None:
        from anthropic import AsyncAnthropic  # lazy: optional dependency

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    def _prompt(self, ctx: RewardContext) -> str:
        return (
            f"{ctx.user_name} just cracked a 3-digit vault in a Telegram puzzle "
            f"game, on attempt {ctx.attempts}, with the code {ctx.code}. "
            "Write the reveal that greets them inside the vault: 2-3 sentences, "
            "noir heist tone, second person, no emoji, no preamble."
        )

    async def stream(self, ctx: RewardContext) -> AsyncIterator[str]:
        buffer = ""
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=300,
            messages=[{"role": "user", "content": self._prompt(ctx)}],
        ) as stream:
            async for delta in stream.text_stream:
                buffer += delta
                yield buffer


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


def build_reward_provider(
    kind: str, static_text: str, api_key: str | None, model: str
) -> RewardProvider:
    static = StaticRewardProvider(static_text)
    if kind == "llm":
        if not api_key:
            log.warning("REWARD_PROVIDER=llm but no ANTHROPIC_API_KEY; using static")
            return static
        return FallbackRewardProvider(LLMRewardProvider(api_key, model), static)
    return static
