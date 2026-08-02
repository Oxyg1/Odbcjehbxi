from __future__ import annotations

from tgmarket.config import FilterConfig
from tgmarket.filters import LotFilter


def test_price_window(lot_factory):
    lot_filter = LotFilter(FilterConfig(min_price=10, max_price=100))
    assert lot_filter.matches(lot_factory(price=50))
    assert not lot_filter.matches(lot_factory(price=5))
    assert not lot_filter.matches(lot_factory(price=101))
    assert lot_filter.matches(lot_factory(price=100)), "max_price is inclusive"


def test_allow_and_deny_lists(lot_factory):
    lot_filter = LotFilter(FilterConfig(gift_ids=[7, 8], exclude_gift_ids=[8]))
    assert lot_filter.matches(lot_factory(gift_id=7))
    assert not lot_filter.matches(lot_factory(gift_id=8)), "exclusion wins over the allow-list"
    assert not lot_filter.matches(lot_factory(gift_id=9))


def test_title_match_is_case_insensitive(lot_factory):
    lot_filter = LotFilter(FilterConfig(titles=["Delicious Cake"]))
    assert lot_filter.matches(lot_factory(title="delicious cake"))
    assert not lot_filter.matches(lot_factory(title="Cake"))
    assert not lot_filter.matches(lot_factory(title=None))


def test_sold_out_and_premium_are_skipped(lot_factory):
    lot_filter = LotFilter(FilterConfig())
    assert not lot_filter.matches(lot_factory(sold_out=True))
    assert not lot_filter.matches(lot_factory(require_premium=True))

    permissive = LotFilter(FilterConfig(skip_sold_out=False, skip_premium_required=False))
    assert permissive.matches(lot_factory(sold_out=True, require_premium=True))


def test_limited_flags(lot_factory):
    limited_only = LotFilter(FilterConfig(limited_only=True))
    assert limited_only.matches(lot_factory(limited=True, available=5, total=100))
    assert not limited_only.matches(lot_factory(limited=False))

    unlimited_only = LotFilter(FilterConfig(unlimited_only=True))
    assert unlimited_only.matches(lot_factory(limited=False))
    assert not unlimited_only.matches(lot_factory(limited=True, available=5))


def test_availability_only_applies_to_limited_catalogue_lots(lot_factory, resale_lot_factory):
    lot_filter = LotFilter(FilterConfig(min_available=2))
    assert not lot_filter.matches(lot_factory(limited=True, available=1))
    assert lot_filter.matches(lot_factory(limited=True, available=2))
    assert lot_filter.matches(lot_factory(limited=False, available=None))
    # A resale listing is a single copy; availability_issued must not veto it.
    assert lot_filter.matches(resale_lot_factory(available=1, total=1000))


def test_supply_bounds(lot_factory):
    lot_filter = LotFilter(FilterConfig(min_supply=100, max_supply=5000))
    assert lot_filter.matches(lot_factory(limited=True, available=5, total=1000))
    assert not lot_filter.matches(lot_factory(limited=True, available=5, total=50))
    assert not lot_filter.matches(lot_factory(limited=True, available=5, total=9000))


def test_reject_reason_explains_itself(lot_factory):
    lot_filter = LotFilter(FilterConfig(max_price=10))
    reason = lot_filter.reject_reason(lot_factory(price=99))
    assert reason is not None and "99" in reason and "max_price" in reason


def test_select_orders_cheapest_first(lot_factory):
    lot_filter = LotFilter(FilterConfig(max_price=100))
    lots = [lot_factory(gift_id=1, price=90), lot_factory(gift_id=2, price=10),
            lot_factory(gift_id=3, price=500), lot_factory(gift_id=4, price=10)]
    assert [(l.gift_id, l.price) for l in lot_filter.select(lots)] == [(2, 10), (4, 10), (1, 90)]
