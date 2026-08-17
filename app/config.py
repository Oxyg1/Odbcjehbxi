"""Загрузка конфигурации из переменных окружения / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

_TRUE = {"1", "true", "yes", "y", "on", "да"}
_FALSE = {"0", "false", "no", "n", "off", "нет"}


def env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(f"{key}: ожидалось true/false, получено {raw!r}")


def env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:  # pragma: no cover - защита от опечаток в .env
        raise ValueError(f"{key}: ожидалось целое число, получено {raw!r}") from exc


def env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw.strip())
    except ValueError as exc:  # pragma: no cover
        raise ValueError(f"{key}: ожидалось число, получено {raw!r}") from exc


def env_path(key: str, default: str) -> Path:
    raw = (os.getenv(key) or "").strip() or default
    path = Path(raw)
    return path if path.is_absolute() else BASE_DIR / path


@dataclass(frozen=True)
class NotificationDefaults:
    """Стартовые значения пользовательских настроек (меняются через /settings)."""

    notify_edits: bool = True
    notify_deletes: bool = True
    include_own: bool = False
    backup_media: bool = True
    silent: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {
            "notify_edits": self.notify_edits,
            "notify_deletes": self.notify_deletes,
            "include_own": self.include_own,
            "backup_media": self.backup_media,
            "silent": self.silent,
        }


@dataclass(frozen=True)
class Config:
    bot_token: str
    db_path: Path
    media_dir: Path
    timezone: str
    retention_days: int
    delete_debounce: float
    chat_delete_threshold: int
    preview_limit: int
    max_messages_in_report: int
    max_media_items: int
    max_media_bytes: int
    log_level: str
    defaults: NotificationDefaults

    @classmethod
    def load(cls, env_file: Path | str | None = None) -> "Config":
        load_dotenv(env_file or BASE_DIR / ".env", override=False)

        token = (os.getenv("BOT_TOKEN") or "").strip()
        if not token:
            raise RuntimeError(
                "Не задан BOT_TOKEN. Скопируйте .env.example в .env и впишите токен от @BotFather."
            )

        return cls(
            bot_token=token,
            db_path=env_path("DB_PATH", "data/tracker.db"),
            media_dir=env_path("MEDIA_DIR", "data/media"),
            timezone=(os.getenv("TIMEZONE") or "Europe/Moscow").strip(),
            retention_days=env_int("RETENTION_DAYS", 30),
            delete_debounce=env_float("DELETE_DEBOUNCE", 2.0),
            chat_delete_threshold=env_int("CHAT_DELETE_THRESHOLD", 5),
            preview_limit=env_int("PREVIEW_LIMIT", 700),
            max_messages_in_report=env_int("MAX_MESSAGES_IN_REPORT", 25),
            max_media_items=env_int("MAX_MEDIA_ITEMS", 10),
            max_media_bytes=env_int("MAX_MEDIA_MB", 20) * 1024 * 1024,
            log_level=(os.getenv("LOG_LEVEL") or "INFO").strip().upper(),
            defaults=NotificationDefaults(
                notify_edits=env_bool("NOTIFY_EDITS", True),
                notify_deletes=env_bool("NOTIFY_DELETES", True),
                include_own=env_bool("INCLUDE_OWN", False),
                backup_media=env_bool("BACKUP_MEDIA", True),
                silent=env_bool("SILENT_NOTIFICATIONS", False),
            ),
        )
