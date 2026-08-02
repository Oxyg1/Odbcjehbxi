"""The monitor → filter → buy loop.

One cycle is: read the catalogue (and optionally resale listings), record what is
new, pick what matches, and buy what the budget allows.  The loop owns error
recovery — a single bad cycle must never end the process, but an account-level
problem (a huge FLOOD_WAIT, an auth failure) must stop it immediately rather
than grinding against Telegram.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Awaitable, Callable, Optional

from .config import AppConfig
from .filters import LotFilter
from .market import MarketClient, UnsupportedApi
from .models import CycleReport, GiftLot
from .notify import Notifier, NullNotifier
from .purchase import Budget, Purchaser
from .ratelimit import FloodWaitTooLong
from .state import State

log = logging.getLogger(__name__)

#: Consecutive failed cycles tolerated before giving up.
MAX_CONSECUTIVE_FAILURES = 5


class Sniper:
    """Wires the pieces together and runs the loop."""

    def __init__(
        self,
        config: AppConfig,
        client: Any,
        market: MarketClient,
        purchaser: Purchaser,
        lot_filter: LotFilter,
        budget: Budget,
        state: State,
        notifier: Optional[Notifier] = None,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        buy_enabled: bool = True,
    ) -> None:
        self.config = config
        self.client = client
        self.market = market
        self.purchaser = purchaser
        self.filter = lot_filter
        self.budget = budget
        self.state = state
        self.notifier = notifier or NullNotifier()
        self._sleep = sleep
        self.buy_enabled = buy_enabled
        self._recipients: list[tuple[str, Any]] = []

    # ---------------------------------------------------------- recipients --

    async def resolve_recipients(self) -> list[tuple[str, Any]]:
        """Resolve recipient handles to input peers once, up front.

        Doing this at startup means a typo in ``buy.recipients`` surfaces
        immediately instead of at the moment a rare gift appears.
        """
        if self._recipients:
            return self._recipients
        resolved: list[tuple[str, Any]] = []
        for name in self.config.buy.recipients:
            peer = await self.client.get_input_entity("me" if name in {"me", "self"} else name)
            resolved.append((name, peer))
        self._recipients = resolved
        return resolved

    # --------------------------------------------------------------- cycle --

    async def collect_lots(self, report: CycleReport) -> list[GiftLot]:
        lots = await self.market.catalog()
        cfg = self.config.filters
        if cfg.include_resale:
            for gift_id in (cfg.resale_gift_ids or cfg.gift_ids):
                try:
                    lots.extend(
                        await self.market.resale(
                            gift_id,
                            limit=cfg.resale_page_limit,
                            max_pages=cfg.resale_max_pages,
                        )
                    )
                except UnsupportedApi as exc:
                    report.errors.append(str(exc))
                    log.error("resale scan disabled: %s", exc)
                    break
        return lots

    async def run_once(self) -> CycleReport:
        report = CycleReport()
        lots = await self.collect_lots(report)
        report.scanned = len(lots)

        fresh = self.state.mark_seen(lots)
        report.new_lots = len(fresh)
        for lot in fresh:
            log.info("new lot: %s", lot.describe())

        candidates = self.filter.select(lots)
        report.matched = len(candidates)
        if not candidates:
            log.info("cycle: %s", report.describe())
            self.state.finish_run()
            return report

        for lot in candidates:
            log.info("match: %s", lot.describe())
        await self._announce_matches(candidates, fresh)

        if not self.buy_enabled:
            self.state.finish_run()
            log.info("cycle (watch only): %s", report.describe())
            return report

        await self._buy_candidates(candidates, report)
        self.state.finish_run()
        log.info("cycle: %s", report.describe())
        return report

    async def _announce_matches(self, candidates: list[GiftLot], fresh: list[GiftLot]) -> None:
        if not self.config.notify.notify_on_match:
            return
        fresh_keys = {lot.key for lot in fresh}
        new_matches = [lot for lot in candidates if lot.key in fresh_keys]
        if not new_matches:
            return
        body = "\n".join(f"• {lot.describe()}" for lot in new_matches[:20])
        await self.notifier.info(f"{len(new_matches)} new matching lot(s):\n{body}")

    async def _buy_candidates(self, candidates: list[GiftLot], report: CycleReport) -> None:
        self.budget.start_cycle()
        balance: Optional[int] = None
        if not self.purchaser.dry_run:
            try:
                balance = await self.market.balance()
                log.info("Stars balance: %d⭐", balance)
            except Exception as exc:  # noqa: BLE001 - balance is a guard, not the task
                if isinstance(exc, FloodWaitTooLong):
                    raise
                report.errors.append(f"balance check failed: {type(exc).__name__}: {exc}")
                log.warning("could not read balance (%s) — refusing to buy blind", exc)
                return

        recipients = await self.resolve_recipients()
        for lot in candidates:
            for name, peer in recipients:
                reason = self.budget.reject_reason(lot, balance=balance)
                if reason:
                    log.info("skipping %s: %s", lot.label, reason)
                    continue

                result = await self.purchaser.buy(
                    lot, peer, name, max_price=self.config.filters.max_price
                )
                self.budget.record(result)
                self.state.record_purchase(result)
                report.purchases.append(result)

                if result.ok and not result.dry_run:
                    if balance is not None:
                        balance -= result.price
                    await self.notifier.success(result.describe())
                elif not result.ok:
                    report.errors.append(result.describe())
                    if self.config.notify.notify_on_error:
                        await self.notifier.error(result.describe())

    # ---------------------------------------------------------------- loop --

    async def run_forever(self, *, max_cycles: Optional[int] = None) -> None:
        runtime = self.config.runtime
        mode = "DRY-RUN" if self.purchaser.dry_run else "LIVE"
        if not self.buy_enabled:
            mode = "WATCH-ONLY"
        log.info("starting in %s mode, polling every %.0fs", mode, runtime.poll_interval)
        if self.config.notify.notify_on_start:
            await self.notifier.info(f"tgmarket started in {mode} mode (interval {runtime.poll_interval:.0f}s)")

        failures = 0
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            cycles += 1
            try:
                await self.run_once()
                failures = 0
            except FloodWaitTooLong as exc:
                log.error("%s", exc)
                await self.notifier.error(f"stopping: {exc}")
                raise
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                failures += 1
                log.exception("cycle failed (%d/%d)", failures, MAX_CONSECUTIVE_FAILURES)
                await self.notifier.error(f"cycle failed ({failures}/{MAX_CONSECUTIVE_FAILURES}): "
                                          f"{type(exc).__name__}: {exc}")
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    await self.notifier.error("too many consecutive failures — shutting down")
                    raise
                await self._sleep(min(60.0 * failures, 300.0))
                continue

            if max_cycles is not None and cycles >= max_cycles:
                break
            await self._sleep(self._next_delay())

    def _next_delay(self) -> float:
        """Poll interval plus a little jitter.

        The jitter keeps several instances (or a restarted one) from lining up
        on the same second; it is not an attempt to look human.
        """
        runtime = self.config.runtime
        if runtime.poll_jitter <= 0:
            return runtime.poll_interval
        return runtime.poll_interval + random.uniform(0, runtime.poll_jitter)
