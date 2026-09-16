"""Runtime configuration, loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    bot_token: str = Field(alias="BOT_TOKEN")

    # --- Gemini ---
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")

    # --- Puzzle ---
    dial_count: int = Field(default=3, alias="DIAL_COUNT", ge=1, le=8)
    # Normally unset: every vault's combination is generated per game. Set it
    # only to pin a code for debugging or a demo.
    secret_code: str | None = Field(default=None, alias="SECRET_CODE")

    # --- State backend ---
    state_backend: str = Field(default="memory", alias="STATE_BACKEND")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    state_ttl: int = Field(default=86_400, alias="STATE_TTL")

    # --- Reward fallback (used when Gemini is unavailable) ---
    static_reward: str = Field(
        default=(
            "The door gives, and {theme} exhales dust into the light. "
            "Whatever was worth guarding is still here, and it is yours."
        ),
        alias="STATIC_REWARD",
    )

    @field_validator("secret_code")
    @classmethod
    def _digits_only(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if not v.isdigit():
            raise ValueError("SECRET_CODE must contain digits only")
        return v

    @field_validator("state_backend")
    @classmethod
    def _known_backend(cls, v: str) -> str:
        if v not in {"memory", "redis"}:
            raise ValueError("STATE_BACKEND must be 'memory' or 'redis'")
        return v

    def model_post_init(self, __context) -> None:  # noqa: D105
        if self.secret_code and len(self.secret_code) != self.dial_count:
            raise ValueError(
                f"SECRET_CODE has {len(self.secret_code)} digits "
                f"but DIAL_COUNT is {self.dial_count}"
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
