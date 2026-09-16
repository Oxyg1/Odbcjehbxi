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
    # Round-trip every generated clue through a solver that has not seen the
    # code, and replace any that do not resolve. Costs one extra fast call per
    # vault; turn it off if you would rather have the second back.
    quest_verify: bool = Field(default=True, alias="QUEST_VERIFY")

    # --- Language ---
    # Used before a player has chosen, and for anyone who never does.
    default_lang: str = Field(default="en", alias="DEFAULT_LANG")
    # Skip the language picker and start every vault in DEFAULT_LANG.
    ask_language: bool = Field(default=True, alias="ASK_LANGUAGE")

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
    # Optional override. Left empty, the offline prize comes from the
    # translation table and follows the player's language.
    static_reward: str | None = Field(default=None, alias="STATIC_REWARD")

    @field_validator("secret_code")
    @classmethod
    def _digits_only(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if not v.isdigit():
            raise ValueError("SECRET_CODE must contain digits only")
        return v

    @field_validator("default_lang")
    @classmethod
    def _known_lang(cls, v: str) -> str:
        from .i18n import LANGS

        if v not in LANGS:
            raise ValueError(f"DEFAULT_LANG must be one of {', '.join(LANGS)}")
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
