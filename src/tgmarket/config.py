"""Configuration loading and validation.

Secrets (``API_ID``/``API_HASH``/session/notification token) come from the
environment only; everything else lives in a YAML file.  That split keeps
credentials out of the repository and out of the config file that people tend
to paste into issue reports.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

try:  # PyYAML is a hard requirement, but keep the import error actionable.
    import yaml
except ImportError as exc:  # pragma: no cover - environment problem, not logic
    raise SystemExit("PyYAML is required: pip install -r requirements.txt") from exc


class ConfigError(ValueError):
    """Raised when the configuration is missing or internally inconsistent."""


#: Telegram punishes aggressive polling with FLOOD_WAIT; refuse to go below
#: this no matter what the config file says.
MIN_POLL_INTERVAL = 15.0
DEFAULT_POLL_INTERVAL = 60.0


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name, default)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def load_dotenv(path: str | os.PathLike[str] = ".env") -> None:
    """Populate ``os.environ`` from a ``.env`` file without overriding it.

    A deliberately tiny reader so the project needs no extra dependency; real
    shells and Docker ``env_file`` directives keep working unchanged.
    """
    file = Path(path)
    if not file.is_file():
        return
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class TelegramConfig:
    """Credentials and transport for the user account."""

    api_id: int = 0
    api_hash: str = ""
    session_name: str = "tgmarket"
    session_dir: str = "sessions"
    session_string: Optional[str] = None
    phone: Optional[str] = None
    password: Optional[str] = None
    proxy: Optional[str] = None
    device_model: str = "tgmarket"
    app_version: str = "1.0"

    @property
    def session_path(self) -> str:
        return str(Path(self.session_dir) / self.session_name)

    def validate(self) -> None:
        if not self.api_id or not self.api_hash:
            raise ConfigError(
                "TG_API_ID / TG_API_HASH are not set. Obtain them from "
                "https://my.telegram.org and put them in your .env file."
            )


@dataclass
class FilterConfig:
    """Rules that decide whether a lot is worth buying."""

    max_price: Optional[int] = None
    min_price: int = 0
    gift_ids: list[int] = field(default_factory=list)
    exclude_gift_ids: list[int] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    limited_only: bool = False
    unlimited_only: bool = False
    skip_sold_out: bool = True
    skip_premium_required: bool = True
    min_supply: Optional[int] = None
    max_supply: Optional[int] = None
    min_available: int = 1
    include_resale: bool = False
    resale_gift_ids: list[int] = field(default_factory=list)
    resale_page_limit: int = 50
    resale_max_pages: int = 1

    def validate(self) -> None:
        if self.max_price is not None and self.max_price < self.min_price:
            raise ConfigError("filters.max_price must not be lower than filters.min_price")
        if self.limited_only and self.unlimited_only:
            raise ConfigError("filters.limited_only and filters.unlimited_only are mutually exclusive")
        if self.include_resale and not (self.resale_gift_ids or self.gift_ids):
            raise ConfigError(
                "filters.include_resale needs filters.resale_gift_ids (or filters.gift_ids): "
                "payments.getResaleStarGifts is queried per gift id"
            )
        if self.resale_page_limit < 1 or self.resale_page_limit > 100:
            raise ConfigError("filters.resale_page_limit must be between 1 and 100")


@dataclass
class BudgetConfig:
    """Hard spending ceilings.

    Purchases are irreversible, so every limit defaults to something small and
    the bot stops rather than guessing when a limit would be exceeded.
    """

    max_stars_per_gift: Optional[int] = None
    max_stars_per_cycle: int = 0
    max_stars_total: int = 0
    max_purchases_per_cycle: int = 1
    max_purchases_per_gift: int = 1
    min_balance_reserve: int = 0

    def validate(self) -> None:
        for name in ("max_stars_per_cycle", "max_stars_total", "max_purchases_per_cycle",
                     "max_purchases_per_gift", "min_balance_reserve"):
            if getattr(self, name) < 0:
                raise ConfigError(f"budget.{name} must not be negative")
        if self.max_stars_total and self.max_stars_per_cycle > self.max_stars_total:
            raise ConfigError("budget.max_stars_per_cycle exceeds budget.max_stars_total")


@dataclass
class BuyConfig:
    """What to do when a lot matches."""

    dry_run: bool = True
    recipients: list[str] = field(default_factory=lambda: ["me"])
    hide_sender_name: bool = False
    include_upgrade: bool = False
    message: Optional[str] = None
    budget: BudgetConfig = field(default_factory=BudgetConfig)

    def validate(self) -> None:
        if not self.recipients:
            raise ConfigError("buy.recipients must list at least one recipient ('me' for yourself)")
        self.budget.validate()
        if not self.dry_run and not (self.budget.max_stars_total or self.budget.max_stars_per_cycle):
            raise ConfigError(
                "live mode requires a spending ceiling: set budget.max_stars_total "
                "and/or budget.max_stars_per_cycle before disabling dry_run"
            )


@dataclass
class RuntimeConfig:
    """Loop timing, persistence and API pacing."""

    poll_interval: float = DEFAULT_POLL_INTERVAL
    poll_jitter: float = 5.0
    state_path: str = "data/state.json"
    log_level: str = "INFO"
    log_file: Optional[str] = None
    max_flood_wait: int = 600
    min_api_interval: float = 0.75
    max_retries: int = 3

    def validate(self) -> None:
        if self.poll_interval < MIN_POLL_INTERVAL:
            raise ConfigError(
                f"runtime.poll_interval must be >= {MIN_POLL_INTERVAL:g}s. "
                "Polling faster mainly buys FLOOD_WAIT errors, not gifts."
            )
        if self.poll_jitter < 0:
            raise ConfigError("runtime.poll_jitter must not be negative")
        if self.min_api_interval < 0:
            raise ConfigError("runtime.min_api_interval must not be negative")
        if self.max_retries < 0:
            raise ConfigError("runtime.max_retries must not be negative")


@dataclass
class NotifyConfig:
    """Out-of-band reporting through a regular Bot API bot."""

    enabled: bool = False
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    notify_on_match: bool = True
    notify_on_error: bool = True
    notify_on_start: bool = True

    def validate(self) -> None:
        if self.enabled and not (self.bot_token and self.chat_id):
            raise ConfigError(
                "notify.enabled requires NOTIFY_BOT_TOKEN and NOTIFY_CHAT_ID in the environment"
            )


@dataclass
class AppConfig:
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    buy: BuyConfig = field(default_factory=BuyConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)

    def validate(self) -> None:
        self.telegram.validate()
        self.filters.validate()
        self.buy.validate()
        self.runtime.validate()
        self.notify.validate()

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None, *, use_dotenv: bool = True) -> "AppConfig":
        """Build a config from ``path`` (YAML) layered under environment secrets."""
        if use_dotenv:
            load_dotenv(_env("TGMARKET_DOTENV", ".env"))

        data: dict[str, Any] = {}
        if path is not None:
            file = Path(path)
            if not file.is_file():
                raise ConfigError(f"config file not found: {file}")
            loaded = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
            if not isinstance(loaded, dict):
                raise ConfigError(f"{file} must contain a YAML mapping at the top level")
            data = loaded

        cfg = cls(
            telegram=_build(TelegramConfig, data.get("telegram")),
            filters=_build(FilterConfig, data.get("filters")),
            buy=_build_buy(data.get("buy")),
            runtime=_build(RuntimeConfig, data.get("runtime")),
            notify=_build(NotifyConfig, data.get("notify")),
        )
        cfg.apply_env()
        cfg.validate()
        return cfg

    def apply_env(self) -> None:
        """Overlay environment variables; they always win over the YAML file."""
        tg = self.telegram
        if (api_id := _env("TG_API_ID")) is not None:
            try:
                tg.api_id = int(api_id)
            except ValueError as exc:
                raise ConfigError("TG_API_ID must be an integer") from exc
        tg.api_hash = _env("TG_API_HASH") or tg.api_hash
        tg.session_name = _env("TG_SESSION_NAME") or tg.session_name
        tg.session_dir = _env("TG_SESSION_DIR") or tg.session_dir
        tg.session_string = _env("TG_SESSION_STRING") or tg.session_string
        tg.phone = _env("TG_PHONE") or tg.phone
        tg.password = _env("TG_PASSWORD") or tg.password
        tg.proxy = _env("TG_PROXY") or tg.proxy

        self.buy.dry_run = _env_bool("DRY_RUN", self.buy.dry_run)

        self.runtime.log_level = _env("LOG_LEVEL") or self.runtime.log_level
        self.runtime.state_path = _env("STATE_PATH") or self.runtime.state_path

        token = _env("NOTIFY_BOT_TOKEN")
        chat = _env("NOTIFY_CHAT_ID")
        self.notify.bot_token = token or self.notify.bot_token
        self.notify.chat_id = chat or self.notify.chat_id
        if token and chat and _env("NOTIFY_ENABLED") is None:
            self.notify.enabled = True
        else:
            self.notify.enabled = _env_bool("NOTIFY_ENABLED", self.notify.enabled)


def _build(cls: type, raw: Any) -> Any:
    """Instantiate a config dataclass from a mapping, rejecting unknown keys."""
    if raw is None:
        return cls()
    if not isinstance(raw, dict):
        raise ConfigError(f"expected a mapping for the {cls.__name__} section, got {type(raw).__name__}")
    known = {f.name for f in fields(cls)}
    unknown = set(raw) - known
    if unknown:
        raise ConfigError(f"unknown option(s) in {cls.__name__}: {', '.join(sorted(unknown))}")
    return cls(**{k: v for k, v in raw.items() if k in known})


def _build_buy(raw: Any) -> BuyConfig:
    if raw is None:
        return BuyConfig()
    if not isinstance(raw, dict):
        raise ConfigError("expected a mapping for the buy section")
    raw = dict(raw)
    budget = _build(BudgetConfig, raw.pop("budget", None))
    cfg = _build(BuyConfig, raw)
    cfg.budget = budget
    return cfg
