"""Tool latency observer for level-up.

Records compact per-tool telemetry to
``$HERMES_HOME/level_up/tool_metrics.jsonl`` from the ``post_tool_call`` hook.
The file is append-only and intentionally schema-light so it can be inspected
with jq, awk, or a notebook without enabling a profiler.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home


def _metrics_path() -> Path:
    path = get_hermes_home() / "level_up" / "tool_metrics.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _result_size(result: Any, result_size: int | None = None) -> int:
    if isinstance(result_size, int) and result_size >= 0:
        return result_size
    if result is None:
        return 0
    if isinstance(result, (bytes, bytearray)):
        return len(result)
    return len(str(result))


def post_tool_call_hook(
    tool_name: str = "",
    args: dict[str, Any] | None = None,
    result: Any = None,
    duration: float | None = None,
    result_size: int | None = None,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    **_: Any,
) -> None:
    record = {
        "ts": time.time(),
        "tool_name": tool_name,
        "duration_s": round(float(duration or 0.0), 4),
        "result_size": _result_size(result, result_size),
        "args_keys": sorted((args or {}).keys()),
        "task_id": task_id,
        "session_id": session_id,
        "tool_call_id": tool_call_id,
    }
    with _metrics_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
