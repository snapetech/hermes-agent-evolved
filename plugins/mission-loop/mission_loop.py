"""Durable mission loop implementation for Hermes.

This module intentionally keeps the controller small and file-first.  The
normal Hermes agent loop remains responsible for tool use; this controller
only decides when to start a fresh iteration, what context to provide, and
whether an external verifier has accepted the result.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home


DEFAULT_MAX_ITERATIONS = 10
DEFAULT_RUN_ITERATIONS = 1
DEFAULT_VERIFIER_TIMEOUT = 900
DEFAULT_AGENT_TURNS = 90
PROGRESS_TAIL_CHARS = 20000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _missions_root() -> Path:
    root = get_hermes_home() / "missions"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip().lower()).strip("-")
    return text[:48] or "mission"


def _mission_id(title: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{_slug(title)}-{uuid.uuid4().hex[:6]}"


def _mission_dir(mission_id: str) -> Path:
    clean = _slug(mission_id)
    if clean != mission_id:
        # IDs are path components; keep this strict to avoid surprising aliases.
        raise ValueError("mission_id may only contain letters, numbers, dot, underscore, and dash")
    return _missions_root() / mission_id


def _state_path(mission_id: str) -> Path:
    return _mission_dir(mission_id) / "state.json"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_text_if_exists(path: Path, limit: int | None = None) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if limit is not None and len(text) > limit:
        return text[-limit:]
    return text


def _workspace_default() -> str:
    for key in ("TERMINAL_CWD", "HERMES_WORKSPACE"):
        value = os.getenv(key)
        if value:
            return str(Path(value).expanduser())
    return str(Path.cwd())


def _coerce_int(value: Any, default: int, *, low: int = 1, high: int = 1000) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


@dataclass
class VerifyResult:
    success: bool
    exit_code: int | None
    output: str
    elapsed_seconds: float
    command: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "output": self.output,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "command": self.command,
        }


class MissionLock:
    """Small durable lock to avoid two controllers running one mission."""

    def __init__(self, mission_id: str):
        self.path = _mission_dir(mission_id) / ".run.lock"
        self.acquired = False

    def __enter__(self) -> "MissionLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError(f"mission is already running: {self.path}") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"pid": os.getpid(), "started_at": _now()}) + "\n")
        self.acquired = True
        return self

    def __exit__(self, *_: object) -> None:
        if self.acquired:
            try:
                self.path.unlink()
            except OSError:
                pass


def create_mission(
    *,
    title: str,
    spec: str,
    workdir: str | None = None,
    verifier: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    success_marker: str = "VERIFIED_DONE",
) -> dict[str, Any]:
    title = (title or "Mission").strip()
    spec = (spec or "").strip()
    if not spec:
        raise ValueError("spec is required")

    mission_id = _mission_id(title)
    mission_dir = _mission_dir(mission_id)
    mission_dir.mkdir(parents=True, exist_ok=False)
    (mission_dir / "artifacts").mkdir(exist_ok=True)

    state = {
        "id": mission_id,
        "title": title,
        "status": "open",
        "created_at": _now(),
        "updated_at": _now(),
        "workdir": str(Path(workdir or _workspace_default()).expanduser()),
        "verifier": (verifier or "").strip(),
        "verifier_timeout_seconds": DEFAULT_VERIFIER_TIMEOUT,
        "max_iterations": _coerce_int(max_iterations, DEFAULT_MAX_ITERATIONS, low=1, high=100),
        "iterations_completed": 0,
        "success_marker": (success_marker or "VERIFIED_DONE").strip(),
        "last_verification": None,
        "last_error": None,
    }

    (mission_dir / "SPEC.md").write_text(spec + "\n", encoding="utf-8")
    _write_json(mission_dir / "state.json", state)
    _append_jsonl(
        mission_dir / "progress.jsonl",
        {"ts": _now(), "event": "created", "status": "open", "note": title},
    )
    return {"success": True, "mission": state, "path": str(mission_dir)}


def load_mission(mission_id: str) -> dict[str, Any]:
    path = _state_path(mission_id)
    if not path.exists():
        raise FileNotFoundError(f"mission not found: {mission_id}")
    return _read_json(path)


def save_mission(state: dict[str, Any]) -> None:
    state["updated_at"] = _now()
    _write_json(_state_path(state["id"]), state)


def list_missions(limit: int = 20, include_closed: bool = True) -> list[dict[str, Any]]:
    missions: list[dict[str, Any]] = []
    for state_file in sorted(_missions_root().glob("*/state.json"), reverse=True):
        try:
            state = _read_json(state_file)
        except Exception:
            continue
        if not include_closed and state.get("status") in {"verified", "failed", "cancelled"}:
            continue
        missions.append(state)
        if len(missions) >= limit:
            break
    return missions


def record_progress(
    mission_id: str,
    *,
    note: str,
    status: str | None = None,
    event: str = "note",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = load_mission(mission_id)
    mission_dir = _mission_dir(mission_id)
    row = {
        "ts": _now(),
        "event": event,
        "status": status or state.get("status", "open"),
        "note": (note or "").strip(),
    }
    if extra:
        row.update(extra)
    _append_jsonl(mission_dir / "progress.jsonl", row)
    if status:
        state["status"] = status
    save_mission(state)
    return {"success": True, "mission": state, "record": row}


def verify_mission(mission_id: str) -> dict[str, Any]:
    state = load_mission(mission_id)
    command = str(state.get("verifier") or "").strip()
    if not command:
        raise ValueError("mission has no verifier command")

    workdir = Path(str(state.get("workdir") or _workspace_default())).expanduser()
    start = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=str(workdir),
            shell=True,
            text=True,
            capture_output=True,
            timeout=_coerce_int(
                state.get("verifier_timeout_seconds"),
                DEFAULT_VERIFIER_TIMEOUT,
                low=1,
                high=86400,
            ),
        )
        output = ((proc.stdout or "") + ("\n" if proc.stdout and proc.stderr else "") + (proc.stderr or "")).strip()
        result = VerifyResult(
            success=proc.returncode == 0,
            exit_code=proc.returncode,
            output=output[-12000:],
            elapsed_seconds=time.monotonic() - start,
            command=command,
        )
    except subprocess.TimeoutExpired as exc:
        result = VerifyResult(
            success=False,
            exit_code=None,
            output=f"Verifier timed out after {exc.timeout}s.",
            elapsed_seconds=time.monotonic() - start,
            command=command,
        )

    result_dict = result.as_dict()
    state["last_verification"] = {**result_dict, "ts": _now()}
    if result.success:
        state["status"] = "verified"
        state["last_error"] = None
    else:
        if state.get("status") == "verified":
            state["status"] = "open"
        state["last_error"] = result.output[:1000]
    save_mission(state)
    _append_jsonl(
        _mission_dir(mission_id) / "progress.jsonl",
        {
            "ts": _now(),
            "event": "verify",
            "status": state["status"],
            "success": result.success,
            "exit_code": result.exit_code,
            "note": result.output[:2000],
        },
    )
    return {"success": True, "mission": state, "verification": result_dict}


def render_iteration_prompt(mission_id: str) -> str:
    state = load_mission(mission_id)
    mission_dir = _mission_dir(mission_id)
    spec = _read_text_if_exists(mission_dir / "SPEC.md")
    progress_tail = _read_text_if_exists(mission_dir / "progress.jsonl", limit=PROGRESS_TAIL_CHARS)
    verification = state.get("last_verification") or {}
    marker = state.get("success_marker") or "VERIFIED_DONE"

    return "\n".join(
        [
            "# Hermes Mission Loop Iteration",
            "",
            "You are one fresh iteration in a durable verifier-gated mission loop.",
            "Do not rely on hidden chat history. Reconstruct state from the filesystem, git state, mission files, and the progress log below.",
            "",
            "## Mission",
            f"- ID: {state['id']}",
            f"- Title: {state.get('title', '')}",
            f"- Workdir: {state.get('workdir', '')}",
            f"- Iteration: {int(state.get('iterations_completed') or 0) + 1} / {state.get('max_iterations')}",
            f"- Verifier: `{state.get('verifier') or 'not configured'}`",
            "",
            "## Spec",
            spec.strip(),
            "",
            "## Recent Progress Log",
            "```jsonl",
            progress_tail.strip() or "(no progress yet)",
            "```",
            "",
            "## Last Verification",
            "```text",
            str(verification.get("output") or "(not run yet)")[:12000],
            "```",
            "",
            "## Operating Rules",
            "- Work in the mission workdir unless the spec explicitly says otherwise.",
            "- Inspect current repo/files before editing; previous iterations may already have made progress.",
            "- Prefer small, verifiable changes. Do not rewrite unrelated code.",
            "- Run focused checks when useful, but the controller will run the verifier after your turn.",
            "- If blocked, write the blocker and the most useful next action in your final response.",
            f"- Include `{marker}` only when you believe the verifier should now pass; external verification is still authoritative.",
            "",
            "Continue the mission from current state.",
        ]
    )


def _artifact_path(mission_id: str, iteration: int, suffix: str) -> Path:
    return _mission_dir(mission_id) / "artifacts" / f"iteration-{iteration:04d}.{suffix}"


def run_mission(mission_id: str, *, iterations: int = DEFAULT_RUN_ITERATIONS) -> dict[str, Any]:
    """Run up to *iterations* fresh agent turns, stopping on verifier success."""
    with MissionLock(mission_id):
        state = load_mission(mission_id)
        max_total = _coerce_int(state.get("max_iterations"), DEFAULT_MAX_ITERATIONS, low=1, high=100)
        requested = _coerce_int(iterations, DEFAULT_RUN_ITERATIONS, low=1, high=100)
        results: list[dict[str, Any]] = []

        if state.get("status") == "verified":
            return {"success": True, "mission": state, "iterations": [], "message": "mission already verified"}

        # If a verifier is configured, check first. This avoids spending tokens
        # after manual fixes have already satisfied the mission.
        if str(state.get("verifier") or "").strip():
            first_verify = verify_mission(mission_id)
            results.append({"event": "pre_verify", "verification": first_verify["verification"]})
            state = first_verify["mission"]
            if state.get("status") == "verified":
                return {"success": True, "mission": state, "iterations": results}

        for _ in range(requested):
            state = load_mission(mission_id)
            completed = int(state.get("iterations_completed") or 0)
            if completed >= max_total:
                state["status"] = "failed"
                state["last_error"] = f"maximum iterations reached ({completed}/{max_total})"
                save_mission(state)
                break

            iteration = completed + 1
            prompt = render_iteration_prompt(mission_id)
            _artifact_path(mission_id, iteration, "prompt.md").write_text(prompt, encoding="utf-8")

            _append_jsonl(
                _mission_dir(mission_id) / "progress.jsonl",
                {"ts": _now(), "event": "iteration_start", "status": "running", "iteration": iteration},
            )

            response_text = ""
            result_payload: dict[str, Any] = {}
            try:
                from run_agent import AIAgent

                agent = AIAgent(
                    max_iterations=DEFAULT_AGENT_TURNS,
                    quiet_mode=True,
                    platform="mission",
                    session_id=f"mission_{state['id']}_{iteration:04d}",
                )
                try:
                    result_payload = agent.run_conversation(prompt, task_id=f"mission_{state['id']}_{iteration:04d}") or {}
                    response_text = str(result_payload.get("final_response") or "")
                    if not response_text and result_payload.get("error"):
                        response_text = f"Error: {result_payload['error']}"
                finally:
                    try:
                        agent.close()
                    except Exception:
                        pass
            except Exception as exc:
                response_text = f"Mission iteration failed before completion: {type(exc).__name__}: {exc}"
                result_payload = {"error": response_text}

            _artifact_path(mission_id, iteration, "response.md").write_text(response_text + "\n", encoding="utf-8")
            state = load_mission(mission_id)
            state["iterations_completed"] = iteration
            state["status"] = "open"
            state["last_error"] = result_payload.get("error")
            save_mission(state)

            _append_jsonl(
                _mission_dir(mission_id) / "progress.jsonl",
                {
                    "ts": _now(),
                    "event": "iteration_complete",
                    "status": "open",
                    "iteration": iteration,
                    "note": response_text[:2000],
                    "agent_error": result_payload.get("error"),
                },
            )

            item: dict[str, Any] = {
                "event": "iteration",
                "iteration": iteration,
                "response_chars": len(response_text),
                "agent_error": result_payload.get("error"),
            }
            if str(state.get("verifier") or "").strip():
                verified = verify_mission(mission_id)
                item["verification"] = verified["verification"]
                state = verified["mission"]
                if state.get("status") == "verified":
                    results.append(item)
                    break
            results.append(item)

        return {"success": True, "mission": load_mission(mission_id), "iterations": results}


def start_background_run(mission_id: str, *, iterations: int = DEFAULT_RUN_ITERATIONS) -> dict[str, Any]:
    """Start a daemon-thread mission run and return immediately.

    Slash commands use this so gateway command dispatch is not blocked by a
    long verifier/agent loop. Operators can inspect progress with
    ``/mission status`` and the artifacts under the mission directory.
    """
    state = load_mission(mission_id)
    iterations = _coerce_int(iterations, DEFAULT_RUN_ITERATIONS, low=1, high=100)

    def _target() -> None:
        try:
            record_progress(
                mission_id,
                note=f"background run started for up to {iterations} iteration(s)",
                event="run_start",
            )
            result = run_mission(mission_id, iterations=iterations)
            final_state = result.get("mission") or {}
            record_progress(
                mission_id,
                note=(
                    f"background run finished with status={final_state.get('status')} "
                    f"after {len(result.get('iterations') or [])} event(s)"
                ),
                status=final_state.get("status") or None,
                event="run_complete",
            )
        except Exception as exc:
            try:
                record_progress(
                    mission_id,
                    note=f"background run failed: {type(exc).__name__}: {exc}",
                    status="open",
                    event="run_error",
                )
            except Exception:
                pass

    thread = threading.Thread(
        target=_target,
        name=f"mission-run-{mission_id[:24]}",
        daemon=True,
    )
    thread.start()
    return {
        "success": True,
        "mission": state,
        "queued": True,
        "iterations": iterations,
        "thread": thread.name,
    }


def mission_loop_tool(args: dict[str, Any]) -> str:
    action = str(args.get("action") or "").strip().lower()
    try:
        if action == "create":
            return json.dumps(
                create_mission(
                    title=str(args.get("title") or "Mission"),
                    spec=str(args.get("spec") or ""),
                    workdir=args.get("workdir") or None,
                    verifier=args.get("verifier") or None,
                    max_iterations=_coerce_int(args.get("max_iterations"), DEFAULT_MAX_ITERATIONS, low=1, high=100),
                    success_marker=str(args.get("success_marker") or "VERIFIED_DONE"),
                ),
                ensure_ascii=False,
            )
        if action == "list":
            return json.dumps({"success": True, "missions": list_missions()}, ensure_ascii=False)
        if action == "status":
            mission_id = str(args.get("mission_id") or "").strip()
            return json.dumps({"success": True, "mission": load_mission(mission_id)}, ensure_ascii=False)
        if action == "record":
            mission_id = str(args.get("mission_id") or "").strip()
            return json.dumps(
                record_progress(
                    mission_id,
                    note=str(args.get("note") or ""),
                    status=str(args.get("status") or "") or None,
                ),
                ensure_ascii=False,
            )
        if action == "verify":
            mission_id = str(args.get("mission_id") or "").strip()
            return json.dumps(verify_mission(mission_id), ensure_ascii=False)
        if action == "render_prompt":
            mission_id = str(args.get("mission_id") or "").strip()
            return json.dumps({"success": True, "prompt": render_iteration_prompt(mission_id)}, ensure_ascii=False)
        if action == "run":
            mission_id = str(args.get("mission_id") or "").strip()
            return json.dumps(
                run_mission(
                    mission_id,
                    iterations=_coerce_int(args.get("iterations"), DEFAULT_RUN_ITERATIONS, low=1, high=100),
                ),
                ensure_ascii=False,
            )
        return json.dumps({"success": False, "error": f"unknown action: {action}"}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"success": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)


def _format_mission(state: dict[str, Any]) -> str:
    verifier = state.get("verifier") or "none"
    last = state.get("last_verification") or {}
    verified = ""
    if last:
        verified = f"\nLast verify: exit={last.get('exit_code')} success={last.get('success')}"
    return (
        f"`{state['id']}` - {state.get('title', '')}\n"
        f"Status: {state.get('status')} | iterations: {state.get('iterations_completed')}/{state.get('max_iterations')}\n"
        f"Workdir: `{state.get('workdir')}`\n"
        f"Verifier: `{verifier}`"
        f"{verified}"
    )


def _help() -> str:
    return """\
/mission - durable verifier-gated mission loops

Commands:
  /mission create --title "Name" --verifier "scripts/run_tests.sh ..." -- <spec>
  /mission list
  /mission status <mission_id>
  /mission record <mission_id> <note>
  /mission verify <mission_id>
  /mission prompt <mission_id>
  /mission run <mission_id> [iterations] [--wait]

Runs are explicit and bounded. Slash-command runs queue in the background by
default; add --wait to block until finished. Each iteration starts a fresh
AIAgent and writes state under `$HERMES_HOME/missions/<mission_id>/`.
"""


def _parse_create(tokens: list[str]) -> dict[str, Any]:
    title = "Mission"
    verifier = ""
    workdir = ""
    max_iterations = DEFAULT_MAX_ITERATIONS
    success_marker = "VERIFIED_DONE"

    if "--" in tokens:
        sep = tokens.index("--")
        opt_tokens = tokens[:sep]
        spec = " ".join(tokens[sep + 1 :]).strip()
    else:
        opt_tokens = []
        spec = " ".join(tokens).strip()

    i = 0
    while i < len(opt_tokens):
        token = opt_tokens[i]
        nxt = opt_tokens[i + 1] if i + 1 < len(opt_tokens) else ""
        if token == "--title" and nxt:
            title = nxt
            i += 2
        elif token == "--verifier" and nxt:
            verifier = nxt
            i += 2
        elif token == "--workdir" and nxt:
            workdir = nxt
            i += 2
        elif token == "--max-iterations" and nxt:
            max_iterations = _coerce_int(nxt, DEFAULT_MAX_ITERATIONS, low=1, high=100)
            i += 2
        elif token == "--success-marker" and nxt:
            success_marker = nxt
            i += 2
        else:
            # Treat unknown option text as part of the spec rather than failing
            # hard in chat surfaces where quoting mistakes are common.
            spec = (" ".join(opt_tokens[i:]) + (" " + spec if spec else "")).strip()
            break

    return {
        "title": title,
        "verifier": verifier,
        "workdir": workdir or None,
        "max_iterations": max_iterations,
        "success_marker": success_marker,
        "spec": spec,
    }


def handle_slash(raw_args: str = "") -> str:
    try:
        tokens = shlex.split(raw_args or "")
    except ValueError as exc:
        return f"Could not parse /mission arguments: {exc}"
    if not tokens or tokens[0] in {"help", "-h", "--help"}:
        return _help()

    cmd = tokens[0].lower()
    rest = tokens[1:]
    try:
        if cmd == "create":
            opts = _parse_create(rest)
            created = create_mission(**opts)
            state = created["mission"]
            return f"Created mission:\n{_format_mission(state)}\nPath: `{created['path']}`"
        if cmd == "list":
            missions = list_missions()
            if not missions:
                return "No missions yet."
            return "\n\n".join(_format_mission(m) for m in missions[:20])
        if cmd == "status":
            if not rest:
                return "Usage: /mission status <mission_id>"
            return _format_mission(load_mission(rest[0]))
        if cmd == "record":
            if len(rest) < 2:
                return "Usage: /mission record <mission_id> <note>"
            result = record_progress(rest[0], note=" ".join(rest[1:]))
            return f"Recorded note for `{result['mission']['id']}`."
        if cmd == "verify":
            if not rest:
                return "Usage: /mission verify <mission_id>"
            result = verify_mission(rest[0])
            verification = result["verification"]
            output = verification.get("output") or ""
            return (
                f"Verifier success={verification.get('success')} exit={verification.get('exit_code')} "
                f"elapsed={verification.get('elapsed_seconds')}s\n"
                f"```text\n{output[:3000]}\n```"
            )
        if cmd == "prompt":
            if not rest:
                return "Usage: /mission prompt <mission_id>"
            prompt = render_iteration_prompt(rest[0])
            return f"```markdown\n{prompt[:12000]}\n```"
        if cmd == "run":
            if not rest:
                return "Usage: /mission run <mission_id> [iterations] [--wait]"
            wait = "--wait" in rest
            filtered = [item for item in rest if item != "--wait"]
            iterations = _coerce_int(filtered[1] if len(filtered) > 1 else DEFAULT_RUN_ITERATIONS, DEFAULT_RUN_ITERATIONS, low=1, high=100)
            if not wait:
                queued = start_background_run(filtered[0], iterations=iterations)
                state = queued["mission"]
                return (
                    f"Mission run queued: `{state['id']}`\n"
                    f"Status: {state.get('status')} | iterations: {state.get('iterations_completed')}/{state.get('max_iterations')}\n"
                    f"Thread: `{queued.get('thread')}`\n"
                    "Use `/mission status <mission_id>` to inspect progress."
                )
            result = run_mission(filtered[0], iterations=iterations)
            state = result["mission"]
            return (
                f"Mission run complete: `{state['id']}`\n"
                f"Status: {state.get('status')} | iterations: {state.get('iterations_completed')}/{state.get('max_iterations')}\n"
                f"Events: {len(result.get('iterations') or [])}"
            )
        return f"Unknown /mission command: {cmd}\n\n{_help()}"
    except Exception as exc:
        return f"Mission command failed: {type(exc).__name__}: {exc}"
