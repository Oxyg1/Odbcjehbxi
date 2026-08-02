"""Read side of the market: the gift catalogue, the resale listings, the balance.

Everything that touches raw TL objects lives here.  Requests are resolved with
:func:`getattr` rather than direct imports so that a Telethon build without, say,
``payments.getResaleStarGifts`` degrades to "resale unsupported" instead of
crashing the process at import time.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Iterable, Optional

from telethon.tl import functions, types

from .models import CATALOG, RESALE, GiftLot
from .ratelimit import ApiGuard

log = logging.getLogger(__name__)

_payments = functions.payments


class UnsupportedApi(RuntimeError):
    """The installed MTProto library does not expose a method we need."""


def _request(name: str) -> Any:
    req = getattr(_payments, name, None)
    if req is None:
        raise UnsupportedApi(
            f"payments.{name} is missing from the installed Telethon build. "
            "Upgrade Telethon (pip install -U telethon) or disable the feature that needs it."
        )
    return req


def _stars_amount(amounts: Optional[Iterable[Any]]) -> Optional[int]:
    """Pick the Stars price out of a list of ``StarsAmount``/``StarsTonAmount``.

    Rounded up: a lot advertised at 99.5⭐ must not slip past a 99⭐ ceiling.
    """
    if not amounts:
        return None
    for amount in amounts:
        if type(amount).__name__ != "StarsAmount":
            continue  # TON-denominated price; this bot only pays in Stars
        whole = getattr(amount, "amount", 0) or 0
        nanos = getattr(amount, "nanos", 0) or 0
        return int(whole) + (1 if nanos > 0 else 0)
    return None


def lot_from_star_gift(gift: Any) -> Optional[GiftLot]:
    """Normalise a catalogue ``StarGift`` into a :class:`GiftLot`."""
    price = getattr(gift, "stars", None)
    if price is None:
        return None
    return GiftLot(
        gift_id=gift.id,
        kind=CATALOG,
        price=int(price),
        title=getattr(gift, "title", None),
        limited=bool(getattr(gift, "limited", False)),
        sold_out=bool(getattr(gift, "sold_out", False)),
        require_premium=bool(getattr(gift, "require_premium", False)),
        available=getattr(gift, "availability_remains", None),
        total=getattr(gift, "availability_total", None),
        resale_count=getattr(gift, "availability_resale", None),
        convert_stars=getattr(gift, "convert_stars", None),
        upgrade_stars=getattr(gift, "upgrade_stars", None),
        raw=gift,
    )


def lot_from_unique_gift(gift: Any) -> Optional[GiftLot]:
    """Normalise a resale ``StarGiftUnique`` listing into a :class:`GiftLot`."""
    if getattr(gift, "resale_ton_only", False):
        return None
    price = _stars_amount(getattr(gift, "resell_amount", None))
    if price is None:
        return None
    return GiftLot(
        gift_id=getattr(gift, "gift_id", 0) or 0,
        kind=RESALE,
        price=price,
        title=getattr(gift, "title", None),
        slug=getattr(gift, "slug", None),
        num=getattr(gift, "num", None),
        limited=True,
        require_premium=bool(getattr(gift, "require_premium", False)),
        available=getattr(gift, "availability_issued", None),
        total=getattr(gift, "availability_total", None),
        raw=gift,
    )


class MarketClient:
    """Thin, normalising wrapper over the gift-related ``payments.*`` methods."""

    def __init__(self, client: Any, guard: ApiGuard) -> None:
        self._client = client
        self._guard = guard
        self._catalog_hash = 0
        self._catalog_cache: list[GiftLot] = []

    async def catalog(self) -> list[GiftLot]:
        """Fetch the Star gift catalogue (``payments.getStarGifts``).

        Telegram answers ``StarGiftsNotModified`` when nothing changed since the
        hash we sent, which is the cheap path we want on a 60-second loop.
        """
        req = _request("GetStarGiftsRequest")
        result = await self._guard.call(
            lambda: self._client(req(hash=self._catalog_hash)), label="payments.getStarGifts"
        )
        if type(result).__name__ == "StarGiftsNotModified":
            log.debug("catalog unchanged (%d cached lots)", len(self._catalog_cache))
            return list(self._catalog_cache)

        lots = [lot for lot in map(lot_from_star_gift, getattr(result, "gifts", [])) if lot]
        self._catalog_hash = getattr(result, "hash", 0) or 0
        self._catalog_cache = lots
        log.debug("catalog refreshed: %d lots (hash=%s)", len(lots), self._catalog_hash)
        return list(lots)

    async def resale(self, gift_id: int, *, limit: int = 50, max_pages: int = 1) -> list[GiftLot]:
        """Fetch resale listings for one gift id, cheapest first.

        ``sort_by_price`` means page one already holds the interesting lots, so
        ``max_pages`` stays at 1 unless the caller really wants more.
        """
        req = _request("GetResaleStarGiftsRequest")
        lots: list[GiftLot] = []
        offset = ""
        for _ in range(max(1, max_pages)):
            result = await self._guard.call(
                lambda off=offset: self._client(
                    req(gift_id=gift_id, offset=off, limit=limit, sort_by_price=True)
                ),
                label="payments.getResaleStarGifts",
            )
            page = [lot for lot in map(lot_from_unique_gift, getattr(result, "gifts", [])) if lot]
            lots.extend(page)
            offset = getattr(result, "next_offset", None) or ""
            if not offset or not page:
                break
        log.debug("resale for gift %d: %d lots", gift_id, len(lots))
        return lots

    async def balance(self) -> int:
        """Current Stars balance of the logged-in account, rounded down."""
        req = _request("GetStarsStatusRequest")
        result = await self._guard.call(
            lambda: self._client(req(peer=types.InputPeerSelf())), label="payments.getStarsStatus"
        )
        amount = getattr(result, "balance", None)
        if amount is None:
            return 0
        if isinstance(amount, int):
            return amount
        whole = getattr(amount, "amount", 0) or 0
        nanos = getattr(amount, "nanos", 0) or 0
        return int(whole) + math.floor(nanos / 1_000_000_000)

    def supports_resale(self) -> bool:
        return getattr(_payments, "GetResaleStarGiftsRequest", None) is not None
