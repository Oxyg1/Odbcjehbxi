"""Write side of the market: turning a matched lot into a paid Star gift.

The flow mirrors what an official client does — build an invoice, request a
payment form, then submit that form:

    payments.getPaymentForm(inputInvoiceStarGift|inputInvoiceStarGiftResale)
    payments.sendStarsForm(form_id, invoice)

Between those two calls the bot re-reads the price *from the form* and refuses
to pay if it drifted from the listing it matched on.  Money leaving the account
is irreversible, so every guard here fails closed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from telethon.tl import functions, types

from .config import BudgetConfig
from .models import RESALE, GiftLot, PurchaseResult
from .ratelimit import ApiGuard, FloodWaitTooLong
from .state import State

log = logging.getLogger(__name__)

_payments = functions.payments


class PurchaseAborted(Exception):
    """A guard refused the purchase before any money moved."""


@dataclass
class Budget:
    """Enforces the spend ceilings from ``buy.budget``."""

    config: BudgetConfig
    state: State
    spent_this_cycle: int = 0
    bought_this_cycle: int = 0

    def start_cycle(self) -> None:
        self.spent_this_cycle = 0
        self.bought_this_cycle = 0

    def reject_reason(self, lot: GiftLot, *, balance: Optional[int] = None) -> Optional[str]:
        cfg = self.config
        if cfg.max_stars_per_gift is not None and lot.price > cfg.max_stars_per_gift:
            return f"price {lot.price}⭐ over budget.max_stars_per_gift ({cfg.max_stars_per_gift}⭐)"
        if cfg.max_purchases_per_cycle and self.bought_this_cycle >= cfg.max_purchases_per_cycle:
            return f"already bought {self.bought_this_cycle} this cycle (budget.max_purchases_per_cycle)"
        if cfg.max_purchases_per_gift and self.state.purchases_for(lot) >= cfg.max_purchases_per_gift:
            return f"already own {self.state.purchases_for(lot)} of gift {lot.gift_id} (budget.max_purchases_per_gift)"
        if cfg.max_stars_per_cycle and self.spent_this_cycle + lot.price > cfg.max_stars_per_cycle:
            return f"would exceed budget.max_stars_per_cycle ({cfg.max_stars_per_cycle}⭐)"
        if cfg.max_stars_total and self.state.spent_total + lot.price > cfg.max_stars_total:
            return (f"would exceed budget.max_stars_total "
                    f"({self.state.spent_total}+{lot.price} > {cfg.max_stars_total}⭐)")
        if balance is not None and lot.price + cfg.min_balance_reserve > balance:
            return f"balance {balance}⭐ too low for {lot.price}⭐ (+{cfg.min_balance_reserve}⭐ reserve)"
        return None

    def record(self, result: PurchaseResult) -> None:
        if not result.ok:
            return
        self.bought_this_cycle += 1
        if not result.dry_run:
            self.spent_this_cycle += result.price


class Purchaser:
    """Executes the two-step Stars payment for a lot."""

    def __init__(
        self,
        client: Any,
        guard: ApiGuard,
        *,
        dry_run: bool = True,
        hide_sender_name: bool = False,
        include_upgrade: bool = False,
        message: Optional[str] = None,
    ) -> None:
        self._client = client
        self._guard = guard
        self.dry_run = dry_run
        self.hide_sender_name = hide_sender_name
        self.include_upgrade = include_upgrade
        self.message = message

    def build_invoice(self, lot: GiftLot, peer: Any) -> Any:
        if lot.kind == RESALE:
            if not lot.slug:
                raise PurchaseAborted("resale lot has no slug — cannot build an invoice")
            return types.InputInvoiceStarGiftResale(slug=lot.slug, to_id=peer)
        return types.InputInvoiceStarGift(
            peer=peer,
            gift_id=lot.gift_id,
            hide_name=self.hide_sender_name or None,
            include_upgrade=self.include_upgrade or None,
            message=types.TextWithEntities(text=self.message, entities=[]) if self.message else None,
        )

    async def buy(self, lot: GiftLot, peer: Any, recipient: str, *,
                  max_price: Optional[int] = None) -> PurchaseResult:
        """Attempt to buy ``lot`` for ``recipient``; never raises on API errors."""
        try:
            invoice = self.build_invoice(lot, peer)
            form = await self._guard.call(
                lambda: self._client(_payments.GetPaymentFormRequest(invoice=invoice)),
                label="payments.getPaymentForm",
            )
            price = form_price(form)
            if price is None:
                raise PurchaseAborted("payment form carried no Stars price")

            # The listing we matched on can be stale by the time the form comes
            # back. Pay the form price only if it still passes our ceilings.
            ceiling = max_price if max_price is not None else lot.price
            if price > ceiling:
                raise PurchaseAborted(
                    f"form price {price}⭐ exceeds the {ceiling}⭐ ceiling (listing said {lot.price}⭐)"
                )
            if price != lot.price:
                log.info("%s: price moved %d⭐ → %d⭐, still within ceiling", lot.label, lot.price, price)

            if self.dry_run:
                log.info("DRY-RUN: not sending payment form %s for %s", getattr(form, "form_id", "?"), lot.label)
                return PurchaseResult(lot=lot, recipient=recipient, ok=True, dry_run=True, price=price)

            result = await self._guard.call(
                lambda: self._client(
                    _payments.SendStarsFormRequest(form_id=form.form_id, invoice=invoice)
                ),
                label="payments.sendStarsForm",
            )
            if type(result).__name__ == "PaymentVerificationNeeded":
                raise PurchaseAborted(
                    "Telegram asked for interactive payment verification — "
                    f"finish it manually at {getattr(result, 'url', 'the returned URL')}"
                )
            log.info("bought %s for %d⭐ → %s", lot.label, price, recipient)
            return PurchaseResult(lot=lot, recipient=recipient, ok=True, dry_run=False, price=price)

        except PurchaseAborted as exc:
            log.warning("purchase aborted for %s: %s", lot.label, exc)
            return PurchaseResult(lot=lot, recipient=recipient, ok=False, dry_run=self.dry_run,
                                  price=lot.price, error=str(exc))
        except FloodWaitTooLong:
            raise  # account-level problem: the loop must stop, not move on
        except Exception as exc:  # noqa: BLE001 - one bad lot must not kill the loop
            log.error("purchase failed for %s: %s: %s", lot.label, type(exc).__name__, exc)
            return PurchaseResult(lot=lot, recipient=recipient, ok=False, dry_run=self.dry_run,
                                  price=lot.price, error=f"{type(exc).__name__}: {exc}")


def form_price(form: Any) -> Optional[int]:
    """Total Stars amount carried by a payment form."""
    invoice = getattr(form, "invoice", None)
    prices = getattr(invoice, "prices", None) or []
    total = 0
    for price in prices:
        amount = getattr(price, "amount", None)
        if amount is None:
            continue
        total += int(amount)
    return total if prices else None
