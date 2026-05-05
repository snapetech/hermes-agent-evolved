#!/usr/bin/env python3
"""Build bounded context for the state-reflection cron job.

The cron agent should not read whole harvest files into model context. This
script summarizes counts, recent samples, duplicate candidates, and MEMORY.md
presence so the model can decide whether there is anything worth reporting.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


HERMES_HOME = Path(__import__("os").environ.get("HERMES_HOME", "/opt/data"))
HARVEST_DIR = HERMES_HOME / "level_up" / "harvest"
MEMORY = HERMES_HOME / "MEMORY.md"
MAX_SAMPLES = 5
MAX_TEXT = 240
SECRET_PATTERNS = (
    re.compile(r"(?i)(credentials?\s+)(?:are|is|=|:)\s+\S+(?:\s*/\s*\S+)?"),
    re.compile(r"(?i)(uses\s+credentials?\s+)\S+(?:\s*/\s*\S+)?"),
    re.compile(r"(?i)(password\s+)(?:is|=|:)\s+\S+"),
    re.compile(r"(?i)(token|secret|api[_ -]?key)(\s*[:=]\s*)\S+"),
)


def _redact(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda m: f"{m.group(1)}[REDACTED]", redacted)
    return redacted


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            item = {"parse_error": line[:MAX_TEXT]}
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _text_for(kind: str, item: dict) -> str:
    key = {"facts": "fact", "avoid": "avoid", "corrections": "fix"}.get(kind, "text")
    text = str(item.get(key) or item.get("text") or item)
    return _redact(" ".join(text.split()))[:MAX_TEXT]


def _summarize(kind: str, path: Path) -> dict:
    rows = _load_jsonl(path)
    statuses = Counter(str(row.get("status", "missing")) for row in rows)
    normalized = Counter(_text_for(kind, row).lower() for row in rows)
    duplicates = [text for text, count in normalized.items() if count > 1][:MAX_SAMPLES]
    return {
        "file": str(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
        "rows": len(rows),
        "statuses": dict(statuses),
        "recent_samples": [_text_for(kind, row) for row in rows[-MAX_SAMPLES:]],
        "duplicate_candidates": duplicates,
    }


def main() -> int:
    report = {
        "purpose": "Bounded state-reflection context. Do not read full harvest files unless this summary identifies a specific small item to inspect.",
        "harvest": {
            "facts": _summarize("facts", HARVEST_DIR / "facts.jsonl"),
            "avoid": _summarize("avoid", HARVEST_DIR / "avoid.jsonl"),
            "corrections": _summarize("corrections", HARVEST_DIR / "corrections.jsonl"),
        },
        "memory": {
            "path": str(MEMORY),
            "exists": MEMORY.exists(),
            "bytes": MEMORY.stat().st_size if MEMORY.exists() else 0,
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
