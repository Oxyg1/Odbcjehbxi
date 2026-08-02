from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tgmarket.config import (  # noqa: E402
    AppConfig,
    BudgetConfig,
    BuyConfig,
    FilterConfig,
    NotifyConfig,
    RuntimeConfig,
    TelegramConfig,
)
from tgmarket.models import CATALOG, RESALE, GiftLot  # noqa: E402


def make_lot(**kwargs) -> GiftLot:
    defaults = dict(gift_id=1, kind=CATALOG, price=50, title="Star", limited=False)
    defaults.update(kwargs)
    return GiftLot(**defaults)


def make_resale_lot(**kwargs) -> GiftLot:
    defaults = dict(gift_id=1, kind=RESALE, price=50, title="Star", slug="star-1", num=1, limited=True)
    defaults.update(kwargs)
    return GiftLot(**defaults)


@pytest.fixture
def lot_factory():
    return make_lot


@pytest.fixture
def resale_lot_factory():
    return make_resale_lot


@pytest.fixture
def app_config(tmp_path) -> AppConfig:
    return AppConfig(
        telegram=TelegramConfig(api_id=1, api_hash="hash", session_dir=str(tmp_path / "sessions")),
        filters=FilterConfig(max_price=100),
        buy=BuyConfig(
            dry_run=True,
            recipients=["me"],
            budget=BudgetConfig(max_stars_total=1000, max_stars_per_cycle=200,
                                max_purchases_per_cycle=2, max_purchases_per_gift=1),
        ),
        runtime=RuntimeConfig(poll_interval=15, poll_jitter=0, state_path=str(tmp_path / "state.json")),
        notify=NotifyConfig(enabled=False),
    )


class FakeSleep:
    """Records sleeps instead of performing them."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)

    @property
    def total(self) -> float:
        return sum(self.calls)


@pytest.fixture
def fake_sleep() -> FakeSleep:
    return FakeSleep()
