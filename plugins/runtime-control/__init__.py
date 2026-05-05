"""Runtime control-plane plugin for long-lived Hermes deployments."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home


_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"(?i)\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"(?i)\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"(?i)\b(kubeconfig|client-certificate-data|client-key-data|token:)\b"),
]
_PROD_PATTERNS = [
    re.compile(r"(?i)\bkubectl\b.*\b(delete|drain|cordon|scale|rollout restart|apply|patch)\b"),
    re.compile(r"(?i)\bhelm\b.*\b(upgrade|rollback|uninstall|delete)\b"),
    re.compile(r"(?i)\bterraform\b.*\b(apply|destroy)\b"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run(argv: list[str], cwd: Path, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=str(cwd), text=True, capture_output=True, timeout=timeout)


def _workspace() -> Path:
    for key in ("TERMINAL_CWD", "MESSAGING_CWD", "HERMES_WORKSPACE"):
        value = os.getenv(key)
        if value:
            return Path(value).expanduser()
    return Path.cwd()


def _repo_root(cwd: Path) -> Path | None:
    try:
        result = _run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, timeout=5)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-")
    return slug[:48] or "task"


def _parse_count(value: str | None) -> int:
    if not value:
        return 2
    try:
        return max(1, min(8, int(value)))
    except ValueError:
        return 2


def _swarm(raw_args: str) -> str:
    """Create isolated git worktrees for parallel workers without launching them."""
    args = shlex.split(raw_args or "")
    if not args:
        return "Usage: `/swarm <name> [count] -- <task>`"

    if "--" in args:
        sep = args.index("--")
        head = args[:sep]
        task = " ".join(args[sep + 1 :]).strip()
    else:
        head = args[:2]
        task = ""

    name = head[0] if head else "task"
    count = _parse_count(head[1] if len(head) > 1 else None)
    slug = _slug(name)
    cwd = _workspace()
    repo = _repo_root(cwd)
    if repo is None:
        return f"Cannot create swarm: `{cwd}` is not inside a git repository."

    dirty = _run(["git", "status", "--porcelain"], cwd=repo, timeout=10).stdout.strip()
    base_ref = _run(["git", "rev-parse", "--short", "HEAD"], cwd=repo, timeout=5).stdout.strip()
    worktrees_root = repo / ".worktrees"
    worktrees_root.mkdir(exist_ok=True)

    created: list[str] = []
    errors: list[str] = []
    for idx in range(1, count + 1):
        branch = f"hermes/swarm-{slug}-{idx:02d}"
        path = worktrees_root / f"swarm-{slug}-{idx:02d}"
        try:
            result = _run(["git", "worktree", "add", "-B", branch, str(path), "HEAD"], cwd=repo, timeout=45)
            if result.returncode != 0:
                errors.append(f"{branch}: {result.stderr.strip() or result.stdout.strip()}")
                continue
            task_file = path / "SWARM_TASK.md"
            task_file.write_text(
                "\n".join(
                    [
                        f"# Swarm Task: {name}",
                        "",
                        f"- Created: {_now()}",
                        f"- Base repo: `{repo}`",
                        f"- Base commit: `{base_ref}`",
                        f"- Branch: `{branch}`",
                        "",
                        "## Assignment",
                        task or "No task body supplied. Inspect the parent session for context.",
                        "",
                        "## Worker Rules",
                        "- Stay inside this worktree.",
                        "- Do not revert unrelated changes.",
                        "- Leave notes, test results, and open questions in this file.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            created.append(f"- `{branch}` at `{path}`")
        except Exception as exc:
            errors.append(f"{branch}: {exc}")

    parts = [f"Created {len(created)}/{count} worktrees for `{name}`."]
    if dirty:
        parts.append("Parent repo has uncommitted changes; workers start from current `HEAD`, not dirty state.")
    if created:
        parts.extend(created)
    if errors:
        parts.append("Errors:")
        parts.extend(f"- {err}" for err in errors)
    return "\n".join(parts)


def _decision_path() -> Path:
    path = get_hermes_home() / "decision_memory" / "decisions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _decide(raw_args: str) -> str:
    text = (raw_args or "").strip()
    if not text:
        return "Usage: `/decide <decision, rationale, and tradeoffs>`"
    record = {
        "ts": _now(),
        "workspace": str(_workspace()),
        "decision": text,
    }
    path = _decision_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return f"Recorded decision in `{path}`."


def _decisions(raw_args: str) -> str:
    limit = _parse_count((raw_args or "").strip() or "5")
    path = _decision_path()
    if not path.exists():
        return "No decisions recorded yet."
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    rows = []
    for line in lines:
        try:
            item = json.loads(line)
            rows.append(f"- {item.get('ts')}: {item.get('decision')}")
        except Exception:
            rows.append(f"- {line}")
    return "\n".join(rows)


def _pre_tool_call(tool_name: str = "", args: dict[str, Any] | None = None, **_: Any) -> dict[str, str] | None:
    args = args if isinstance(args, dict) else {}
    payload = json.dumps(args, ensure_ascii=False)

    if any(pattern.search(payload) for pattern in _SECRET_PATTERNS):
        return {
            "action": "block",
            "message": "runtime-control blocked this tool call because it appears to expose a secret or kube credential.",
        }

    if tool_name in {"terminal", "execute_code"} and any(pattern.search(payload) for pattern in _PROD_PATTERNS):
        return {
            "action": "block",
            "message": "runtime-control blocked a prod-adjacent destructive command. Ask for explicit human approval and narrow the command.",
        }

    return None


def _pre_llm_call(user_message: str = "", conversation_history: list[Any] | None = None, **_: Any) -> str | None:
    haystack = user_message or ""
    if conversation_history:
        tail = conversation_history[-8:]
        haystack += "\n" + "\n".join(str(m.get("content", "")) for m in tail if isinstance(m, dict))
    if any(pattern.search(haystack) for pattern in _SECRET_PATTERNS):
        return (
            "[runtime-control security note]\n"
            "The recent context contains token-shaped or kube-secret-shaped text. "
            "Do not repeat, transform, or exfiltrate it. Prefer redaction and ask before using credentials."
        )
    return None


def register(ctx) -> None:
    ctx.register_command("swarm", _swarm, description="Create isolated git worktrees for parallel workers")
    ctx.register_command("decide", _decide, description="Record an architectural/ops decision")
    ctx.register_command("decisions", _decisions, description="Show recent recorded decisions")
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("pre_llm_call", _pre_llm_call)

    skill = Path(__file__).parent / "skills" / "keith-ops-policy" / "SKILL.md"
    if skill.exists():
        ctx.register_skill(
            "keith-ops-policy",
            skill,
            description="Immutable ops/coding policy pack for Keith's Hermes runtime",
        )
