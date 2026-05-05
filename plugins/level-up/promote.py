"""Promote harvested memories into live memory stores."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home


_KIND_FILES = {
    "fact": "facts.jsonl",
    "facts": "facts.jsonl",
    "user": "facts.jsonl",
    "correction": "corrections.jsonl",
    "corrections": "corrections.jsonl",
    "avoid": "avoid.jsonl",
    "avoids": "avoid.jsonl",
    "hindsight": "facts.jsonl",
}


def _harvest_dir() -> Path:
    return get_hermes_home() / "level_up" / "harvest"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                row.setdefault("_line", idx)
                rows.append(row)
        except Exception:
            continue
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            row = {k: v for k, v in row.items() if k != "_line"}
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def _select(rows: list[dict[str, Any]], item_id: str) -> tuple[int, dict[str, Any]] | None:
    wanted = item_id.strip()
    for idx, row in enumerate(rows):
        if str(row.get("id", "")).strip() == wanted:
            return idx, row
    try:
        line_no = int(wanted)
    except ValueError:
        return None
    for idx, row in enumerate(rows):
        if int(row.get("_line", -1)) == line_no:
            return idx, row
    return None


def _entry_text(kind: str, row: dict[str, Any]) -> str:
    if kind in {"fact", "facts", "user", "hindsight"}:
        return str(row.get("fact") or row.get("text") or row.get("content") or "").strip()
    if kind in {"correction", "corrections"}:
        context = str(row.get("context") or "").strip()
        fix = str(row.get("fix") or "").strip()
        return f"Correction: {context}\nFix: {fix}".strip()
    if kind in {"avoid", "avoids"}:
        return f"Avoid: {str(row.get('avoid') or row.get('text') or '').strip()}"
    return str(row.get("text") or row.get("content") or "").strip()


def _append_markdown(path: Path, heading: str, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    block = f"{prefix}\n## {heading}\n\n- {text.replace(chr(10), chr(10) + '  ')}\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(block)


def _promote_to_hindsight(text: str, kind: str) -> str:
    """Best-effort Hindsight retain, with a profile-local audit fallback."""
    try:
        from plugins.memory.hindsight import HindsightMemoryProvider

        provider = HindsightMemoryProvider()
        if provider.is_available():
            result = provider.handle_tool_call(
                "hindsight_retain",
                {"content": text, "context": f"promoted harvest {kind}"},
            )
            return f"Hindsight retain attempted: {result[:240]}"
    except Exception:
        pass

    path = get_hermes_home() / "level_up" / "hindsight_promotions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": time.time(), "kind": kind, "content": text}, ensure_ascii=False) + "\n")
    return f"Hindsight unavailable; wrote audit fallback to `{path}`."


def promote_command(raw_args: str = "") -> str:
    """`/promote <kind> <id> [memory|user|soul|hindsight]`."""
    parts = (raw_args or "").split()
    if len(parts) < 2:
        return "Usage: `/promote <fact|user|correction|avoid|hindsight> <line-or-id> [memory|user|soul|hindsight]`"

    kind = parts[0].strip().lower()
    item_id = parts[1].strip()
    target = parts[2].strip().lower() if len(parts) >= 3 else ""
    filename = _KIND_FILES.get(kind)
    if not filename:
        return f"Unknown promote kind `{kind}`. Use fact, user, correction, avoid, or hindsight."

    path = _harvest_dir() / filename
    rows = _read_jsonl(path)
    selected = _select(rows, item_id)
    if selected is None:
        return f"No `{kind}` harvest entry found for id/line `{item_id}` in `{path}`."

    idx, row = selected
    if row.get("status") == "promoted":
        return f"`{kind}` entry `{item_id}` is already promoted."

    text = _entry_text(kind, row)
    if not text:
        return f"`{kind}` entry `{item_id}` has no promotable text."

    if not target:
        if kind == "user":
            target = "user"
        elif kind == "hindsight":
            target = "hindsight"
        elif kind in {"correction", "corrections", "avoid", "avoids"}:
            target = "soul"
        else:
            target = "memory"

    home = get_hermes_home()
    if target == "memory":
        dest = home / "memories" / "MEMORY.md"
        _append_markdown(dest, "Promoted Harvest", text)
        detail = f"Appended to `{dest}`."
    elif target == "user":
        dest = home / "memories" / "USER.md"
        _append_markdown(dest, "Promoted User Memory", text)
        detail = f"Appended to `{dest}`."
    elif target == "soul":
        dest = home / "SOUL.md"
        _append_markdown(dest, "Promoted Operational Memory", text)
        detail = f"Appended to `{dest}`."
    elif target == "hindsight":
        detail = _promote_to_hindsight(text, kind)
    else:
        return "Target must be one of memory, user, soul, or hindsight."

    row["status"] = "promoted"
    row["promoted_ts"] = time.time()
    row["promoted_target"] = target
    rows[idx] = row
    _write_jsonl(path, rows)
    return f"Promoted `{kind}` entry `{item_id}`. {detail}"
