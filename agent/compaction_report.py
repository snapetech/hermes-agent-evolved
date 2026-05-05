"""Helpers for loading and formatting session compaction telemetry."""

from __future__ import annotations

import json
import glob
import os
from pathlib import Path
from typing import Any, Optional

from hermes_constants import get_hermes_home


def session_log_path(session_id: str) -> Path:
    """Return the JSON session-log path for a Hermes session ID."""
    return get_hermes_home() / "sessions" / f"session_{session_id}.json"


def load_session_compaction_data(session_id: str) -> Optional[dict[str, Any]]:
    """Load compaction metrics/events from the persisted session log."""
    path = session_log_path(session_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return {
        "session_id": session_id,
        "path": path,
        "compaction_metrics": payload.get("compaction_metrics") or {},
        "compaction_events": payload.get("compaction_events") or [],
    }


def resolve_session_reference(
    session_db: Any,
    raw_reference: Optional[str],
    *,
    current_session_id: Optional[str] = None,
) -> Optional[str]:
    """Resolve an optional session selector to a concrete session ID.

    Resolution order:
    - current session when no selector is given
    - exact session ID
    - exact title via SessionDB
    - unique session-id prefix among persisted session logs
    """
    ref = (raw_reference or "").strip()
    if not ref:
        return current_session_id

    if session_db is not None:
        try:
            session = session_db.get_session(ref)
        except Exception:
            session = None
        if session and session.get("id"):
            return str(session["id"])
        try:
            titled = session_db.get_session_by_title(ref)
        except Exception:
            titled = None
        if titled and titled.get("id"):
            return str(titled["id"])

    pattern = str(get_hermes_home() / "sessions" / f"session_{ref}*.json")
    matches = sorted(glob.glob(pattern))
    if len(matches) == 1:
        name = os.path.basename(matches[0])
        if name.startswith("session_") and name.endswith(".json"):
            return name[len("session_") : -len(".json")]
    return ref


def parse_compaction_command_args(raw_args: str) -> tuple[int, Optional[str], Optional[str]]:
    """Parse `/compaction` arguments.

    Supports:
    - `/compaction`
    - `/compaction 10`
    - `/compaction --session <id-or-title>`
    - `/compaction 10 --session <id-or-title>`

    Returns `(limit, session_ref, error)`.
    """
    parts = [part for part in (raw_args or "").split() if part]
    limit = 5
    session_ref: Optional[str] = None
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == "--session":
            if i + 1 >= len(parts):
                return limit, session_ref, "Missing value for --session"
            session_ref = parts[i + 1]
            i += 2
            continue
        if part.isdigit():
            limit = max(1, int(part))
            i += 1
            continue
        return limit, session_ref, f"Unrecognized argument: {part}"
    return limit, session_ref, None


def build_live_compaction_data(agent: Any) -> dict[str, Any]:
    """Build a compaction snapshot from a live agent instance."""
    metrics = {}
    if hasattr(agent, "_build_compaction_metrics"):
        try:
            metrics = agent._build_compaction_metrics() or {}
        except Exception:
            metrics = {}
    events = list(getattr(agent, "_compaction_events", []) or [])
    return {
        "session_id": getattr(agent, "session_id", None),
        "path": getattr(agent, "session_log_file", None),
        "compaction_metrics": metrics,
        "compaction_events": events,
    }


def _fmt_kv_map(mapping: dict[str, Any]) -> str:
    if not mapping:
        return "none"
    return ", ".join(f"{key}={mapping[key]}" for key in sorted(mapping))


def _format_event_line(event: dict[str, Any]) -> str:
    source = event.get("source") or "unknown"
    trigger = event.get("trigger") or "unknown"
    parts = [f"{source}/{trigger}"]

    est = event.get("estimated_input_tokens")
    maximum = event.get("max_input_tokens")
    if isinstance(est, int) and isinstance(maximum, int):
        parts.append(f"{est:,}>{maximum:,}")

    before = event.get("pre_message_count")
    after = event.get("post_message_count")
    if before not in (None, "") and after not in (None, ""):
        parts.append(f"msgs {before}->{after}")

    tok_before = event.get("approx_tokens_before")
    tok_after = event.get("approx_tokens_after")
    if tok_before not in (None, "") and tok_after not in (None, ""):
        try:
            parts.append(f"tok ~{int(tok_before):,}->{int(tok_after):,}")
        except (TypeError, ValueError):
            parts.append(f"tok ~{tok_before}->{tok_after}")

    attempt = event.get("compression_attempt")
    if attempt not in (None, ""):
        parts.append(f"attempt {attempt}")
    artifact_id = event.get("artifact_id")
    if artifact_id not in (None, ""):
        parts.append(f"artifact {artifact_id}")
    validation = event.get("summary_validation_valid")
    if validation is False:
        parts.append("validation missing")

    timestamp = event.get("timestamp")
    if timestamp:
        parts.append(str(timestamp))

    return " | ".join(parts)


def format_compaction_report(
    data: Optional[dict[str, Any]],
    *,
    limit: int = 5,
    markdown: bool = False,
) -> str:
    """Render a human-readable compaction summary."""
    if not data:
        return (
            "No compaction telemetry found for this session."
            if not markdown
            else "No compaction telemetry found for this session."
        )

    metrics = data.get("compaction_metrics") or {}
    events = list(data.get("compaction_events") or [])
    session_id = data.get("session_id") or "unknown"

    if markdown:
        lines = [
            "🗜️ **Compaction Report**",
            f"Session: `{session_id}`",
            f"Events: {metrics.get('event_count', len(events))}",
            f"By source: {_fmt_kv_map(metrics.get('by_source') or {})}",
            f"By trigger: {_fmt_kv_map(metrics.get('by_trigger') or {})}",
        ]
        proxy_count = metrics.get("proxy_overflow_compactions")
        if proxy_count:
            lines.append(f"Admission-proxy retries: {proxy_count}")
        if metrics.get("with_artifacts"):
            lines.append(f"Artifacts: {metrics.get('with_artifacts')}")
        if metrics.get("summary_validation_failures"):
            lines.append(f"Validation warnings: {metrics.get('summary_validation_failures')}")
        if not events:
            lines.append("No compaction events recorded.")
            return "\n".join(lines)
        lines.append("")
        lines.append("Recent events:")
        for event in events[-max(1, limit):]:
            lines.append(f"- {_format_event_line(event)}")
        return "\n".join(lines)

    lines = [
        "  🗜️ Compaction Report",
        f"  {'─' * 40}",
        f"  Session:                  {session_id}",
        f"  Events:                   {metrics.get('event_count', len(events))}",
        f"  By source:                {_fmt_kv_map(metrics.get('by_source') or {})}",
        f"  By trigger:               {_fmt_kv_map(metrics.get('by_trigger') or {})}",
    ]
    proxy_count = metrics.get("proxy_overflow_compactions")
    if proxy_count:
        lines.append(f"  Proxy retry compactions:   {proxy_count}")
    if metrics.get("with_artifacts"):
        lines.append(f"  Archived artifacts:        {metrics.get('with_artifacts')}")
    if metrics.get("summary_validation_failures"):
        lines.append(f"  Validation warnings:       {metrics.get('summary_validation_failures')}")
    if not events:
        lines.append("  Recent events:            none")
        return "\n".join(lines)
    lines.append("  Recent events:")
    for event in events[-max(1, limit):]:
        lines.append(f"    - {_format_event_line(event)}")
    return "\n".join(lines)
