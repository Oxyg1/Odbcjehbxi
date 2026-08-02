"""Durable state: what we have seen, what we have bought, what we have spent.

A restart must not re-buy a gift or re-announce lots that were already handled,
so the ledger is flushed to disk after every mutation with an atomic replace.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from .models import GiftLot, PurchaseResult

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
_MAX_PURCHASE_LOG = 500


class State:
    """JSON-backed ledger. Small enough that a database would be overkill."""

    def __init__(self, path: str | os.PathLike[str], *, autosave: bool = True) -> None:
        self.path = Path(path)
        self.autosave = autosave
        self.seen: dict[str, float] = {}
        self.spent_total: int = 0
        self.purchases: list[dict[str, Any]] = []
        self.purchase_count_by_gift: dict[str, int] = {}
        self.last_run: Optional[float] = None

    # ------------------------------------------------------------------ io --

    @classmethod
    def load(cls, path: str | os.PathLike[str], *, autosave: bool = True) -> "State":
        state = cls(path, autosave=autosave)
        if not state.path.is_file():
            return state
        try:
            data = json.loads(state.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # A corrupt ledger must not stop the bot, but losing the spend
            # record silently would be worse than saying so loudly.
            log.error("could not read state file %s (%s) — starting from empty state", state.path, exc)
            return state
        if data.get("version") != SCHEMA_VERSION:
            log.warning("state file %s has version %s, expected %s — starting fresh",
                        state.path, data.get("version"), SCHEMA_VERSION)
            return state
        state.seen = {str(k): float(v) for k, v in (data.get("seen") or {}).items()}
        state.spent_total = int(data.get("spent_total") or 0)
        state.purchases = list(data.get("purchases") or [])
        state.purchase_count_by_gift = {
            str(k): int(v) for k, v in (data.get("purchase_count_by_gift") or {}).items()
        }
        state.last_run = data.get("last_run")
        return state

    def save(self) -> None:
        payload = {
            "version": SCHEMA_VERSION,
            "seen": self.seen,
            "spent_total": self.spent_total,
            "purchases": self.purchases[-_MAX_PURCHASE_LOG:],
            "purchase_count_by_gift": self.purchase_count_by_gift,
            "last_run": self.last_run,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".state-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except OSError as exc:
            log.error("could not persist state to %s: %s", self.path, exc)
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def _touch(self) -> None:
        if self.autosave:
            self.save()

    # --------------------------------------------------------------- lots --

    def is_new(self, lot: GiftLot) -> bool:
        return lot.key not in self.seen

    def mark_seen(self, lots: list[GiftLot]) -> list[GiftLot]:
        """Record ``lots`` and return the subset that had never been seen."""
        now = time.time()
        fresh = [lot for lot in lots if lot.key not in self.seen]
        for lot in lots:
            self.seen.setdefault(lot.key, now)
        if fresh:
            self._touch()
        return fresh

    # ---------------------------------------------------------- purchases --

    def purchases_for(self, lot: GiftLot) -> int:
        return self.purchase_count_by_gift.get(str(lot.gift_id), 0)

    def record_purchase(self, result: PurchaseResult) -> None:
        self.purchases.append(
            {
                "at": result.at,
                "gift_id": result.lot.gift_id,
                "key": result.lot.key,
                "title": result.lot.title,
                "price": result.price,
                "recipient": result.recipient,
                "ok": result.ok,
                "dry_run": result.dry_run,
                "error": result.error,
            }
        )
        if result.ok and not result.dry_run:
            self.spent_total += result.price
            gid = str(result.lot.gift_id)
            self.purchase_count_by_gift[gid] = self.purchase_count_by_gift.get(gid, 0) + 1
        self._touch()

    def finish_run(self) -> None:
        self.last_run = time.time()
        self._touch()
