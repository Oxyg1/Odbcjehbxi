from __future__ import annotations

import pytest

from tgmarket.filters import LotFilter
from tgmarket.market import UnsupportedApi
from tgmarket.models import GiftLot, PurchaseResult
from tgmarket.notify import NullNotifier
from tgmarket.purchase import Budget
from tgmarket.ratelimit import FloodWaitTooLong
from tgmarket.runner import MAX_CONSECUTIVE_FAILURES, Sniper
from tgmarket.state import State


class FakeMarket:
    def __init__(self, catalog=(), resale=None, balance=10_000):
        self._catalog = list(catalog)
        self._resale = resale or {}
        self._balance = balance
        self.catalog_calls = 0
        self.resale_calls: list[int] = []
        self.balance_calls = 0

    async def catalog(self):
        self.catalog_calls += 1
        value = self._catalog[0] if self.catalog_calls == 1 else self._catalog[-1]
        if isinstance(value, Exception):
            raise value
        return list(value)

    async def resale(self, gift_id, *, limit=50, max_pages=1):
        self.resale_calls.append(gift_id)
        value = self._resale.get(gift_id, [])
        if isinstance(value, Exception):
            raise value
        return list(value)

    async def balance(self):
        self.balance_calls += 1
        if isinstance(self._balance, Exception):
            raise self._balance
        return self._balance


class FakePurchaser:
    def __init__(self, dry_run=True, outcome=True, error=None):
        self.dry_run = dry_run
        self.outcome = outcome
        self.error = error
        self.calls: list[tuple[GiftLot, str]] = []

    async def buy(self, lot, peer, recipient, *, max_price=None):
        self.calls.append((lot, recipient))
        return PurchaseResult(lot=lot, recipient=recipient, ok=self.outcome,
                              dry_run=self.dry_run, price=lot.price, error=self.error)


class FakeClient:
    async def get_input_entity(self, name):
        if name == "@ghost":
            raise ValueError("No user has @ghost as username")
        return f"peer:{name}"


class RecordingNotifier(NullNotifier):
    def __init__(self):
        super().__init__()
        self.messages: list[tuple[str, str]] = []

    async def send(self, text, *, level="info"):
        self.messages.append((level, text))
        return True


def build_sniper(app_config, *, catalog=(), resale=None, purchaser=None, balance=10_000,
                 notifier=None, buy_enabled=True, sleep=None, market=None):
    state = State(app_config.runtime.state_path, autosave=False)
    market = market or FakeMarket(catalog=catalog or [[]], resale=resale, balance=balance)
    return Sniper(
        config=app_config,
        client=FakeClient(),
        market=market,
        purchaser=purchaser or FakePurchaser(),
        lot_filter=LotFilter(app_config.filters),
        budget=Budget(app_config.buy.budget, state),
        state=state,
        notifier=notifier or NullNotifier(),
        sleep=sleep or (lambda s: _noop()),
        buy_enabled=buy_enabled,
    )


async def _noop():
    return None


# ------------------------------------------------------------------- cycle --

async def test_cycle_buys_matching_lots(app_config, lot_factory):
    lots = [lot_factory(gift_id=1, price=30), lot_factory(gift_id=2, price=5000)]
    purchaser = FakePurchaser()
    sniper = build_sniper(app_config, catalog=[lots], purchaser=purchaser)

    report = await sniper.run_once()

    assert report.scanned == 2 and report.new_lots == 2 and report.matched == 1
    assert [lot.gift_id for lot, _ in purchaser.calls] == [1]
    assert report.purchases[0].ok


async def test_watch_mode_never_buys(app_config, lot_factory):
    purchaser = FakePurchaser()
    sniper = build_sniper(app_config, catalog=[[lot_factory(price=10)]],
                          purchaser=purchaser, buy_enabled=False)

    report = await sniper.run_once()
    assert report.matched == 1 and purchaser.calls == []


async def test_lots_are_only_announced_once(app_config, lot_factory):
    lots = [lot_factory(gift_id=1, price=30)]
    notifier = RecordingNotifier()
    sniper = build_sniper(app_config, catalog=[lots, lots], notifier=notifier, buy_enabled=False)

    first = await sniper.run_once()
    second = await sniper.run_once()

    assert (first.new_lots, second.new_lots) == (1, 0)
    assert len([m for m in notifier.messages if "new matching" in m[1]]) == 1


async def test_purchase_count_limit_stops_repeat_buys(app_config, lot_factory):
    app_config.buy.budget.max_purchases_per_gift = 1
    app_config.buy.dry_run = False
    lots = [lot_factory(gift_id=1, price=30)]
    purchaser = FakePurchaser(dry_run=False)
    sniper = build_sniper(app_config, catalog=[lots, lots], purchaser=purchaser)

    await sniper.run_once()
    await sniper.run_once()
    assert len(purchaser.calls) == 1, "the same gift id must not be bought twice"


async def test_cycle_budget_caps_spending(app_config, lot_factory):
    app_config.buy.dry_run = False
    app_config.buy.budget.max_stars_per_cycle = 100
    app_config.buy.budget.max_purchases_per_cycle = 10
    app_config.buy.budget.max_purchases_per_gift = 10
    lots = [lot_factory(gift_id=i, price=60) for i in range(1, 4)]
    purchaser = FakePurchaser(dry_run=False)
    sniper = build_sniper(app_config, catalog=[lots], purchaser=purchaser)

    report = await sniper.run_once()
    assert len(purchaser.calls) == 1, "60+60 would breach the 100 star cycle cap"
    assert report.spent == 60


async def test_live_mode_checks_balance_first(app_config, lot_factory):
    app_config.buy.dry_run = False
    market = FakeMarket(catalog=[[lot_factory(price=30)]], balance=10)
    purchaser = FakePurchaser(dry_run=False)
    sniper = build_sniper(app_config, purchaser=purchaser, market=market)

    await sniper.run_once()
    assert market.balance_calls == 1
    assert purchaser.calls == [], "an unaffordable lot is never sent to the payment API"


async def test_balance_failure_blocks_buying(app_config, lot_factory):
    app_config.buy.dry_run = False
    market = FakeMarket(catalog=[[lot_factory(price=30)]], balance=RuntimeError("nope"))
    purchaser = FakePurchaser(dry_run=False)
    sniper = build_sniper(app_config, purchaser=purchaser, market=market)

    report = await sniper.run_once()
    assert purchaser.calls == [], "never buy blind"
    assert any("balance check failed" in err for err in report.errors)


async def test_dry_run_skips_the_balance_call(app_config, lot_factory):
    market = FakeMarket(catalog=[[lot_factory(price=30)]])
    sniper = build_sniper(app_config, market=market)
    await sniper.run_once()
    assert market.balance_calls == 0


async def test_balance_is_decremented_within_a_cycle(app_config, lot_factory):
    app_config.buy.dry_run = False
    app_config.buy.budget.max_purchases_per_cycle = 5
    app_config.buy.budget.max_purchases_per_gift = 5
    app_config.buy.budget.max_stars_per_cycle = 1000
    lots = [lot_factory(gift_id=1, price=60), lot_factory(gift_id=2, price=60)]
    market = FakeMarket(catalog=[lots], balance=100)
    purchaser = FakePurchaser(dry_run=False)
    sniper = build_sniper(app_config, market=market, purchaser=purchaser)

    await sniper.run_once()
    assert len(purchaser.calls) == 1, "the second lot no longer fits the remaining balance"


async def test_failed_purchase_is_reported(app_config, lot_factory):
    notifier = RecordingNotifier()
    purchaser = FakePurchaser(outcome=False, error="GIFT_SOLD_OUT")
    sniper = build_sniper(app_config, catalog=[[lot_factory(price=10)]],
                          purchaser=purchaser, notifier=notifier)

    report = await sniper.run_once()
    assert report.errors and "GIFT_SOLD_OUT" in report.errors[0]
    assert any(level == "error" for level, _ in notifier.messages)


async def test_resale_scan_is_queried_per_gift_id(app_config, lot_factory, resale_lot_factory):
    app_config.filters.include_resale = True
    app_config.filters.resale_gift_ids = [7, 8]
    market = FakeMarket(catalog=[[]], resale={7: [resale_lot_factory(gift_id=7, price=20, slug="a")],
                                              8: [resale_lot_factory(gift_id=8, price=90, slug="b")]})
    sniper = build_sniper(app_config, market=market, buy_enabled=False)

    report = await sniper.run_once()
    assert market.resale_calls == [7, 8]
    assert report.scanned == 2 and report.matched == 2


async def test_missing_resale_support_degrades_gracefully(app_config, resale_lot_factory):
    app_config.filters.include_resale = True
    app_config.filters.resale_gift_ids = [7]
    market = FakeMarket(catalog=[[]], resale={7: UnsupportedApi("payments.getResaleStarGifts is missing")})
    sniper = build_sniper(app_config, market=market, buy_enabled=False)

    report = await sniper.run_once()
    assert report.errors and "getResaleStarGifts" in report.errors[0]


async def test_recipients_are_resolved_once(app_config, lot_factory):
    app_config.buy.recipients = ["me", "@friend"]
    app_config.buy.budget.max_purchases_per_cycle = 5
    app_config.buy.budget.max_purchases_per_gift = 5
    purchaser = FakePurchaser()
    sniper = build_sniper(app_config, catalog=[[lot_factory(price=10)]], purchaser=purchaser)

    await sniper.run_once()
    assert [name for _, name in purchaser.calls] == ["me", "@friend"]


async def test_bad_recipient_fails_fast(app_config):
    app_config.buy.recipients = ["@ghost"]
    sniper = build_sniper(app_config)
    with pytest.raises(ValueError):
        await sniper.resolve_recipients()


# -------------------------------------------------------------------- loop --

async def test_loop_survives_a_failing_cycle(app_config, lot_factory, fake_sleep):
    market = FakeMarket(catalog=[RuntimeError("boom"), [lot_factory(price=10)]])
    notifier = RecordingNotifier()
    sniper = build_sniper(app_config, market=market, notifier=notifier, sleep=fake_sleep)

    await sniper.run_forever(max_cycles=2)
    assert market.catalog_calls == 2
    assert any("cycle failed" in text for _, text in notifier.messages)


async def test_loop_gives_up_after_repeated_failures(app_config, fake_sleep):
    market = FakeMarket(catalog=[RuntimeError("boom")])
    sniper = build_sniper(app_config, market=market, sleep=fake_sleep)

    with pytest.raises(RuntimeError):
        await sniper.run_forever(max_cycles=20)
    assert market.catalog_calls == MAX_CONSECUTIVE_FAILURES


async def test_excessive_flood_wait_stops_the_loop(app_config, fake_sleep):
    market = FakeMarket(catalog=[FloodWaitTooLong(86400, 600, "payments.getStarGifts")])
    notifier = RecordingNotifier()
    sniper = build_sniper(app_config, market=market, notifier=notifier, sleep=fake_sleep)

    with pytest.raises(FloodWaitTooLong):
        await sniper.run_forever(max_cycles=10)
    assert market.catalog_calls == 1, "a huge FLOOD_WAIT must not be retried"
    assert any("stopping" in text for _, text in notifier.messages)


async def test_loop_waits_between_cycles(app_config, fake_sleep, lot_factory):
    app_config.runtime.poll_interval = 60
    app_config.runtime.poll_jitter = 0
    sniper = build_sniper(app_config, catalog=[[lot_factory(price=10)]], sleep=fake_sleep)

    await sniper.run_forever(max_cycles=3)
    assert fake_sleep.calls == [60, 60], "no trailing sleep after the final cycle"


async def test_jitter_stays_inside_its_window(app_config, lot_factory):
    app_config.runtime.poll_interval = 60
    app_config.runtime.poll_jitter = 5
    sniper = build_sniper(app_config)
    delays = [sniper._next_delay() for _ in range(50)]
    assert all(60 <= d <= 65 for d in delays)
