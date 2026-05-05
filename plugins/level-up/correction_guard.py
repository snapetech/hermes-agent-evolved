"""Correction-aware approval elevation.

Cross-references pending tool calls against previously-recorded corrections
and decisions. When a high-confidence match is found, the tool call is
blocked with a reminder so the operator (or the agent's own reasoning
step) can reconsider before proceeding.

Reads from:
  - `$HERMES_HOME/decision_memory/decisions.jsonl` (from runtime-control)
  - `$HERMES_HOME/level_up/harvest/corrections.jsonl` (from harvest.py)
  - `$HERMES_HOME/level_up/harvest/avoid.jsonl`

Scoring is term-overlap based — no model call, runs in milliseconds.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


_WORD_RE = re.compile(r"[A-Za-z0-9_.\-/]{3,}")
_STOP = frozenset({
    "the", "and", "for", "with", "that", "this", "when", "from", "into",
    "then", "have", "has", "are", "was", "were", "been", "not", "but",
    "you", "your", "our", "will", "can", "should", "any", "use", "used",
    "running", "done", "just", "set", "get",
})


def _tokens(text: str) -> set[str]:
    text = (text or "").lower()
    return {w for w in _WORD_RE.findall(text) if w not in _STOP and len(w) >= 3}


def _overlap_score(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(4, min(len(a), len(b)))


# ---------------------------------------------------------------------------
# Source readers
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path, cap: int = 500) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-cap:]
    except Exception:
        return []
    items: list[dict[str, Any]] = []
    for line in lines:
        try:
            items.append(json.loads(line))
        except Exception:
            continue
    return items


def _load_sources() -> list[dict[str, Any]]:
    home = get_hermes_home()
    entries: list[dict[str, Any]] = []

    for item in _read_jsonl(home / "decision_memory" / "decisions.jsonl"):
        entries.append({"kind": "decision", "text": item.get("decision", ""), "raw": item})

    for item in _read_jsonl(home / "level_up" / "harvest" / "corrections.jsonl"):
        entries.append({
            "kind": "correction",
            "text": f"{item.get('context','')} — {item.get('fix','')}",
            "raw": item,
        })

    for item in _read_jsonl(home / "level_up" / "harvest" / "avoid.jsonl"):
        entries.append({"kind": "avoid", "text": item.get("avoid", ""), "raw": item})

    return entries


# Lightweight cache so the hook doesn't re-read files on every tool call.
_CACHE: dict[str, Any] = {"ts": 0.0, "entries": []}
_CACHE_TTL = 30.0


def _sources() -> list[dict[str, Any]]:
    now = time.time()
    if now - _CACHE["ts"] < _CACHE_TTL and _CACHE["entries"]:
        return _CACHE["entries"]
    entries = _load_sources()
    _CACHE["ts"] = now
    _CACHE["entries"] = entries
    return entries


# ---------------------------------------------------------------------------
# Hook
# ---------------------------------------------------------------------------

# Only gate tools where reconsideration is cheap and relevant.
_GATED_TOOLS = frozenset({"terminal", "execute_code", "file_write", "edit_file", "write_file"})
_THRESHOLD = 0.45


def _is_runtime_package_install(tool_name: str, args: dict[str, Any]) -> bool:
    if tool_name != "terminal":
        return False
    command = args.get("command")
    if not isinstance(command, str) or not command.strip():
        return False
    try:
        from tools.approval import is_runtime_package_install_command
        return is_runtime_package_install_command(command)
    except Exception:
        return False


def pre_tool_call_hook(tool_name: str = "", args: dict[str, Any] | None = None, **_: Any) -> dict[str, str] | None:
    if tool_name not in _GATED_TOOLS:
        return None

    args = args if isinstance(args, dict) else {}
    if _is_runtime_package_install(tool_name, args):
        return None

    call_text_parts = [tool_name]
    for key in ("command", "code", "script", "path", "file_path", "content", "query"):
        value = args.get(key)
        if isinstance(value, str) and value:
            call_text_parts.append(value[:1000])
    call_tokens = _tokens(" ".join(call_text_parts))
    if not call_tokens:
        return None

    best_score = 0.0
    best_entry: dict[str, Any] | None = None
    for entry in _sources():
        score = _overlap_score(call_tokens, _tokens(entry.get("text") or ""))
        if score > best_score:
            best_score = score
            best_entry = entry

    if best_entry is None or best_score < _THRESHOLD:
        return None

    excerpt = (best_entry.get("text") or "")[:240]
    message = (
        f"level-up correction-guard: a prior {best_entry['kind']} overlaps this "
        f"call (score={best_score:.2f}). Re-read it before proceeding.\n"
        f"Prior note: {excerpt}"
    )
    return {"action": "block", "message": message}
