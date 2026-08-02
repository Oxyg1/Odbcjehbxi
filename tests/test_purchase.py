from __future__ import annotations

from telethon.tl import types
from telethon.tl.types import payments as payment_types

from tgmarket.config import BudgetConfig
from tgmarket.models import PurchaseResult
from tgmarket.purchase import Budget, Purchaser, form_price
from tgmarket.ratelimit import ApiGuard, RateLimiter
from tgmarket.state import State


def make_form(form_id=555, stars=50):
    return payment_types.PaymentFormStars(
        form_id=form_id,
        bot_id=0,
        title="Gift",
        description="",
        invoice=types.Invoice(
            currency="XTR",
            prices=[types.LabeledPrice(label="Gift", amount=stars)],
        ),
        users=[],
    )


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def __call__(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def build(responses, **kwargs):
    client = FakeClient(responses)
    return client, Purchaser(client, ApiGuard(RateLimiter()), **kwargs)


PEER = types.InputPeerSelf()


# ------------------------------------------------------------------ invoice --

def test_catalog_invoice_shape(lot_factory):
    _, purchaser = build([], dry_run=True, hide_sender_name=True, message="enjoy")
    invoice = purchaser.build_invoice(lot_factory(gift_id=42), PEER)
    assert isinstance(invoice, types.InputInvoiceStarGift)
    assert invoice.gift_id == 42 and invoice.hide_name is True
    assert invoice.message.text == "enjoy"


def test_resale_invoice_uses_the_slug(resale_lot_factory):
    _, purchaser = build([], dry_run=True)
    invoice = purchaser.build_invoice(resale_lot_factory(slug="pepe-7"), PEER)
    assert isinstance(invoice, types.InputInvoiceStarGiftResale)
    assert invoice.slug == "pepe-7"


def test_form_price_sums_the_line_items():
    assert form_price(make_form(stars=125)) == 125
    assert form_price(payment_types.PaymentFormStars(
        form_id=1, bot_id=0, title="", description="",
        invoice=types.Invoice(currency="XTR", prices=[]), users=[])) is None


# ----------------------------------------------------------------- payment --

async def test_dry_run_requests_the_form_but_never_pays(lot_factory):
    client, purchaser = build([make_form(stars=50)], dry_run=True)
    result = await purchaser.buy(lot_factory(price=50), PEER, "me")

    assert result.ok and result.dry_run and result.price == 50
    assert len(client.requests) == 1, "dry run stops before payments.sendStarsForm"
    assert type(client.requests[0]).__name__ == "GetPaymentFormRequest"


async def test_live_purchase_sends_the_form(lot_factory):
    client, purchaser = build(
        [make_form(form_id=999, stars=50), payment_types.PaymentResult(updates=types.Updates(
            updates=[], users=[], chats=[], date=None, seq=0))],
        dry_run=False,
    )
    result = await purchaser.buy(lot_factory(price=50), PEER, "me")

    assert result.ok and not result.dry_run and result.price == 50
    send = client.requests[1]
    assert send.form_id == 999, "the form id from getPaymentForm is submitted unchanged"


async def test_price_increase_between_listing_and_form_aborts(lot_factory):
    client, purchaser = build([make_form(stars=500)], dry_run=False)
    result = await purchaser.buy(lot_factory(price=50), PEER, "me", max_price=100)

    assert not result.ok
    assert "exceeds" in result.error and "500" in result.error
    assert len(client.requests) == 1, "no payment is sent once the guard trips"


async def test_price_drop_is_accepted_and_charged_at_the_form_price(lot_factory):
    client, purchaser = build(
        [make_form(stars=30), payment_types.PaymentResult(updates=types.Updates(
            updates=[], users=[], chats=[], date=None, seq=0))],
        dry_run=False,
    )
    result = await purchaser.buy(lot_factory(price=50), PEER, "me", max_price=100)
    assert result.ok and result.price == 30


async def test_ceiling_defaults_to_the_listing_price(lot_factory):
    """Without an explicit max_price, the listed price is the ceiling."""
    client, purchaser = build([make_form(stars=51)], dry_run=False)
    result = await purchaser.buy(lot_factory(price=50), PEER, "me")
    assert not result.ok and "51" in result.error


async def test_verification_required_is_not_reported_as_success(lot_factory):
    client, purchaser = build(
        [make_form(stars=50), payment_types.PaymentVerificationNeeded(url="https://t.me/verify")],
        dry_run=False,
    )
    result = await purchaser.buy(lot_factory(price=50), PEER, "me")
    assert not result.ok and "verification" in result.error.lower()


async def test_api_errors_are_captured_not_raised(lot_factory):
    client, purchaser = build([RuntimeError("BALANCE_TOO_LOW")], dry_run=False)
    result = await purchaser.buy(lot_factory(price=50), PEER, "me")
    assert not result.ok and "BALANCE_TOO_LOW" in result.error


async def test_resale_lot_without_slug_is_refused(resale_lot_factory):
    client, purchaser = build([], dry_run=False)
    result = await purchaser.buy(resale_lot_factory(slug=None), PEER, "me")
    assert not result.ok and "slug" in result.error
    assert client.requests == []


# ------------------------------------------------------------------ budget --

def budget(tmp_path, **kwargs) -> Budget:
    return Budget(BudgetConfig(**kwargs), State(tmp_path / "state.json", autosave=False))


def test_per_gift_ceiling(tmp_path, lot_factory):
    guard = budget(tmp_path, max_stars_per_gift=100)
    assert guard.reject_reason(lot_factory(price=100)) is None
    assert "max_stars_per_gift" in guard.reject_reason(lot_factory(price=101))


def test_cycle_limits(tmp_path, lot_factory):
    guard = budget(tmp_path, max_stars_per_cycle=100, max_purchases_per_cycle=2)
    lot = lot_factory(price=60)
    guard.start_cycle()

    assert guard.reject_reason(lot) is None
    guard.record(PurchaseResult(lot=lot, recipient="me", ok=True, dry_run=False, price=60))
    assert "max_stars_per_cycle" in guard.reject_reason(lot)

    guard.start_cycle()
    assert guard.reject_reason(lot) is None, "a new cycle resets the per-cycle counters"


def test_lifetime_total(tmp_path, lot_factory):
    guard = budget(tmp_path, max_stars_total=100)
    guard.state.spent_total = 60
    assert "max_stars_total" in guard.reject_reason(lot_factory(price=50))
    assert guard.reject_reason(lot_factory(price=40)) is None


def test_duplicate_gift_protection(tmp_path, lot_factory):
    guard = budget(tmp_path, max_purchases_per_gift=1)
    lot = lot_factory(gift_id=9, price=10)
    guard.state.record_purchase(PurchaseResult(lot=lot, recipient="me", ok=True, dry_run=False, price=10))
    assert "already own" in guard.reject_reason(lot)


def test_balance_and_reserve(tmp_path, lot_factory):
    guard = budget(tmp_path, min_balance_reserve=100)
    lot = lot_factory(price=50)
    assert guard.reject_reason(lot, balance=200) is None
    assert "too low" in guard.reject_reason(lot, balance=120)
    assert "too low" in guard.reject_reason(lot, balance=10)


def test_dry_run_purchases_do_not_consume_the_star_budget(tmp_path, lot_factory):
    guard = budget(tmp_path, max_stars_per_cycle=100)
    guard.start_cycle()
    guard.record(PurchaseResult(lot=lot_factory(), recipient="me", ok=True, dry_run=True, price=90))
    assert guard.spent_this_cycle == 0
    assert guard.bought_this_cycle == 1, "but they still count against the purchase count"
