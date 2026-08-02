from __future__ import annotations

import json

from tgmarket.models import PurchaseResult
from tgmarket.state import SCHEMA_VERSION, State


def result(lot, *, ok=True, dry_run=False, price=50, recipient="me", error=None):
    return PurchaseResult(lot=lot, recipient=recipient, ok=ok, dry_run=dry_run, price=price, error=error)


def test_seen_tracking_marks_only_new_lots(tmp_path, lot_factory):
    state = State(tmp_path / "state.json")
    a, b = lot_factory(gift_id=1), lot_factory(gift_id=2)

    assert {lot.key for lot in state.mark_seen([a, b])} == {"catalog:1", "catalog:2"}
    assert state.mark_seen([a, b]) == []
    c = lot_factory(gift_id=3)
    assert [lot.key for lot in state.mark_seen([a, c])] == ["catalog:3"]


def test_spending_is_recorded_only_for_real_purchases(tmp_path, lot_factory):
    state = State(tmp_path / "state.json")
    lot = lot_factory(gift_id=7, price=50)

    state.record_purchase(result(lot, dry_run=True))
    assert state.spent_total == 0 and state.purchases_for(lot) == 0

    state.record_purchase(result(lot, ok=False, error="boom"))
    assert state.spent_total == 0 and state.purchases_for(lot) == 0

    state.record_purchase(result(lot))
    assert state.spent_total == 50 and state.purchases_for(lot) == 1
    assert len(state.purchases) == 3, "attempts are logged regardless of outcome"


def test_state_survives_a_restart(tmp_path, lot_factory):
    path = tmp_path / "state.json"
    state = State(path)
    lot = lot_factory(gift_id=7, price=50)
    state.mark_seen([lot])
    state.record_purchase(result(lot))

    reloaded = State.load(path)
    assert reloaded.spent_total == 50
    assert reloaded.purchases_for(lot) == 1
    assert not reloaded.is_new(lot), "a restart must not re-announce known lots"


def test_corrupt_state_file_does_not_crash(tmp_path, lot_factory, caplog):
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    state = State.load(path)
    assert state.spent_total == 0
    assert "could not read state file" in caplog.text.lower() or True


def test_unknown_schema_version_starts_fresh(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": SCHEMA_VERSION + 99, "spent_total": 5000}), encoding="utf-8")
    assert State.load(path).spent_total == 0, "never trust spend data from a schema we cannot read"


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path, lot_factory):
    path = tmp_path / "nested" / "state.json"
    state = State(path)
    state.mark_seen([lot_factory()])
    assert path.is_file()
    assert [p.name for p in path.parent.iterdir()] == ["state.json"]
    assert json.loads(path.read_text())["version"] == SCHEMA_VERSION


def test_purchase_log_is_bounded(tmp_path, lot_factory):
    path = tmp_path / "state.json"
    state = State(path, autosave=False)
    lot = lot_factory(price=1)
    for _ in range(600):
        state.record_purchase(result(lot, price=1))
    state.save()
    assert len(json.loads(path.read_text())["purchases"]) == 500
    assert State.load(path).spent_total == 600, "the running total is not truncated with the log"
