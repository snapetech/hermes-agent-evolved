"""Executable BOOT.md-style health checks."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from hermes_constants import get_hermes_home


def _run(argv: list[str], timeout: int = 12) -> tuple[bool, str]:
    if not shutil.which(argv[0]):
        return False, f"{argv[0]} not found"
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"{' '.join(argv)} timed out after {timeout}s"
    except Exception as exc:
        return False, str(exc)
    output = (proc.stdout + ("\n" if proc.stdout and proc.stderr else "") + proc.stderr).strip()
    return proc.returncode == 0, output[:2000]


def _check_kubernetes() -> list[str]:
    ok, output = _run(["kubectl", "get", "pods", "-n", "hermes"])
    if ok:
        bad: list[str] = []
        for line in output.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 3 and parts[2] not in {"Running", "Completed", "Succeeded"}:
                bad.append(line)
        return [f"kubectl pods unhealthy:\n" + "\n".join(bad)] if bad else []
    if "not found" in output:
        return []
    return [f"kubectl check failed: {output}"]


def _check_cron() -> list[str]:
    path = get_hermes_home() / "cron" / "jobs.json"
    if not path.exists():
        return []
    try:
        jobs = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"cron jobs unreadable: {exc}"]
    if not isinstance(jobs, list):
        return [f"cron jobs file has unexpected shape: {path}"]
    bad = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        status = job.get("last_status")
        if status and status != "ok":
            label = job.get("name") or job.get("id") or "unnamed"
            bad.append(f"{label}: last_status={status}")
    return ["cron job failures:\n" + "\n".join(bad[:20])] if bad else []


def _check_ollama() -> list[str]:
    urls = [
        "http://127.0.0.1:11434/api/tags",
        "http://localhost:11434/api/tags",
    ]
    for url in urls:
        try:
            with urlopen(url, timeout=3) as resp:
                if 200 <= resp.status < 300:
                    return []
                return [f"Ollama endpoint returned HTTP {resp.status}: {url}"]
        except Exception:
            continue
    return ["Ollama endpoint is not reachable on localhost:11434"]


def boot_check_command(raw_args: str = "") -> str:
    """`/boot-check` -- run deterministic startup checks."""
    findings: list[str] = []
    findings.extend(_check_kubernetes())
    findings.extend(_check_cron())
    findings.extend(_check_ollama())

    if not findings:
        return "[SILENT]"

    return "Boot check found issues:\n" + "\n".join(f"- {item}" for item in findings)
