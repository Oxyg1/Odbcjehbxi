"""Runtime configuration, loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    bot_token: str = Field(alias="BOT_TOKEN")

    secret_code: str = Field(default="732", alias="SECRET_CODE")
    dial_count: int = Field(default=3, alias="DIAL_COUNT", ge=1, le=8)

    state_backend: Literal["memory", "redis"] = Field(
        default="memory", alias="STATE_BACKEND"
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    state_ttl: int = Field(default=86_400, alias="STATE_TTL")

    reward_provider: Literal["static", "llm"] = Field(
        default="static", alias="REWARD_PROVIDER"
    )
    static_reward: str = Field(
        default="You cracked it. Promo code: CRYPTEX-732-OPEN", alias="STATIC_REWARD"
    )
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    reward_model: str = Field(default="claude-sonnet-5", alias="REWARD_MODEL")

    @field_validator("secret_code")
    @classmethod
    def _digits_only(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("SECRET_CODE must contain digits only")
        return v

    @property
    def secret_dials(self) -> tuple[int, ...]:
        return tuple(int(ch) for ch in self.secret_code)

    def model_post_init(self, __context) -> None:  # noqa: D105
        if len(self.secret_code) != self.dial_count:
            raise ValueError(
                f"SECRET_CODE has {len(self.secret_code)} digits "
                f"but DIAL_COUNT is {self.dial_count}"
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
