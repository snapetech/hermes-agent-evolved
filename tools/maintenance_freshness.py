"""Durable freshness ledger for recurring Hermes maintenance work."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home


UTC = timezone.utc


@dataclass(frozen=True)
class FreshnessItem:
    key: str
    kind: str
    title: str
    cadence_seconds: int | None
    importance: float
    risk: float
    metadata: dict[str, Any]


DEFAULT_ITEMS: tuple[FreshnessItem, ...] = (
    FreshnessItem(
        "upstream-sync:hermes-agent",
        "update",
        "Review upstream Hermes Agent drift and sync our fork when appropriate",
        7 * 24 * 3600,
        0.95,
        0.85,
        {"suggested_tool": "hermes-upstream-sync skill", "evidence": "git rev-list HEAD..origin/main"},
    ),
    FreshnessItem(
        "runtime-installs:promote",
        "tooling",
        "Review runtime apt/pip/npm installs and promote useful packages into declarative lists",
        3 * 24 * 3600,
        0.8,
        0.55,
        {"suggested_tool": "runtime_installs(action=\"list\")"},
    ),
    FreshnessItem(
        "stack-audit:cve",
        "security",
        "Refresh stack inventory and conservative CVE audit",
        7 * 24 * 3600,
        0.95,
        0.9,
        {"suggested_tool": "stack_audit(action=\"audit\")"},
    ),
    FreshnessItem(
        "resource-review:k3s",
        "ops",
        "Review Kubernetes resource requests, limits, restarts, and usage drift",
        7 * 24 * 3600,
        0.75,
        0.75,
        {"report_dir": "$HERMES_HOME/self-improvement/resource-review/reports"},
    ),
    FreshnessItem(
        "memory:hygiene",
        "memory",
        "Review memory for noisy task-progress entries and promote durable facts",
        7 * 24 * 3600,
        0.7,
        0.55,
        {"paths": ["$HERMES_HOME/memories/MEMORY.md", "$HERMES_HOME/memories/USER.md"]},
    ),
    FreshnessItem(
        "introspection:self-review",
        "introspection",
        "Run or inspect Hermes introspection and convert repeated friction into scoped fixes",
        3 * 24 * 3600,
        0.85,
        0.7,
        {"report": "$HERMES_HOME/self-improvement/introspection/reports/latest.md"},
    ),
    FreshnessItem(
        "edge-watch:quick",
        "research",
        "Inspect quick edge-watch findings for high-signal actionable changes",
        12 * 3600,
        0.65,
        0.35,
        {"report_dir": "$HERMES_HOME/self-improvement/reports"},
    ),
    FreshnessItem(
        "edge-watch:daily",
        "research",
        "Inspect daily edge-watch digest for upstream, model, tooling, and ecosystem changes",
        36 * 3600,
        0.75,
        0.45,
        {"report_dir": "$HERMES_HOME/self-improvement/reports"},
    ),
    FreshnessItem(
        "edge-watch:weekly",
        "research",
        "Review weekly edge-watch roll-up and decide which improvements deserve follow-up",
        8 * 24 * 3600,
        0.8,
        0.5,
        {"report_dir": "$HERMES_HOME/self-improvement/reports"},
    ),
    FreshnessItem(
        "docs:configmap-embeds",
        "docs",
        "Verify Kubernetes ConfigMap-embedded docs/scripts match their checked-in sources",
        7 * 24 * 3600,
        0.7,
        0.45,
        {"command": "python scripts/sync_configmap_embeds.py --check"},
    ),
    FreshnessItem(
        "skills:review",
        "skills",
        "Review stale or frequently used skills for missing guardrails, validation, and troubleshooting",
        14 * 24 * 3600,
        0.65,
        0.4,
        {"paths": ["skills/", "$HERMES_HOME/skills/"]},
    ),
    FreshnessItem(
        "tools:registry-smoke",
        "tools",
        "Smoke-check tool registry discovery and high-value tool availability",
        7 * 24 * 3600,
        0.7,
        0.5,
        {"surface": "model_tools.get_tool_definitions"},
    ),
    FreshnessItem(
        "model-benchmark:local-utility",
        "models",
        "Re-check local/free model routing utility against current task mix and external cost pressure",
        14 * 24 * 3600,
        0.65,
        0.45,
        {"focus": "qwen local, Kilo freebies, Codex, Claude budget"},
    ),
    FreshnessItem(
        "reproducibility:live-audit",
        "ops",
        "Audit live pod image, repo checkout, config embeds, and runtime persistence against git",
        7 * 24 * 3600,
        0.85,
        0.8,
        {"target": "hermes-gateway pod"},
    ),
)


def _db_path() -> Path:
    return get_hermes_home() / "maintenance" / "freshness.sqlite"


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            key TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            cadence_seconds INTEGER,
            importance REAL NOT NULL DEFAULT 0.5,
            risk REAL NOT NULL DEFAULT 0.5,
            last_done_at TEXT,
            last_status TEXT,
            last_evidence TEXT,
            next_due_at TEXT,
            snoozed_until TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_key TEXT NOT NULL,
            ts TEXT NOT NULL,
            status TEXT NOT NULL,
            evidence TEXT,
            actor TEXT,
            run_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_freshness_kind ON items(kind)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_freshness_events_item ON events(item_key, ts)")
    return conn


def _compute_next_due(last_done_at: str | None, cadence_seconds: int | None) -> str | None:
    if not cadence_seconds:
        return None
    base = _parse_dt(last_done_at)
    if base is None:
        return None
    return _iso(base + timedelta(seconds=int(cadence_seconds)))


def _row_to_item(row: sqlite3.Row, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or _now()
    cadence = row["cadence_seconds"]
    last_done = _parse_dt(row["last_done_at"])
    next_due = _parse_dt(row["next_due_at"])
    snoozed_until = _parse_dt(row["snoozed_until"])
    if next_due is None and cadence and last_done:
        next_due = last_done + timedelta(seconds=int(cadence))

    is_snoozed = bool(snoozed_until and snoozed_until > current)
    is_due = False
    overdue_seconds = 0.0
    if not is_snoozed:
        if next_due:
            overdue_seconds = (current - next_due).total_seconds()
            is_due = overdue_seconds >= 0
        elif last_done is None:
            is_due = True
            overdue_seconds = float(cadence or 86400)

    if cadence:
        if last_done:
            age_ratio = max(0.0, (current - last_done).total_seconds() / float(cadence))
        elif next_due:
            age_ratio = max(0.0, 1.0 + (current - next_due).total_seconds() / float(cadence))
        else:
            age_ratio = 2.0
    else:
        age_ratio = 1.0 if is_due else 0.0

    importance = float(row["importance"])
    risk = float(row["risk"])
    overdue_score = round(max(0.0, age_ratio) * (0.6 + importance) * (0.5 + risk), 4)

    return {
        "key": row["key"],
        "kind": row["kind"],
        "title": row["title"],
        "cadence_seconds": cadence,
        "importance": importance,
        "risk": risk,
        "last_done_at": row["last_done_at"],
        "last_status": row["last_status"],
        "last_evidence": row["last_evidence"],
        "next_due_at": _iso(next_due),
        "snoozed_until": row["snoozed_until"],
        "is_snoozed": is_snoozed,
        "is_due": is_due,
        "overdue_seconds": int(max(0, overdue_seconds)),
        "age_ratio": round(age_ratio, 4),
        "overdue_score": overdue_score,
        "metadata": _json_loads(row["metadata_json"]),
        "updated_at": row["updated_at"],
    }


def upsert_item(
    key: str,
    *,
    kind: str,
    title: str,
    cadence_seconds: int | None = None,
    importance: float = 0.5,
    risk: float = 0.5,
    last_done_at: str | None = None,
    last_status: str | None = None,
    last_evidence: str | None = None,
    next_due_at: str | None = None,
    metadata: dict[str, Any] | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Create or update an item without overwriting observed completion fields with nulls."""
    key = key.strip()
    if not key:
        raise ValueError("key is required")
    kind = (kind or "maintenance").strip()
    title = (title or key).strip()
    now = _iso(_now())
    next_due_at = next_due_at or _compute_next_due(last_done_at, cadence_seconds)
    metadata_json = json.dumps(metadata or {}, sort_keys=True)

    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO items (
                key, kind, title, cadence_seconds, importance, risk,
                last_done_at, last_status, last_evidence, next_due_at,
                snoozed_until, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                kind = excluded.kind,
                title = excluded.title,
                cadence_seconds = excluded.cadence_seconds,
                importance = excluded.importance,
                risk = excluded.risk,
                last_done_at = COALESCE(excluded.last_done_at, items.last_done_at),
                last_status = COALESCE(excluded.last_status, items.last_status),
                last_evidence = COALESCE(excluded.last_evidence, items.last_evidence),
                next_due_at = COALESCE(excluded.next_due_at, items.next_due_at),
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                key,
                kind,
                title,
                cadence_seconds,
                importance,
                risk,
                last_done_at,
                last_status,
                last_evidence,
                next_due_at,
                metadata_json,
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM items WHERE key = ?", (key,)).fetchone()
    return _row_to_item(row)


def record_completion(
    key: str,
    *,
    status: str = "ok",
    evidence: str = "",
    actor: str = "",
    run_id: str = "",
    kind: str = "maintenance",
    title: str | None = None,
    cadence_seconds: int | None = None,
    importance: float = 0.5,
    risk: float = 0.5,
    metadata: dict[str, Any] | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    key = key.strip()
    if not key:
        raise ValueError("key is required")
    ts = _iso(_now())
    status = (status or "ok").strip().lower()
    with _connect(db_path) as conn:
        existing = conn.execute("SELECT * FROM items WHERE key = ?", (key,)).fetchone()
        if existing:
            cadence = cadence_seconds if cadence_seconds is not None else existing["cadence_seconds"]
            merged_metadata = _json_loads(existing["metadata_json"])
            merged_metadata.update(metadata or {})
            item_title = title or existing["title"]
            item_kind = kind if kind != "maintenance" else existing["kind"]
            item_importance = importance if importance != 0.5 else float(existing["importance"])
            item_risk = risk if risk != 0.5 else float(existing["risk"])
        else:
            cadence = cadence_seconds
            merged_metadata = metadata or {}
            item_title = title or key
            item_kind = kind
            item_importance = importance
            item_risk = risk
        next_due = _compute_next_due(ts, cadence)
        metadata_json = json.dumps(merged_metadata, sort_keys=True)
        conn.execute(
            """
            INSERT INTO items (
                key, kind, title, cadence_seconds, importance, risk,
                last_done_at, last_status, last_evidence, next_due_at,
                snoozed_until, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                kind = excluded.kind,
                title = excluded.title,
                cadence_seconds = excluded.cadence_seconds,
                importance = excluded.importance,
                risk = excluded.risk,
                last_done_at = excluded.last_done_at,
                last_status = excluded.last_status,
                last_evidence = excluded.last_evidence,
                next_due_at = excluded.next_due_at,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                key,
                item_kind,
                item_title,
                cadence,
                item_importance,
                item_risk,
                ts,
                status,
                evidence or None,
                next_due,
                metadata_json,
                ts,
                ts,
            ),
        )
        conn.execute(
            """
            INSERT INTO events (item_key, ts, status, evidence, actor, run_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (key, ts, status, evidence or None, actor or None, run_id or None, json.dumps(metadata or {}, sort_keys=True)),
        )
        row = conn.execute("SELECT * FROM items WHERE key = ?", (key,)).fetchone()
    return _row_to_item(row)


def snooze_item(
    key: str,
    *,
    snooze_until: str | None = None,
    snooze_seconds: int | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    if not key:
        raise ValueError("key is required")
    until = _parse_dt(snooze_until)
    if until is None:
        until = _now() + timedelta(seconds=int(snooze_seconds or 24 * 3600))
    now = _iso(_now())
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM items WHERE key = ?", (key,)).fetchone()
        if row is None:
            raise KeyError(f"unknown freshness item: {key}")
        conn.execute(
            "UPDATE items SET snoozed_until = ?, updated_at = ? WHERE key = ?",
            (_iso(until), now, key),
        )
        row = conn.execute("SELECT * FROM items WHERE key = ?", (key,)).fetchone()
    return _row_to_item(row)


def list_items(
    *,
    kind: str | None = None,
    include_snoozed: bool = True,
    limit: int = 50,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM items"
    params: list[Any] = []
    if kind:
        query += " WHERE kind = ?"
        params.append(kind)
    with _connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    items = [_row_to_item(row) for row in rows]
    if not include_snoozed:
        items = [item for item in items if not item["is_snoozed"]]
    items.sort(key=lambda item: (not item["is_due"], -item["overdue_score"], item.get("next_due_at") or "", item["key"]))
    return items[: max(1, int(limit))]


def due_items(
    *,
    kind: str | None = None,
    include_snoozed: bool = False,
    limit: int = 20,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    return [
        item
        for item in list_items(kind=kind, include_snoozed=include_snoozed, limit=500, db_path=db_path)
        if item["is_due"] or (include_snoozed and item["is_snoozed"])
    ][: max(1, int(limit))]


def explain_item(key: str, *, limit: int = 20, db_path: Path | None = None) -> dict[str, Any]:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM items WHERE key = ?", (key,)).fetchone()
        if row is None:
            raise KeyError(f"unknown freshness item: {key}")
        events = conn.execute(
            "SELECT * FROM events WHERE item_key = ? ORDER BY ts DESC, id DESC LIMIT ?",
            (key, max(1, int(limit))),
        ).fetchall()
    item = _row_to_item(row)
    item["events"] = [
        {
            "id": event["id"],
            "ts": event["ts"],
            "status": event["status"],
            "evidence": event["evidence"],
            "actor": event["actor"],
            "run_id": event["run_id"],
            "metadata": _json_loads(event["metadata_json"]),
        }
        for event in events
    ]
    return item


def _cron_cadence_seconds(schedule: dict[str, Any]) -> int | None:
    if not isinstance(schedule, dict):
        return None
    if schedule.get("kind") == "interval":
        minutes = schedule.get("minutes")
        try:
            return int(minutes) * 60
        except (TypeError, ValueError):
            return None
    return None


def sync_cron_items(*, db_path: Path | None = None) -> int:
    try:
        from cron.jobs import list_jobs
    except Exception:
        return 0

    count = 0
    try:
        jobs = list_jobs(include_disabled=True)
    except TypeError:
        jobs = list_jobs()
    except Exception:
        return 0

    for job in jobs or []:
        if not isinstance(job, dict) or not job.get("id"):
            continue
        schedule = job.get("schedule") or {}
        key = f"cron:{job['id']}"
        title = str(job.get("name") or job.get("prompt") or job["id"]).strip().splitlines()[0][:120]
        metadata = {
            "enabled": job.get("enabled"),
            "state": job.get("state"),
            "schedule": schedule,
            "repeat": job.get("repeat"),
            "source": "cron/jobs.json",
        }
        upsert_item(
            key,
            kind="cron",
            title=f"Cron: {title}",
            cadence_seconds=_cron_cadence_seconds(schedule),
            importance=0.7,
            risk=0.45,
            last_done_at=job.get("last_run_at"),
            last_status=job.get("last_status"),
            last_evidence=job.get("last_error") or job.get("last_delivery_error"),
            next_due_at=job.get("next_run_at"),
            metadata=metadata,
            db_path=db_path,
        )
        count += 1
    return count


def seed_defaults(*, include_cron: bool = True, db_path: Path | None = None) -> dict[str, Any]:
    for item in DEFAULT_ITEMS:
        upsert_item(
            item.key,
            kind=item.kind,
            title=item.title,
            cadence_seconds=item.cadence_seconds,
            importance=item.importance,
            risk=item.risk,
            metadata=item.metadata,
            db_path=db_path,
        )
    cron_count = sync_cron_items(db_path=db_path) if include_cron else 0
    return {
        "default_count": len(DEFAULT_ITEMS),
        "cron_count": cron_count,
        "db_path": str(db_path or _db_path()),
    }
