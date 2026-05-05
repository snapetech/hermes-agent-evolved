#!/usr/bin/env python3
"""Durable state helper for the Hermes nightly local-LLM review loop."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home


SCHEMA_VERSION = 1
DEFAULT_MODEL_DIR = Path("/opt/models/hermes-bench")


@dataclass(frozen=True)
class NightlyPaths:
    root: Path
    state: Path
    reports_dir: Path
    latest_report: Path


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utc_now().isoformat()


def parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def nightly_paths() -> NightlyPaths:
    root = get_hermes_home() / "self-improvement" / "local-llm-nightly"
    reports_dir = root / "reports"
    return NightlyPaths(
        root=root,
        state=root / "state.json",
        reports_dir=reports_dir,
        latest_report=reports_dir / "latest.md",
    )


def _default_run_id(now: datetime | None = None) -> str:
    return (now or utc_now()).date().isoformat()


def _default_report_path(paths: NightlyPaths, run_id: str) -> Path:
    return paths.reports_dir / f"{run_id}.md"


def default_state(now: datetime | None = None) -> dict[str, Any]:
    run_id = _default_run_id(now)
    paths = nightly_paths()
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "status": "not_started",
        "phase": "startup",
        "attempt_count": 0,
        "started_at": None,
        "updated_at": None,
        "ended_at": None,
        "current_candidate": None,
        "summary": "",
        "report_path": str(_default_report_path(paths, run_id)),
        "latest_report_path": str(paths.latest_report),
        "recovery": {
            "resume_from_run_id": None,
            "resume_from_phase": None,
            "resume_from_candidate": None,
            "stale_previous_run": False,
            "needs_reconciliation": False,
            "issues": [],
        },
        "candidates": [],
        "notes": [],
        "history": [],
    }


def load_state(path: Path | None = None) -> dict[str, Any]:
    state_path = path or nightly_paths().state
    if not state_path.exists():
        return default_state()
    try:
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return default_state()
    base = default_state()
    if isinstance(loaded, dict):
        base.update({k: v for k, v in loaded.items() if k in base})
        if not isinstance(base.get("recovery"), dict):
            base["recovery"] = default_state()["recovery"]
        else:
            recovery = default_state()["recovery"]
            recovery.update({k: v for k, v in base["recovery"].items() if k in recovery})
            base["recovery"] = recovery
        if not isinstance(base.get("candidates"), list):
            base["candidates"] = []
        if not isinstance(base.get("notes"), list):
            base["notes"] = []
        if not isinstance(base.get("history"), list):
            base["history"] = []
    return base


def write_state(state: dict[str, Any], path: Path | None = None) -> Path:
    state_path = path or nightly_paths().state
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return state_path


def _append_note(state: dict[str, Any], note: str) -> None:
    text = note.strip()
    if not text:
        return
    state.setdefault("notes", []).append({"ts": iso_now(), "note": text})


def _push_history(state: dict[str, Any], snapshot: dict[str, Any], *, limit: int = 12) -> None:
    history = state.setdefault("history", [])
    history.append(snapshot)
    if len(history) > limit:
        del history[:-limit]


def _is_stale_running(state: dict[str, Any], *, stale_after_hours: float) -> bool:
    if state.get("status") != "running":
        return False
    updated = parse_dt(state.get("updated_at")) or parse_dt(state.get("started_at"))
    if updated is None:
        return True
    return utc_now() - updated > timedelta(hours=stale_after_hours)


def begin_run(
    *,
    phase: str = "startup",
    run_id: str | None = None,
    summary: str = "",
    stale_after_hours: float = 18,
    state_path: Path | None = None,
) -> dict[str, Any]:
    state = load_state(state_path)
    paths = nightly_paths()
    now = iso_now()
    run_id = (run_id or _default_run_id()).strip() or _default_run_id()
    stale_running = _is_stale_running(state, stale_after_hours=stale_after_hours)
    prior_run_id = state.get("run_id")
    same_run = prior_run_id == run_id
    resumable = same_run and state.get("status") in {"running", "failed", "interrupted", "partial"}

    if state.get("status") == "running" and (stale_running or not same_run):
        interrupted = deepcopy(state)
        interrupted["status"] = "interrupted"
        interrupted["ended_at"] = now
        _push_history(state, interrupted)
        state["recovery"] = {
            "resume_from_run_id": prior_run_id,
            "resume_from_phase": interrupted.get("phase"),
            "resume_from_candidate": interrupted.get("current_candidate"),
            "stale_previous_run": stale_running,
            "needs_reconciliation": True,
            "issues": ["unfinished previous run"],
        }
    elif not isinstance(state.get("recovery"), dict):
        state["recovery"] = default_state()["recovery"]

    if not resumable or not same_run:
        state = default_state()
        state["run_id"] = run_id
        state["report_path"] = str(_default_report_path(paths, run_id))
        state["latest_report_path"] = str(paths.latest_report)

    state["status"] = "running"
    state["phase"] = phase
    state["started_at"] = state.get("started_at") or now
    state["updated_at"] = now
    state["ended_at"] = None
    state["attempt_count"] = int(state.get("attempt_count") or 0) + 1
    state["summary"] = summary or state.get("summary") or ""
    if resumable:
        issues = list(state["recovery"].get("issues") or [])
        issues.append(f"resumed run {run_id}")
        state["recovery"]["issues"] = issues[-8:]
        state["recovery"]["needs_reconciliation"] = True
    _append_note(state, f"begin phase={phase} attempt={state['attempt_count']}")
    write_state(state, state_path)
    return state


def checkpoint_run(
    *,
    phase: str,
    note: str = "",
    candidate: str | None = None,
    summary: str | None = None,
    state_path: Path | None = None,
) -> dict[str, Any]:
    state = load_state(state_path)
    state["status"] = "running"
    state["phase"] = phase
    state["updated_at"] = iso_now()
    if candidate is not None:
        state["current_candidate"] = candidate or None
    if summary is not None:
        state["summary"] = summary
    _append_note(state, note)
    write_state(state, state_path)
    return state


def _upsert_candidate(
    state: dict[str, Any],
    *,
    name: str,
    status: str,
    local_path: str = "",
    note: str = "",
) -> dict[str, Any]:
    candidates = state.setdefault("candidates", [])
    record = None
    for item in candidates:
        if isinstance(item, dict) and item.get("name") == name:
            record = item
            break
    if record is None:
        record = {"name": name, "notes": []}
        candidates.append(record)
    record["status"] = status
    if local_path:
        record["local_path"] = local_path
    record["updated_at"] = iso_now()
    if note.strip():
        record.setdefault("notes", []).append(note.strip())
    return record


def update_candidate(
    *,
    name: str,
    status: str,
    local_path: str = "",
    note: str = "",
    state_path: Path | None = None,
) -> dict[str, Any]:
    state = load_state(state_path)
    _upsert_candidate(state, name=name, status=status, local_path=local_path, note=note)
    state["updated_at"] = iso_now()
    state["current_candidate"] = name
    write_state(state, state_path)
    return state


def finalize_run(
    *,
    status: str,
    summary: str = "",
    report_path: str | None = None,
    state_path: Path | None = None,
) -> dict[str, Any]:
    state = load_state(state_path)
    state["status"] = status
    state["summary"] = summary or state.get("summary") or ""
    state["ended_at"] = iso_now()
    state["updated_at"] = state["ended_at"]
    state["current_candidate"] = None
    state["recovery"]["needs_reconciliation"] = status != "completed"
    if report_path:
        state["report_path"] = report_path
    snapshot = deepcopy(state)
    _push_history(state, snapshot)
    write_state(state, state_path)
    return state


def reconcile_state(
    *,
    model_dir: Path | None = None,
    stale_after_hours: float = 18,
    state_path: Path | None = None,
) -> dict[str, Any]:
    state = load_state(state_path)
    issues: list[dict[str, Any]] = []
    model_dir = model_dir or DEFAULT_MODEL_DIR

    if _is_stale_running(state, stale_after_hours=stale_after_hours):
        state["status"] = "interrupted"
        state["recovery"]["stale_previous_run"] = True
        state["recovery"]["needs_reconciliation"] = True
        issues.append({
            "type": "stale_running_state",
            "message": "nightly run was still marked running past the stale threshold",
        })

    for candidate in state.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        local_path = str(candidate.get("local_path") or "").strip()
        if not local_path:
            continue
        path = Path(local_path)
        status = str(candidate.get("status") or "")
        if status in {"rejected", "deleted"} and path.exists():
            issues.append({
                "type": "leftover_rejected_download",
                "candidate": candidate.get("name"),
                "path": str(path),
            })
        if status in {"downloaded", "benchmarked", "queued"} and not path.exists():
            issues.append({
                "type": "missing_candidate_file",
                "candidate": candidate.get("name"),
                "path": str(path),
            })

    report_path = Path(str(state.get("report_path") or ""))
    latest_report = Path(str(state.get("latest_report_path") or ""))
    if state.get("status") == "completed" and report_path and not report_path.exists():
        issues.append({
            "type": "missing_dated_report",
            "path": str(report_path),
        })
    if latest_report and not latest_report.exists():
        issues.append({
            "type": "missing_latest_report",
            "path": str(latest_report),
        })

    state["updated_at"] = iso_now()
    state["recovery"]["needs_reconciliation"] = bool(issues)
    state["recovery"]["issues"] = [item["type"] for item in issues]
    write_state(state, state_path)
    return {"state": state, "issues": issues, "model_dir": str(model_dir)}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    begin = sub.add_parser("begin", help="start or resume a nightly run")
    begin.add_argument("--phase", default="startup")
    begin.add_argument("--run-id")
    begin.add_argument("--summary", default="")
    begin.add_argument("--stale-hours", type=float, default=18)

    checkpoint = sub.add_parser("checkpoint", help="write a phase heartbeat")
    checkpoint.add_argument("--phase", required=True)
    checkpoint.add_argument("--note", default="")
    checkpoint.add_argument("--candidate")
    checkpoint.add_argument("--summary")

    candidate = sub.add_parser("candidate", help="record candidate status")
    candidate.add_argument("--name", required=True)
    candidate.add_argument("--status", required=True)
    candidate.add_argument("--local-path", default="")
    candidate.add_argument("--note", default="")

    finalize = sub.add_parser("finalize", help="finish a nightly run")
    finalize.add_argument("--status", default="completed")
    finalize.add_argument("--summary", default="")
    finalize.add_argument("--report-path")

    reconcile = sub.add_parser("reconcile", help="inspect stale or inconsistent nightly state")
    reconcile.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    reconcile.add_argument("--stale-hours", type=float, default=18)

    sub.add_parser("show", help="print current nightly state")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "begin":
        result = begin_run(
            phase=args.phase,
            run_id=args.run_id,
            summary=args.summary,
            stale_after_hours=args.stale_hours,
        )
    elif args.command == "checkpoint":
        result = checkpoint_run(
            phase=args.phase,
            note=args.note,
            candidate=args.candidate,
            summary=args.summary,
        )
    elif args.command == "candidate":
        result = update_candidate(
            name=args.name,
            status=args.status,
            local_path=args.local_path,
            note=args.note,
        )
    elif args.command == "finalize":
        result = finalize_run(
            status=args.status,
            summary=args.summary,
            report_path=args.report_path,
        )
    elif args.command == "reconcile":
        result = reconcile_state(model_dir=args.model_dir, stale_after_hours=args.stale_hours)
    else:
        result = load_state()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
