from __future__ import annotations

from telethon.tl import types
from telethon.tl.types import payments as payment_types

from tgmarket.market import MarketClient, lot_from_star_gift, lot_from_unique_gift
from tgmarket.models import CATALOG, RESALE
from tgmarket.ratelimit import ApiGuard, RateLimiter


def make_star_gift(gift_id=1, stars=50, **kwargs):
    return types.StarGift(
        id=gift_id,
        sticker=None,
        stars=stars,
        convert_stars=kwargs.pop("convert_stars", stars // 2),
        **kwargs,
    )


def make_unique_gift(**kwargs):
    defaults = dict(
        id=1,
        gift_id=99,
        title="Plush Pepe",
        slug="plushpepe-1",
        num=1,
        attributes=[],
        availability_issued=1,
        availability_total=1000,
    )
    defaults.update(kwargs)
    return types.StarGiftUnique(**defaults)


class FakeClient:
    """Records requests and replays canned responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def __call__(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def build_market(responses):
    client = FakeClient(responses)
    return client, MarketClient(client, ApiGuard(RateLimiter()))


# ----------------------------------------------------------- normalisation --

def test_catalog_gift_normalisation():
    lot = lot_from_star_gift(
        make_star_gift(gift_id=5, stars=75, limited=True, availability_remains=3,
                       availability_total=1000, title="Cake", require_premium=True)
    )
    assert (lot.gift_id, lot.price, lot.kind) == (5, 75, CATALOG)
    assert (lot.limited, lot.available, lot.total) == (True, 3, 1000)
    assert lot.require_premium and lot.key == "catalog:5"


def test_resale_gift_normalisation():
    lot = lot_from_unique_gift(
        make_unique_gift(resell_amount=[types.StarsAmount(amount=1200, nanos=0)])
    )
    assert (lot.kind, lot.price, lot.slug, lot.num) == (RESALE, 1200, "plushpepe-1", 1)
    assert lot.key == "resale:plushpepe-1", "resale copies are distinct lots"


def test_resale_price_rounds_up_so_ceilings_hold():
    lot = lot_from_unique_gift(
        make_unique_gift(resell_amount=[types.StarsAmount(amount=99, nanos=500_000_000)])
    )
    assert lot.price == 100, "a 99.5 star lot must not slip past a 99 star ceiling"


def test_ton_only_resale_lots_are_dropped():
    ton_only = make_unique_gift(resale_ton_only=True,
                                resell_amount=[types.StarsAmount(amount=10, nanos=0)])
    assert lot_from_unique_gift(ton_only) is None
    # Priced in TON only, without the flag: still unpayable in Stars.
    assert lot_from_unique_gift(make_unique_gift(resell_amount=[types.StarsTonAmount(amount=5)])) is None
    assert lot_from_unique_gift(make_unique_gift(resell_amount=[])) is None


# ------------------------------------------------------------------- calls --

async def test_catalog_fetches_and_caches_by_hash():
    gifts = [make_star_gift(gift_id=1, stars=10), make_star_gift(gift_id=2, stars=20)]
    client, market = build_market([
        payment_types.StarGifts(hash=777, gifts=gifts, chats=[], users=[]),
        payment_types.StarGiftsNotModified(),
    ])

    first = await market.catalog()
    assert [lot.gift_id for lot in first] == [1, 2]
    assert client.requests[0].hash == 0

    second = await market.catalog()
    assert client.requests[1].hash == 777, "the server hash is echoed back to get the cheap path"
    assert [lot.gift_id for lot in second] == [1, 2], "unchanged means serve the cache"


async def test_catalog_result_is_not_shared_with_the_cache():
    client, market = build_market([
        payment_types.StarGifts(hash=1, gifts=[make_star_gift()], chats=[], users=[]),
        payment_types.StarGiftsNotModified(),
    ])
    lots = await market.catalog()
    lots.clear()
    assert len(await market.catalog()) == 1, "caller mutations must not empty the cache"


async def test_resale_paginates_until_offset_runs_out():
    page1 = payment_types.ResaleStarGifts(
        count=2, gifts=[make_unique_gift(slug="a", resell_amount=[types.StarsAmount(amount=10, nanos=0)])],
        chats=[], users=[], next_offset="cursor",
    )
    page2 = payment_types.ResaleStarGifts(
        count=2, gifts=[make_unique_gift(slug="b", resell_amount=[types.StarsAmount(amount=20, nanos=0)])],
        chats=[], users=[], next_offset=None,
    )
    client, market = build_market([page1, page2])

    lots = await market.resale(99, limit=25, max_pages=5)
    assert [lot.slug for lot in lots] == ["a", "b"]
    assert client.requests[0].offset == "" and client.requests[1].offset == "cursor"
    assert client.requests[0].sort_by_price is True, "cheapest lots must come first"


async def test_resale_respects_max_pages():
    page = payment_types.ResaleStarGifts(
        count=99, gifts=[make_unique_gift(resell_amount=[types.StarsAmount(amount=10, nanos=0)])],
        chats=[], users=[], next_offset="more",
    )
    client, market = build_market([page, page, page])
    await market.resale(99, max_pages=2)
    assert len(client.requests) == 2


async def test_balance_reads_stars_amount():
    client, market = build_market([
        payment_types.StarsStatus(balance=types.StarsAmount(amount=1234, nanos=0), chats=[], users=[])
    ])
    assert await market.balance() == 1234


async def test_balance_floors_partial_stars():
    client, market = build_market([
        payment_types.StarsStatus(balance=types.StarsAmount(amount=10, nanos=900_000_000),
                                  chats=[], users=[])
    ])
    assert await market.balance() == 10, "never round a balance up — it gates spending"
