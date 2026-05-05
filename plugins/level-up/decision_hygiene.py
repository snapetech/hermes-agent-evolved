"""Decision-log hygiene checks."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home


_WORD_RE = re.compile(r"[A-Za-z0-9_.\-/]{3,}")
_STOP = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "into", "then",
    "have", "has", "are", "was", "were", "been", "not", "but", "will",
    "can", "should", "use", "using", "used", "decision", "because",
})


def _decision_path() -> Path:
    return get_hermes_home() / "decision_memory" / "decisions.jsonl"


def _read_decisions() -> list[dict[str, Any]]:
    path = _decision_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except Exception:
            continue
    return rows


def _parse_ts(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0
    return 0.0


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if w not in _STOP}


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(4, min(len(a), len(b)))


def decision_hygiene_command(raw_args: str = "") -> str:
    """`/decision-hygiene` -- flag stale and likely-overlapping decisions."""
    rows = _read_decisions()
    if not rows:
        return "No decisions recorded yet."

    now = time.time()
    stale: list[dict[str, Any]] = []
    for row in rows:
        ts = _parse_ts(row.get("updated_at") or row.get("ts"))
        if ts and now - ts > 90 * 24 * 3600:
            stale.append(row)

    tail = rows[-50:]
    overlaps: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    tokenized = [(_tokens(str(row.get("decision") or row.get("text") or "")), row) for row in tail]
    for i, (left_tokens, left) in enumerate(tokenized):
        for right_tokens, right in tokenized[i + 1:]:
            score = _overlap(left_tokens, right_tokens)
            if score >= 0.55:
                overlaps.append((score, left, right))
    overlaps.sort(key=lambda item: item[0], reverse=True)

    if not stale and not overlaps:
        return f"Decision hygiene clean: {len(rows)} decisions checked."

    lines = [f"Decision hygiene: {len(rows)} decisions checked."]
    if stale:
        lines.append(f"Stale decisions (>90 days): {len(stale)}")
        for row in stale[-10:]:
            ts = row.get("updated_at") or row.get("ts") or "unknown"
            text = str(row.get("decision") or row.get("text") or "")[:160]
            lines.append(f"- {ts}: {text}")
    if overlaps:
        lines.append("Probable overlaps/contradictions in last 50:")
        for score, left, right in overlaps[:10]:
            ltext = str(left.get("decision") or left.get("text") or "")[:100]
            rtext = str(right.get("decision") or right.get("text") or "")[:100]
            lines.append(f"- score={score:.2f}: {ltext} / {rtext}")
    return "\n".join(lines)
