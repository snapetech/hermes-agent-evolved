"""Tool wrapper for the Hermes maintenance freshness ledger."""

from __future__ import annotations

import json

from tools.maintenance_freshness import (
    due_items,
    explain_item,
    list_items,
    record_completion,
    seed_defaults,
    snooze_item,
    upsert_item,
)
from tools.registry import registry


def maintenance_freshness(
    action: str = "due",
    key: str = "",
    kind: str = "",
    title: str = "",
    cadence_seconds: int | None = None,
    importance: float = 0.5,
    risk: float = 0.5,
    status: str = "ok",
    evidence: str = "",
    actor: str = "",
    run_id: str = "",
    metadata: dict | None = None,
    limit: int = 20,
    include_snoozed: bool = False,
    snooze_until: str = "",
    snooze_seconds: int | None = None,
    include_cron: bool = True,
) -> str:
    action = (action or "due").strip().lower()
    metadata = metadata if isinstance(metadata, dict) else {}
    try:
        if action == "seed":
            seeded = seed_defaults(include_cron=include_cron)
            return json.dumps({"success": True, "action": action, **seeded}, ensure_ascii=False)
        if action == "list":
            return json.dumps(
                {
                    "success": True,
                    "action": action,
                    "items": list_items(
                        kind=kind or None,
                        include_snoozed=include_snoozed,
                        limit=limit,
                    ),
                },
                ensure_ascii=False,
            )
        if action == "due":
            return json.dumps(
                {
                    "success": True,
                    "action": action,
                    "items": due_items(
                        kind=kind or None,
                        include_snoozed=include_snoozed,
                        limit=limit,
                    ),
                },
                ensure_ascii=False,
            )
        if action == "record":
            return json.dumps(
                {
                    "success": True,
                    "action": action,
                    "item": record_completion(
                        key,
                        status=status,
                        evidence=evidence,
                        actor=actor,
                        run_id=run_id,
                        kind=kind or "maintenance",
                        title=title or None,
                        cadence_seconds=cadence_seconds,
                        importance=importance,
                        risk=risk,
                        metadata=metadata,
                    ),
                },
                ensure_ascii=False,
            )
        if action == "upsert":
            return json.dumps(
                {
                    "success": True,
                    "action": action,
                    "item": upsert_item(
                        key,
                        kind=kind or "maintenance",
                        title=title or key,
                        cadence_seconds=cadence_seconds,
                        importance=importance,
                        risk=risk,
                        metadata=metadata,
                    ),
                },
                ensure_ascii=False,
            )
        if action == "snooze":
            return json.dumps(
                {
                    "success": True,
                    "action": action,
                    "item": snooze_item(
                        key,
                        snooze_until=snooze_until or None,
                        snooze_seconds=snooze_seconds,
                    ),
                },
                ensure_ascii=False,
            )
        if action == "explain":
            return json.dumps(
                {
                    "success": True,
                    "action": action,
                    "item": explain_item(key, limit=limit),
                },
                ensure_ascii=False,
            )
        return json.dumps({"success": False, "error": f"Unknown action: {action}"}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps(
            {"success": False, "error": f"{type(exc).__name__}: {exc}"},
            ensure_ascii=False,
        )


registry.register(
    name="maintenance_freshness",
    toolset="terminal",
    schema={
        "name": "maintenance_freshness",
        "description": (
            "Track and query durable maintenance freshness across Putter, cron, self-review, "
            "runtime installs, upstream syncs, audits, docs, skills, and model-routing checks. "
            "Use seed first on a new profile, due to pick stale work, and record after completing maintenance."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["seed", "list", "due", "record", "upsert", "snooze", "explain"],
                    "description": "Operation to run. seed creates default items and imports cron state. due lists stale priorities. record marks completed work.",
                    "default": "due",
                },
                "key": {
                    "type": "string",
                    "description": "Stable item key such as upstream-sync:hermes-agent, runtime-installs:promote, or cron:<job-id>.",
                },
                "kind": {
                    "type": "string",
                    "description": "Optional category filter or item category: update, tooling, security, ops, memory, introspection, research, docs, skills, tools, models, cron.",
                },
                "title": {"type": "string", "description": "Human title for upsert or first record."},
                "cadence_seconds": {
                    "type": "integer",
                    "description": "Expected freshness cadence. Used to compute next_due_at and overdue score.",
                },
                "importance": {
                    "type": "number",
                    "description": "Priority multiplier from 0.0 to 1.0. Higher means stale items rank sooner.",
                    "default": 0.5,
                },
                "risk": {
                    "type": "number",
                    "description": "Neglect-risk multiplier from 0.0 to 1.0. Higher means stale items rank sooner.",
                    "default": 0.5,
                },
                "status": {
                    "type": "string",
                    "description": "Completion status for record, usually ok, blocked, skipped, failed, or proposed.",
                    "default": "ok",
                },
                "evidence": {
                    "type": "string",
                    "description": "Short durable evidence for record, e.g. report path, commit hash, command result, or reason blocked.",
                },
                "actor": {"type": "string", "description": "Who/what recorded the event, e.g. putter, cron, operator."},
                "run_id": {"type": "string", "description": "Optional session, cron, or task id associated with this event."},
                "metadata": {
                    "type": "object",
                    "description": "Small JSON object for item-specific details. Keep it compact.",
                    "additionalProperties": True,
                },
                "limit": {"type": "integer", "description": "Max items/events to return.", "default": 20},
                "include_snoozed": {
                    "type": "boolean",
                    "description": "Include currently snoozed items in list/due output.",
                    "default": False,
                },
                "snooze_until": {
                    "type": "string",
                    "description": "ISO timestamp to snooze an item until. Alternative to snooze_seconds.",
                },
                "snooze_seconds": {
                    "type": "integer",
                    "description": "Relative snooze duration in seconds. Defaults to one day for snooze.",
                },
                "include_cron": {
                    "type": "boolean",
                    "description": "For seed, import cron/jobs.json into cron:<job-id> freshness items.",
                    "default": True,
                },
            },
            "required": ["action"],
        },
    },
    handler=lambda args, **_kw: maintenance_freshness(
        action=args.get("action", "due"),
        key=args.get("key", ""),
        kind=args.get("kind", ""),
        title=args.get("title", ""),
        cadence_seconds=args.get("cadence_seconds"),
        importance=args.get("importance", 0.5),
        risk=args.get("risk", 0.5),
        status=args.get("status", "ok"),
        evidence=args.get("evidence", ""),
        actor=args.get("actor", ""),
        run_id=args.get("run_id", ""),
        metadata=args.get("metadata"),
        limit=args.get("limit", 20),
        include_snoozed=args.get("include_snoozed", False),
        snooze_until=args.get("snooze_until", ""),
        snooze_seconds=args.get("snooze_seconds"),
        include_cron=args.get("include_cron", True),
    ),
    check_fn=lambda: True,
    emoji="🧭",
    max_result_size_chars=80_000,
)
