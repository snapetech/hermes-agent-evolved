"""Memory harvest on compaction.

Hermes' built-in compressor summarizes old turns but throws away the raw
content. This module runs a second pass over the most recent compressed
sessions and asks the same local model to extract durable facts and
corrections, which are queued for operator review under
`$HERMES_HOME/level_up/harvest/{facts,corrections}.jsonl`.

Designed to run as a cron job — see configmap.yaml for the template.
Also exposed as `/harvest [limit]` for manual runs.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


HARVEST_PROMPT = """You are reviewing a conversation between an operator and
Hermes Agent. Extract durable knowledge that should survive into long-term
memory. Be selective: only items that will be useful in future sessions.

Return ONLY a single JSON object with these keys (omit keys if empty):
{
  "facts":       ["stable facts about the operator, env, or codebase"],
  "corrections": [{"context": "where the model was wrong", "fix": "what's correct"}],
  "avoid":       ["patterns or commands that led to failure"]
}

Exclude: politeness, filler, transient debugging, raw tool output,
conversational repetition. The JSON object is the entire response — no
prose, no code fences.

---- Conversation excerpt ----
{excerpt}
---- End excerpt ----
"""


@dataclass
class HarvestResult:
    ts: float
    session_id: str
    facts: list[str] = field(default_factory=list)
    corrections: list[dict[str, str]] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _harvest_dir() -> Path:
    path = get_hermes_home() / "level_up" / "harvest"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir(exist_ok=True)
    return path


def _append_jsonl(name: str, record: dict[str, Any]) -> None:
    path = _harvest_dir() / name
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _recent_sessions(limit: int) -> list[tuple[str, float, str]]:
    """Return the N most recently active sessions as (id, last_active, excerpt)."""
    db_path = get_hermes_home() / "state.db"
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path), timeout=1.0)
    conn.row_factory = sqlite3.Row
    try:
        rows = list(conn.execute(
            """
            SELECT s.id AS id,
                   COALESCE((SELECT MAX(m.timestamp) FROM messages m WHERE m.session_id = s.id),
                            s.started_at) AS last_active
            FROM sessions s
            ORDER BY last_active DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall())
        sessions: list[tuple[str, float, str]] = []
        for row in rows:
            msgs = list(conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY timestamp ASC LIMIT 80",
                (row["id"],),
            ).fetchall())
            if len(msgs) < 6:
                continue
            excerpt_lines: list[str] = []
            for m in msgs:
                role = m["role"] or "assistant"
                content = m["content"] or ""
                if isinstance(content, str) and content.strip():
                    excerpt_lines.append(f"{role}: {content.strip()[:800]}")
            excerpt = "\n".join(excerpt_lines)[:12000]
            sessions.append((row["id"], float(row["last_active"] or 0), excerpt))
        return sessions
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _call_model(prompt: str) -> str:
    """Call the configured compression model with a compact prompt."""
    # Lazy import — agent.auxiliary_client may not be importable from all entry points.
    try:
        from agent.auxiliary_client import call_auxiliary  # type: ignore
    except Exception as exc:
        logger.debug("level-up: auxiliary client unavailable (%s); using urllib fallback", exc)
        return _call_model_urllib(prompt)
    try:
        return call_auxiliary(
            role="compression",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
        ) or ""
    except Exception as exc:
        logger.warning("level-up: auxiliary compression call failed: %s", exc)
        return ""


def _call_model_urllib(prompt: str) -> str:
    import os
    import yaml
    from urllib.request import Request, urlopen

    cfg_path = get_hermes_home() / "config.yaml"
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return ""

    aux = ((cfg.get("auxiliary") or {}).get("compression") or {})
    model_cfg = cfg.get("model") or {}
    base_url = aux.get("base_url") or model_cfg.get("base_url")
    model = aux.get("model") or (cfg.get("fallback_model") or {}).get("model") or model_cfg.get("default")
    if not base_url or not model:
        return ""

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 1024,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if os.getenv("OPENAI_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['OPENAI_API_KEY']}"
    url = base_url.rstrip("/") + "/chat/completions"
    try:
        with urlopen(Request(url, data=payload, headers=headers, method="POST"), timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("level-up: harvest model call failed: %s", exc)
        return ""
    try:
        return data["choices"][0]["message"]["content"] or ""
    except Exception:
        return ""


def _parse_extraction(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return {}
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------------------
# Public API + slash command
# ---------------------------------------------------------------------------

def run_harvest(limit: int = 5) -> HarvestResult:
    """Harvest memories from the N most recent sessions. Returns an aggregate."""
    sessions = _recent_sessions(limit)
    aggregate = HarvestResult(ts=time.time(), session_id=f"aggregate_{int(time.time())}")

    for session_id, _last_active, excerpt in sessions:
        raw = _call_model(HARVEST_PROMPT.replace("{excerpt}", excerpt))
        data = _parse_extraction(raw)
        if not data:
            continue

        facts = [str(x).strip() for x in data.get("facts") or [] if str(x).strip()]
        corrections = [
            {"context": str(c.get("context", "")).strip(), "fix": str(c.get("fix", "")).strip()}
            for c in data.get("corrections") or []
            if isinstance(c, dict) and c.get("context") and c.get("fix")
        ]
        avoid = [str(x).strip() for x in data.get("avoid") or [] if str(x).strip()]

        ts = time.time()
        for item in facts:
            _append_jsonl("facts.jsonl", {"ts": ts, "session_id": session_id, "fact": item, "status": "proposed"})
        for item in corrections:
            _append_jsonl("corrections.jsonl", {"ts": ts, "session_id": session_id, **item, "status": "proposed"})
        for item in avoid:
            _append_jsonl("avoid.jsonl", {"ts": ts, "session_id": session_id, "avoid": item, "status": "proposed"})

        aggregate.facts.extend(facts)
        aggregate.corrections.extend(corrections)
        aggregate.avoid.extend(avoid)

    return aggregate


def harvest_command(raw_args: str = "") -> str:
    """`/harvest [limit]` — extract proposed memories from recent sessions."""
    try:
        limit = max(1, min(20, int(raw_args.strip() or "5")))
    except ValueError:
        limit = 5

    result = run_harvest(limit=limit)
    total = len(result.facts) + len(result.corrections) + len(result.avoid)
    if total == 0:
        return f"Harvested {limit} session(s); nothing durable extracted. `[SILENT]`"

    return (
        f"Harvested {limit} session(s):\n"
        f"- facts: {len(result.facts)}\n"
        f"- corrections: {len(result.corrections)}\n"
        f"- avoid: {len(result.avoid)}\n"
        f"See `{_harvest_dir()}/` for proposed entries."
    )


# ---------------------------------------------------------------------------
# Session-end hook
# ---------------------------------------------------------------------------

def on_session_end_hook(session_id: str = "", **_: Any) -> None:
    """Low-frequency trigger: harvest this one session when it ends cleanly."""
    # Skip very short sessions — they rarely contain durable knowledge.
    try:
        sessions = _recent_sessions(limit=1)
        if not sessions or sessions[0][0] != session_id:
            return
        run_harvest(limit=1)
    except Exception as exc:
        logger.debug("level-up: session-end harvest skipped: %s", exc)
