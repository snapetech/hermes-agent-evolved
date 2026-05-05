import json
from datetime import datetime, timedelta, timezone

from tools.maintenance_freshness import (
    due_items,
    explain_item,
    list_items,
    record_completion,
    seed_defaults,
    snooze_item,
)
from tools.maintenance_freshness_tool import maintenance_freshness


def test_seed_defaults_creates_due_items(tmp_path):
    db_path = tmp_path / "freshness.sqlite"

    result = seed_defaults(include_cron=False, db_path=db_path)
    due = due_items(limit=5, db_path=db_path)

    assert result["default_count"] > 5
    assert db_path.exists()
    assert due
    assert due[0]["is_due"] is True
    assert "key" in due[0]
    assert "overdue_score" in due[0]


def test_record_completion_sets_next_due_and_event_history(tmp_path):
    db_path = tmp_path / "freshness.sqlite"

    item = record_completion(
        "docs:configmap-embeds",
        status="ok",
        evidence="scripts/sync_configmap_embeds.py --check passed",
        actor="putter",
        cadence_seconds=3600,
        db_path=db_path,
    )
    explained = explain_item("docs:configmap-embeds", db_path=db_path)

    assert item["last_status"] == "ok"
    assert item["is_due"] is False
    assert item["next_due_at"] is not None
    assert explained["events"][0]["actor"] == "putter"
    assert "sync_configmap" in explained["events"][0]["evidence"]


def test_snooze_suppresses_due_by_default(tmp_path):
    db_path = tmp_path / "freshness.sqlite"
    seed_defaults(include_cron=False, db_path=db_path)

    snooze_until = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    snoozed = snooze_item("upstream-sync:hermes-agent", snooze_until=snooze_until, db_path=db_path)
    due_keys = {item["key"] for item in due_items(db_path=db_path)}
    due_with_snoozed = {item["key"] for item in due_items(include_snoozed=True, db_path=db_path)}

    assert snoozed["is_snoozed"] is True
    assert "upstream-sync:hermes-agent" not in due_keys
    assert "upstream-sync:hermes-agent" in due_with_snoozed


def test_tool_wrapper_uses_profile_home(monkeypatch, tmp_path):
    home = tmp_path / "hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(home))

    seeded = json.loads(maintenance_freshness(action="seed", include_cron=False))
    recorded = json.loads(
        maintenance_freshness(
            action="record",
            key="tools:registry-smoke",
            status="ok",
            evidence="registry smoke passed",
            actor="test",
        )
    )
    listed = json.loads(maintenance_freshness(action="list", limit=3))

    assert seeded["success"] is True
    assert str(home) in seeded["db_path"]
    assert recorded["success"] is True
    assert recorded["item"]["last_status"] == "ok"
    assert listed["success"] is True
    assert listed["items"]


def test_list_orders_unseen_items_before_fresh_items(tmp_path):
    db_path = tmp_path / "freshness.sqlite"
    seed_defaults(include_cron=False, db_path=db_path)
    record_completion(
        "upstream-sync:hermes-agent",
        status="ok",
        evidence="checked upstream drift",
        actor="test",
        db_path=db_path,
    )

    items = list_items(limit=100, db_path=db_path)

    assert items[0]["key"] != "upstream-sync:hermes-agent"
    assert any(item["key"] == "upstream-sync:hermes-agent" and not item["is_due"] for item in items)
