"""Normalised data structures shared by every module.

The MTProto layer changes often (see ``docs/RESEARCH.md`` — API instability is
one of the three named risks), so nothing outside :mod:`tgmarket.market` works
with raw TL objects.  Everything downstream consumes :class:`GiftLot`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

CATALOG = "catalog"
RESALE = "resale"


@dataclass(frozen=True)
class GiftLot:
    """A single purchasable lot, either from the catalogue or the resale market.

    ``price`` is always in Telegram Stars.  Resale lots priced exclusively in
    TON are dropped during normalisation, because this bot only pays in Stars.
    """

    gift_id: int
    kind: str
    price: int
    title: Optional[str] = None
    slug: Optional[str] = None
    num: Optional[int] = None
    limited: bool = False
    sold_out: bool = False
    require_premium: bool = False
    available: Optional[int] = None
    total: Optional[int] = None
    resale_count: Optional[int] = None
    convert_stars: Optional[int] = None
    upgrade_stars: Optional[int] = None
    raw: Any = field(default=None, compare=False, repr=False)

    @property
    def key(self) -> str:
        """Stable identity used for de-duplication in :mod:`tgmarket.state`.

        Catalogue entries are identified by gift id; resale listings by slug,
        since the same gift id yields many distinct numbered copies.
        """
        if self.kind == RESALE and self.slug:
            return f"resale:{self.slug}"
        return f"{self.kind}:{self.gift_id}"

    @property
    def label(self) -> str:
        name = self.title or f"gift {self.gift_id}"
        if self.num is not None:
            name = f"{name} #{self.num}"
        return name

    def describe(self) -> str:
        bits = [f"{self.label} — {self.price}⭐"]
        if self.limited:
            if self.available is not None and self.total is not None:
                bits.append(f"limited {self.available}/{self.total}")
            else:
                bits.append("limited")
        if self.kind == RESALE:
            bits.append("resale")
        if self.sold_out:
            bits.append("sold out")
        return " | ".join(bits)


@dataclass(frozen=True)
class PurchaseResult:
    """Outcome of one attempted purchase."""

    lot: GiftLot
    recipient: str
    ok: bool
    dry_run: bool
    price: int
    error: Optional[str] = None
    at: float = field(default_factory=time.time)

    def describe(self) -> str:
        if self.ok and self.dry_run:
            head = "DRY-RUN would buy"
        elif self.ok:
            head = "bought"
        else:
            head = "FAILED to buy"
        line = f"{head} {self.lot.label} for {self.price}⭐ → {self.recipient}"
        if self.error:
            line = f"{line}: {self.error}"
        return line


@dataclass
class CycleReport:
    """Summary of a single monitor/purchase iteration."""

    scanned: int = 0
    new_lots: int = 0
    matched: int = 0
    purchases: list[PurchaseResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def spent(self) -> int:
        return sum(p.price for p in self.purchases if p.ok and not p.dry_run)

    def describe(self) -> str:
        return (
            f"scanned={self.scanned} new={self.new_lots} matched={self.matched} "
            f"bought={sum(1 for p in self.purchases if p.ok)} "
            f"failed={sum(1 for p in self.purchases if not p.ok)} spent={self.spent}⭐"
        )
