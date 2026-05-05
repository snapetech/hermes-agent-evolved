"""Typed failure taxonomy and recovery recipes.

Ports claw-code-parity's RecoveryRecipe idea into a Hermes plugin. Tool
failures are classified into stable categories, each with an ordered list
of remediation steps. A post_tool_call hook records failures; a slash
command lets the operator inspect and manually trigger recovery.

State lives at `$HERMES_HOME/level_up/recovery.jsonl` as append-only JSONL.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

from .escalation import Escalation, escalate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

CATEGORIES: tuple[str, ...] = (
    "backend_timeout",
    "backend_unreachable",
    "tool_crash",
    "tool_output_invalid",
    "context_overflow",
    "strategy_exhausted",
    "approval_timeout",
    "workspace_conflict",
    "permission_denied",
    "network_error",
    "unknown",
)


RECIPES: dict[str, list[str]] = {
    "backend_timeout":      ["retry_same", "retry_different_backend", "escalate"],
    "backend_unreachable":  ["retry_different_backend", "escalate"],
    "tool_crash":           ["retry_same", "simplify_strategy", "escalate"],
    "tool_output_invalid":  ["simplify_strategy", "escalate"],
    "context_overflow":     ["compact_context", "retry_same", "escalate"],
    "strategy_exhausted":   ["escalate"],
    "approval_timeout":     ["escalate"],
    "workspace_conflict":   ["escalate"],
    "permission_denied":    ["escalate"],
    "network_error":        ["retry_same", "escalate"],
    "unknown":              ["retry_same", "escalate"],
}


_CLASSIFIERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\btimed?\s*out\b|\btimeout\b", re.I),                       "backend_timeout"),
    (re.compile(r"\bconnection\s+(refused|reset|aborted)\b|\benameservfail\b", re.I), "backend_unreachable"),
    (re.compile(r"\b(context|tokens?)\b.*\b(limit|exceed|overflow|too\s+long|window)\b", re.I), "context_overflow"),
    (re.compile(r"\bcontext_length_exceeded\b|\bmaximum context length\b", re.I), "context_overflow"),
    (re.compile(r"\b(permission|access)\s+denied\b|\bforbidden\b|\b403\b", re.I), "permission_denied"),
    (re.compile(r"\b(dns|resolve|socket|unreachable|temporary failure)\b", re.I), "network_error"),
    (re.compile(r"\bapproval\b.*\b(timed?\s*out|expired)\b", re.I),           "approval_timeout"),
    (re.compile(r"\bgit\b.*\b(merge|conflict|rebase|lock|index\.lock)\b", re.I), "workspace_conflict"),
    (re.compile(r"\b(json|decode|parse)\s+error\b|\bunexpected\s+token\b", re.I), "tool_output_invalid"),
    (re.compile(r"\btraceback\b|\bexception\b|\bstacktrace\b", re.I),          "tool_crash"),
    (re.compile(r"\bmax_?iterations?\b|\bloop\s+limit\b|\bstrategy\s+exhausted\b", re.I), "strategy_exhausted"),
)


def classify(message: str) -> str:
    """Classify a failure message into a stable category."""
    text = message or ""
    for pattern, category in _CLASSIFIERS:
        if pattern.search(text):
            return category
    return "unknown"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

@dataclass
class RecoveryEvent:
    ts: float
    tool_name: str
    category: str
    recipe: list[str]
    attempt: int
    step: str
    message_excerpt: str
    extra: dict[str, Any] = field(default_factory=dict)


def _recovery_path() -> Path:
    path = get_hermes_home() / "level_up" / "recovery.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append(event: RecoveryEvent) -> None:
    with _recovery_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")


def _recent_attempts(tool_name: str, category: str, within_seconds: int = 600) -> int:
    path = _recovery_path()
    if not path.exists():
        return 0
    cutoff = time.time() - within_seconds
    count = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-500:]:
            try:
                item = json.loads(line)
            except Exception:
                continue
            if item.get("tool_name") == tool_name and item.get("category") == category and item.get("ts", 0) >= cutoff:
                count += 1
    except Exception:
        return 0
    return count


# ---------------------------------------------------------------------------
# Hook integration
# ---------------------------------------------------------------------------

_ERROR_SENTINELS = ("error:", "failed:", "exception", "traceback", "\"error\":")


def _looks_like_failure(result: Any) -> tuple[bool, str]:
    """Best-effort detection of whether a tool result represents a failure."""
    if result is None:
        return False, ""
    text = result if isinstance(result, str) else str(result)
    lower = text.lower()

    # Hermes tools commonly return JSON with an explicit error/ok field.
    if text.lstrip().startswith("{"):
        try:
            data = json.loads(text)
        except Exception:
            data = None
        if isinstance(data, dict):
            if data.get("ok") is False:
                return True, text[:400]
            if data.get("error"):
                return True, text[:400]

    return (any(s in lower for s in _ERROR_SENTINELS), text[:400])


def post_tool_call_hook(tool_name: str = "", args: dict[str, Any] | None = None, result: Any = None, **_: Any) -> None:
    """Classify any failure, record it, and fire escalation when recipe exhausts."""
    failed, excerpt = _looks_like_failure(result)
    if not failed:
        return

    category = classify(excerpt)
    recipe = RECIPES.get(category, RECIPES["unknown"])
    attempt = _recent_attempts(tool_name, category) + 1
    # Clamp to the last slot when we've already cycled through the recipe.
    step = recipe[min(attempt - 1, len(recipe) - 1)]

    event = RecoveryEvent(
        ts=time.time(),
        tool_name=tool_name,
        category=category,
        recipe=list(recipe),
        attempt=attempt,
        step=step,
        message_excerpt=excerpt,
        extra={"args_keys": sorted((args or {}).keys())},
    )
    _append(event)

    if step == "escalate":
        escalate(
            Escalation(
                reason=f"{tool_name} failed with category={category} after {attempt} attempts",
                category=category,
                severity="error",
                details={
                    "tool": tool_name,
                    "attempt": attempt,
                    "recipe": list(recipe),
                    "excerpt": excerpt,
                },
            )
        )


# ---------------------------------------------------------------------------
# Slash command
# ---------------------------------------------------------------------------

def recovery_command(raw_args: str = "") -> str:
    """`/recovery [limit]` — show recent recovery events and recipe hits."""
    try:
        limit = max(1, min(50, int(raw_args.strip() or "10")))
    except ValueError:
        limit = 10

    path = _recovery_path()
    if not path.exists():
        return "No recovery events recorded yet."

    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    if not lines:
        return "No recovery events recorded yet."

    rows: list[str] = []
    for line in lines:
        try:
            item = json.loads(line)
        except Exception:
            rows.append(f"- {line}")
            continue
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item.get("ts", 0)))
        rows.append(
            f"- {ts} {item.get('tool_name')} → {item.get('category')} "
            f"[step={item.get('step')} attempt={item.get('attempt')}]"
        )
    return "\n".join(rows)
