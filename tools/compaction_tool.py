"""Tools for retrieving archived compaction context.

Compaction keeps the live prompt small, but the raw compacted span is archived
in SQLite.  These tools let the model search and expand that archive for the
current session lineage without mixing in unrelated past sessions.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from tools.registry import registry, tool_error


def _lineage_ids(db: Any, current_session_id: Optional[str]) -> List[str]:
    if not db or not current_session_id:
        return []
    try:
        return db.get_session_lineage_ids(current_session_id)
    except Exception:
        return [current_session_id]


def compaction_search(
    query: str = "",
    limit: int = 5,
    db: Any = None,
    current_session_id: str = None,
) -> str:
    """Search compaction artifacts in the current session lineage."""
    if db is None:
        return tool_error("Session database not available.", success=False)
    try:
        limit = max(1, min(int(limit or 5), 10))
    except (TypeError, ValueError):
        limit = 5

    lineage = _lineage_ids(db, current_session_id)
    if not lineage:
        return json.dumps({
            "success": True,
            "query": query or "",
            "results": [],
            "count": 0,
            "message": "No current session lineage available.",
        }, ensure_ascii=False)

    rows = db.search_compaction_artifacts(
        query=query or "",
        session_ids=lineage,
        limit=limit,
    )
    results = []
    for row in rows:
        validation = row.get("validation") or {}
        checkpoint = row.get("checkpoint") or {}
        results.append({
            "artifact_id": row.get("id"),
            "source_session_id": row.get("source_session_id"),
            "continuation_session_id": row.get("continuation_session_id"),
            "trigger": row.get("trigger"),
            "source": row.get("source"),
            "status": row.get("status"),
            "created_at": row.get("created_at"),
            "snippet": row.get("snippet"),
            "summary_preview": (row.get("summary") or "")[:1200],
            "validation": validation,
            "files": (checkpoint.get("files") or [])[:20] if isinstance(checkpoint, dict) else [],
            "commands": (checkpoint.get("commands") or [])[:10] if isinstance(checkpoint, dict) else [],
            "errors": (checkpoint.get("errors") or [])[:5] if isinstance(checkpoint, dict) else [],
            "approx_tokens_before": row.get("approx_tokens_before"),
            "approx_tokens_after": row.get("approx_tokens_after"),
        })

    return json.dumps({
        "success": True,
        "query": query or "",
        "lineage": lineage,
        "results": results,
        "count": len(results),
    }, ensure_ascii=False)


def compaction_expand(
    artifact_id: int,
    include_raw: bool = True,
    max_messages: int = 20,
    db: Any = None,
    current_session_id: str = None,
) -> str:
    """Return a full compaction artifact, optionally including raw messages."""
    if db is None:
        return tool_error("Session database not available.", success=False)
    try:
        artifact_id = int(artifact_id)
    except (TypeError, ValueError):
        return tool_error("artifact_id must be an integer.", success=False)

    artifact = db.get_compaction_artifact(artifact_id)
    if not artifact:
        return tool_error(f"Compaction artifact {artifact_id} not found.", success=False)

    lineage = set(_lineage_ids(db, current_session_id))
    if lineage and (
        artifact.get("source_session_id") not in lineage
        and artifact.get("continuation_session_id") not in lineage
    ):
        return tool_error(
            f"Compaction artifact {artifact_id} is not in the current session lineage.",
            success=False,
        )

    try:
        max_messages = max(1, min(int(max_messages or 20), 100))
    except (TypeError, ValueError):
        max_messages = 20

    raw_messages = artifact.get("raw_messages") or []
    if not include_raw:
        raw_messages = []
    else:
        raw_messages = raw_messages[:max_messages]

    return json.dumps({
        "success": True,
        "artifact_id": artifact.get("id"),
        "source_session_id": artifact.get("source_session_id"),
        "continuation_session_id": artifact.get("continuation_session_id"),
        "created_at": artifact.get("created_at"),
        "trigger": artifact.get("trigger"),
        "source": artifact.get("source"),
        "status": artifact.get("status"),
        "summary": artifact.get("summary"),
        "checkpoint": artifact.get("checkpoint"),
        "validation": artifact.get("validation"),
        "event": artifact.get("event"),
        "raw_messages": raw_messages,
        "raw_message_count": len(artifact.get("raw_messages") or []),
        "returned_raw_messages": len(raw_messages),
    }, ensure_ascii=False)


def check_compaction_tool_requirements() -> bool:
    try:
        from hermes_state import DEFAULT_DB_PATH
        return DEFAULT_DB_PATH.parent.exists()
    except ImportError:
        return False


COMPACTION_SEARCH_SCHEMA = {
    "name": "compaction_search",
    "description": (
        "Search archived context from this session's compaction lineage. Use this when "
        "a detail may have been compacted out of the live prompt: prior file paths, "
        "commands, errors, tool outputs, decisions, or user asks from earlier in the "
        "same long-running conversation. This searches only the current compressed "
        "session lineage, not unrelated past sessions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keywords, phrase, or FTS5 query. Omit/empty to list recent compaction artifacts.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum artifacts to return (default 5, max 10).",
                "default": 5,
            },
        },
        "required": [],
    },
}


COMPACTION_EXPAND_SCHEMA = {
    "name": "compaction_expand",
    "description": (
        "Expand one compaction artifact returned by compaction_search. Returns the "
        "summary, deterministic checkpoint, validation metadata, and optionally the "
        "exact raw messages that were removed from the live prompt."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "artifact_id": {
                "type": "integer",
                "description": "Artifact id from compaction_search.",
            },
            "include_raw": {
                "type": "boolean",
                "description": "Whether to include exact archived raw messages.",
                "default": True,
            },
            "max_messages": {
                "type": "integer",
                "description": "Maximum raw messages to return (default 20, max 100).",
                "default": 20,
            },
        },
        "required": ["artifact_id"],
    },
}


registry.register(
    name="compaction_search",
    toolset="compaction",
    schema=COMPACTION_SEARCH_SCHEMA,
    handler=lambda args, **kw: compaction_search(
        query=args.get("query") or "",
        limit=args.get("limit", 5),
        db=kw.get("db"),
        current_session_id=kw.get("current_session_id"),
    ),
    check_fn=check_compaction_tool_requirements,
    emoji="🗜️",
)

registry.register(
    name="compaction_expand",
    toolset="compaction",
    schema=COMPACTION_EXPAND_SCHEMA,
    handler=lambda args, **kw: compaction_expand(
        artifact_id=args.get("artifact_id"),
        include_raw=args.get("include_raw", True),
        max_messages=args.get("max_messages", 20),
        db=kw.get("db"),
        current_session_id=kw.get("current_session_id"),
    ),
    check_fn=check_compaction_tool_requirements,
    emoji="🗜️",
)
