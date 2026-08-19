import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _parse_proxies(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


@dataclass(frozen=True)
class Config:
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    bot_api_proxy: str | None = field(default_factory=lambda: os.getenv("BOT_API_PROXY") or None)
    proxies: list[str] = field(default_factory=lambda: _parse_proxies(os.getenv("PROXIES")))
    database_path: str = field(default_factory=lambda: os.getenv("DATABASE_PATH", "data/usernames.db"))
    log_file: str = field(default_factory=lambda: os.getenv("LOG_FILE", "data/bot.log"))
    rate_limit_per_second: float = field(
        default_factory=lambda: float(os.getenv("RATE_LIMIT_PER_SECOND", "5"))
    )
    cache_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv("CACHE_TTL_SECONDS", "300"))
    )
    request_timeout_seconds: float = 10.0
    max_retries: int = 3


config = Config()


def validate_config() -> None:
    if not config.bot_token:
        raise RuntimeError(
            "BOT_TOKEN is not set. Copy .env.example to .env and fill in your bot token from @BotFather."
        )
