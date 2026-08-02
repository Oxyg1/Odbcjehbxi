"""Lot selection.

Pure functions over :class:`~tgmarket.models.GiftLot` — no I/O, no API objects —
so the buying rules can be unit-tested without a Telegram account.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .config import FilterConfig
from .models import RESALE, GiftLot


class LotFilter:
    """Evaluates lots against the configured rules."""

    def __init__(self, config: FilterConfig) -> None:
        self.config = config
        self._titles = {t.strip().casefold() for t in config.titles if t.strip()}
        self._ids = set(config.gift_ids)
        self._excluded = set(config.exclude_gift_ids)

    def reject_reason(self, lot: GiftLot) -> Optional[str]:
        """Return why ``lot`` is not buyable, or ``None`` if it passes."""
        cfg = self.config

        if lot.gift_id in self._excluded:
            return "gift id excluded"
        if self._ids and lot.gift_id not in self._ids:
            return "gift id not in allow-list"
        if self._titles and (lot.title or "").strip().casefold() not in self._titles:
            return "title not in allow-list"

        if lot.price < cfg.min_price:
            return f"price {lot.price} below min_price {cfg.min_price}"
        if cfg.max_price is not None and lot.price > cfg.max_price:
            return f"price {lot.price} above max_price {cfg.max_price}"

        if cfg.skip_sold_out and lot.sold_out:
            return "sold out"
        if cfg.skip_premium_required and lot.require_premium:
            return "requires Telegram Premium"

        if cfg.limited_only and not lot.limited:
            return "not a limited gift"
        if cfg.unlimited_only and lot.limited:
            return "limited gift"

        # Availability only means something for limited catalogue lots: resale
        # listings are single copies and unlimited gifts report nothing at all.
        if lot.kind != RESALE and lot.limited and lot.available is not None:
            if lot.available < cfg.min_available:
                return f"only {lot.available} left, need {cfg.min_available}"

        if lot.total is not None:
            if cfg.min_supply is not None and lot.total < cfg.min_supply:
                return f"supply {lot.total} below min_supply {cfg.min_supply}"
            if cfg.max_supply is not None and lot.total > cfg.max_supply:
                return f"supply {lot.total} above max_supply {cfg.max_supply}"

        return None

    def matches(self, lot: GiftLot) -> bool:
        return self.reject_reason(lot) is None

    def select(self, lots: Iterable[GiftLot]) -> list[GiftLot]:
        """Matching lots, cheapest first — the bot spends its budget on those."""
        return sorted((lot for lot in lots if self.matches(lot)), key=lambda l: (l.price, l.gift_id))
