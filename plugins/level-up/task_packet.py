"""Structured TaskPacket wrapper around `delegate_task`.

A TaskPacket is a contract-driven work order with an objective, scope,
acceptance tests, commit policy, and escalation policy. Parent agents
invoke the `/task` slash command with a YAML or JSON body and this
module validates the packet, runs the work via the existing
`delegate_task` tool, then executes acceptance tests.

Example:

    /task
    objective: Refactor bootstrap-runtime.sh to split secret loading into its own function.
    scope: deploy/k8s/bootstrap-runtime.sh
    acceptance_tests:
      - shellcheck deploy/k8s/bootstrap-runtime.sh
    commit_policy: none
    escalation_policy: on-failure

The parent never sees the child's intermediate reasoning — only the
structured report.
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

from .escalation import Escalation, escalate

logger = logging.getLogger(__name__)


@dataclass
class TaskPacket:
    objective: str
    scope: str | None = None
    acceptance_tests: list[str] = field(default_factory=list)
    commit_policy: str = "none"              # one of: none, squash, per-step
    escalation_policy: str = "on-failure"    # one of: never, on-failure, always
    max_wall_time: int = 900
    toolsets: list[str] | None = None
    context: str | None = None
    max_diff_lines: int | None = None
    forbid_new_deps: bool = False
    files_touched_must_match: list[str] = field(default_factory=list)


VALID_COMMIT_POLICIES = {"none", "squash", "per-step"}
VALID_ESCALATION_POLICIES = {"never", "on-failure", "always"}


def _parse_packet(raw: str) -> TaskPacket:
    body = (raw or "").strip()
    if not body:
        raise ValueError("TaskPacket body is empty. Supply YAML or JSON.")

    data: Any
    if body.lstrip().startswith("{"):
        data = json.loads(body)
    else:
        try:
            import yaml
        except ImportError as exc:
            raise ValueError("YAML packets require PyYAML; pass JSON instead.") from exc
        data = yaml.safe_load(body)

    if not isinstance(data, dict):
        raise ValueError("TaskPacket must be a JSON/YAML object.")

    objective = (data.get("objective") or "").strip()
    if not objective:
        raise ValueError("TaskPacket.objective is required.")

    commit = (data.get("commit_policy") or "none").strip()
    if commit not in VALID_COMMIT_POLICIES:
        raise ValueError(f"commit_policy must be one of {sorted(VALID_COMMIT_POLICIES)}")

    escalate_policy = (data.get("escalation_policy") or "on-failure").strip()
    if escalate_policy not in VALID_ESCALATION_POLICIES:
        raise ValueError(f"escalation_policy must be one of {sorted(VALID_ESCALATION_POLICIES)}")

    tests_raw = data.get("acceptance_tests") or []
    if isinstance(tests_raw, str):
        tests = [tests_raw]
    else:
        tests = [str(x) for x in tests_raw if str(x).strip()]

    toolsets = data.get("toolsets")
    if isinstance(toolsets, str):
        toolsets = [t.strip() for t in toolsets.split(",") if t.strip()]
    elif isinstance(toolsets, list):
        toolsets = [str(t) for t in toolsets]
    else:
        toolsets = None

    return TaskPacket(
        objective=objective,
        scope=(data.get("scope") or None),
        acceptance_tests=tests,
        commit_policy=commit,
        escalation_policy=escalate_policy,
        max_wall_time=int(data.get("max_wall_time") or 900),
        toolsets=toolsets,
        context=(data.get("context") or None),
        max_diff_lines=(
            int(data["max_diff_lines"])
            if data.get("max_diff_lines") is not None
            else None
        ),
        forbid_new_deps=bool(data.get("forbid_new_deps") or False),
        files_touched_must_match=_normalize_patterns(data.get("files_touched_must_match")),
    )


def _log_path() -> Path:
    path = get_hermes_home() / "level_up" / "tasks.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _run_test(cmd: str, timeout: int) -> dict[str, Any]:
    argv = shlex.split(cmd)
    if not argv:
        return {"cmd": cmd, "ok": False, "error": "empty command"}
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return {
            "cmd": cmd,
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-800:],
            "stderr": proc.stderr[-800:],
        }
    except subprocess.TimeoutExpired:
        return {"cmd": cmd, "ok": False, "error": f"timed out after {timeout}s"}
    except FileNotFoundError:
        return {"cmd": cmd, "ok": False, "error": f"command not found: {argv[0]}"}
    except Exception as exc:
        return {"cmd": cmd, "ok": False, "error": str(exc)}


def _normalize_patterns(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def _git(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *argv], capture_output=True, text=True, timeout=20)


def _changed_files() -> list[str]:
    proc = _git(["diff", "--name-only", "HEAD", "--"])
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _diff_lines() -> int:
    proc = _git(["diff", "--numstat", "HEAD", "--"])
    if proc.returncode != 0:
        return 0
    total = 0
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            for value in parts[:2]:
                if value.isdigit():
                    total += int(value)
    return total


_DEPENDENCY_FILES = (
    "requirements*.txt",
    "constraints*.txt",
    "pyproject.toml",
    "poetry.lock",
    "uv.lock",
    "Pipfile",
    "Pipfile.lock",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
)


def _quality_gates(packet: TaskPacket) -> list[dict[str, Any]]:
    files = _changed_files()
    diff_lines = _diff_lines()
    failures: list[dict[str, Any]] = []

    if packet.max_diff_lines is not None and diff_lines > packet.max_diff_lines:
        failures.append({
            "gate": "max_diff_lines",
            "ok": False,
            "limit": packet.max_diff_lines,
            "actual": diff_lines,
        })

    if packet.forbid_new_deps:
        dep_files = [
            path for path in files
            if any(fnmatch(Path(path).name, pattern) or fnmatch(path, pattern) for pattern in _DEPENDENCY_FILES)
        ]
        if dep_files:
            failures.append({"gate": "forbid_new_deps", "ok": False, "files": dep_files})

    if packet.files_touched_must_match:
        offenders = [
            path for path in files
            if not any(fnmatch(path, pattern) for pattern in packet.files_touched_must_match)
        ]
        if offenders:
            failures.append({
                "gate": "files_touched_must_match",
                "ok": False,
                "patterns": packet.files_touched_must_match,
                "files": offenders,
            })

    return failures


def run_packet(packet: TaskPacket, ctx: Any) -> str:
    """Dispatch the packet through delegate_task and run acceptance checks."""
    args: dict[str, Any] = {
        "goal": packet.objective,
        "max_iterations": 50,
    }
    if packet.context:
        args["context"] = packet.context
    if packet.scope:
        args["context"] = (args.get("context", "") + f"\n\nSCOPE: {packet.scope}").strip()
    if packet.toolsets:
        args["toolsets"] = packet.toolsets

    start = time.time()
    try:
        delegate_result = ctx.dispatch_tool("delegate_task", args)
    except Exception as exc:
        _log_event({"ts": time.time(), "packet": packet.__dict__, "error": str(exc)})
        if packet.escalation_policy != "never":
            escalate(Escalation(
                reason=f"TaskPacket dispatch failed: {exc}",
                category="tool_crash",
                severity="error",
                details={"packet": packet.__dict__},
            ))
        return f"TaskPacket dispatch failed: {exc}"

    tests = [_run_test(cmd, timeout=max(30, packet.max_wall_time // 4)) for cmd in packet.acceptance_tests]
    failed = [t for t in tests if not t.get("ok")]
    gate_failures = _quality_gates(packet)

    event = {
        "ts": time.time(),
        "duration_s": round(time.time() - start, 1),
        "packet": packet.__dict__,
        "delegate_result_excerpt": (delegate_result or "")[:1200],
        "tests": tests,
        "quality_gates": gate_failures,
        "success": not failed and not gate_failures,
    }
    _log_event(event)

    if packet.escalation_policy == "always" or (packet.escalation_policy == "on-failure" and (failed or gate_failures)):
        escalate(Escalation(
            reason=f"TaskPacket {'failed' if failed or gate_failures else 'completed'}: {packet.objective[:120]}",
            category="task_packet",
            severity="error" if failed or gate_failures else "info",
            details={
                "failed_tests": [t.get("cmd") for t in failed],
                "quality_gates": gate_failures,
                "duration_s": event["duration_s"],
            },
        ))

    lines = [
        f"TaskPacket: {packet.objective}",
        f"- duration: {event['duration_s']}s",
        f"- tests: {len(tests)} ({len(failed)} failed)",
        f"- quality gates: {len(gate_failures)} failed",
    ]
    for test in tests:
        marker = "✅" if test.get("ok") else "❌"
        lines.append(f"  {marker} {test['cmd']}")
    if failed:
        lines.append("Delegate output (excerpt):")
        lines.append((delegate_result or "")[:600])
    if gate_failures:
        lines.append("Quality gate failures:")
        for failure in gate_failures:
            lines.append(f"  - {failure['gate']}: {json.dumps(failure, ensure_ascii=False)}")
    return "\n".join(lines)


def _log_event(event: dict[str, Any]) -> None:
    with _log_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def task_command(raw_args: str = "", *, ctx: Any = None) -> str:
    """`/task` — run a structured TaskPacket."""
    if ctx is None:
        return "TaskPacket requires plugin context (internal error)."
    try:
        packet = _parse_packet(raw_args)
    except Exception as exc:
        return f"Invalid TaskPacket: {exc}\n\nExpected YAML or JSON with at least `objective:`."
    return run_packet(packet, ctx)
