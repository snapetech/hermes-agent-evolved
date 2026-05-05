"""Ops Runtime dashboard plugin backend."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import yaml
from fastapi import APIRouter

from hermes_constants import get_hermes_home

router = APIRouter()


def _run(argv: list[str], timeout: int = 5) -> dict[str, Any]:
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except FileNotFoundError:
        return {"ok": False, "error": f"{argv[0]} not found"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"{argv[0]} timed out after {timeout}s"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _load_config() -> dict[str, Any]:
    cfg_path = get_hermes_home() / "config.yaml"
    try:
        return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _ollama_ps(base_url: str) -> dict[str, Any]:
    if not base_url:
        return {"ok": False, "error": "model.base_url not configured"}
    root = base_url.removesuffix("/v1").rstrip("/")
    try:
        req = Request(f"{root}/api/ps", headers={"Accept": "application/json"})
        with urlopen(req, timeout=3) as resp:
            return {"ok": True, "data": json.loads(resp.read().decode("utf-8"))}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _session_stats() -> dict[str, Any]:
    db_path = get_hermes_home() / "state.db"
    if not db_path.exists():
        return {"ok": False, "error": "state.db not found", "path": str(db_path)}
    try:
        conn = sqlite3.connect(str(db_path), timeout=1.0)
        conn.row_factory = sqlite3.Row
        now = time.time()
        active = conn.execute("SELECT COUNT(*) FROM sessions WHERE ended_at IS NULL").fetchone()[0]
        stale = conn.execute(
            """
            SELECT COUNT(*)
            FROM sessions s
            WHERE s.ended_at IS NULL
              AND COALESCE((SELECT MAX(m.timestamp) FROM messages m WHERE m.session_id = s.id), s.started_at) < ?
            """,
            (now - 6 * 60 * 60,),
        ).fetchone()[0]
        recent = [
            dict(row)
            for row in conn.execute(
                """
                SELECT s.id, s.source, s.model, s.started_at, s.ended_at,
                       COALESCE((SELECT MAX(m.timestamp) FROM messages m WHERE m.session_id = s.id), s.started_at) AS last_active,
                       (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS messages
                FROM sessions s
                ORDER BY last_active DESC
                LIMIT 8
                """
            ).fetchall()
        ]
        return {"ok": True, "active": active, "stale_6h": stale, "recent": recent}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "path": str(db_path)}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _cron_stats() -> dict[str, Any]:
    path = get_hermes_home() / "cron" / "jobs.json"
    if not path.exists():
        return {"ok": True, "jobs": 0, "enabled": 0, "failures": 0, "recent_failures": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        jobs = data.get("jobs", [])
        failures = [
            {
                "id": job.get("id"),
                "name": job.get("name"),
                "last_error": job.get("last_error"),
                "last_delivery_error": job.get("last_delivery_error"),
                "last_run_at": job.get("last_run_at"),
            }
            for job in jobs
            if job.get("last_status") == "error" or job.get("last_delivery_error")
        ]
        return {
            "ok": True,
            "jobs": len(jobs),
            "enabled": sum(1 for job in jobs if job.get("enabled", True)),
            "failures": len(failures),
            "recent_failures": failures[-5:],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "path": str(path)}


def _mcp_processes() -> dict[str, Any]:
    result = _run(["ps", "-eo", "pid,ppid,rss,etime,command"], timeout=5)
    if not result.get("ok"):
        return result
    rows = []
    for line in result.get("stdout", "").splitlines()[1:]:
        lower = line.lower()
        if "mcp" not in lower and "modelcontextprotocol" not in lower:
            continue
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        rows.append(
            {
                "pid": parts[0],
                "ppid": parts[1],
                "rss_kb": parts[2],
                "etime": parts[3],
                "command": parts[4],
            }
        )
    return {"ok": True, "count": len(rows), "processes": rows[:20]}


def _hooks_state() -> dict[str, Any]:
    hooks_dir = get_hermes_home() / "hooks"
    boot = get_hermes_home() / "BOOT.md"
    hooks = sorted(p.name for p in hooks_dir.iterdir() if p.is_dir()) if hooks_dir.is_dir() else []
    return {
        "ok": True,
        "boot_md": str(boot) if boot.exists() else None,
        "hooks": hooks,
    }


def _alerts(snapshot: dict[str, Any]) -> list[str]:
    alerts: list[str] = []
    sessions = snapshot.get("sessions") or {}
    cron = snapshot.get("cron") or {}
    mcp = snapshot.get("mcp_processes") or {}
    kubernetes = snapshot.get("kubernetes") or {}

    if sessions.get("stale_6h", 0) > 0:
        alerts.append(f"{sessions['stale_6h']} active sessions have been stale for more than 6h")
    if cron.get("failures", 0) > 0:
        alerts.append(f"{cron['failures']} cron jobs have recent failures")
    if mcp.get("count", 0) > 12:
        alerts.append(f"{mcp['count']} MCP-like child processes are running")
    if kubernetes and not kubernetes.get("ok"):
        alerts.append("kubectl health snapshot failed")
    return alerts


@router.get("/snapshot")
async def snapshot():
    cfg = _load_config()
    model_cfg = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
    terminal_cfg = cfg.get("terminal") if isinstance(cfg.get("terminal"), dict) else {}
    gateway_cfg = cfg.get("gateway") if isinstance(cfg.get("gateway"), dict) else {}
    memory_cfg = cfg.get("memory") if isinstance(cfg.get("memory"), dict) else {}

    kubectl = _run(
        [
            "kubectl",
            "-n",
            os.getenv("HERMES_K8S_NAMESPACE", "hermes"),
            "get",
            "deploy,svc,pod",
            "-o",
            "wide",
        ],
        timeout=8,
    )

    processes_path = get_hermes_home() / "processes.json"
    try:
        processes = json.loads(processes_path.read_text(encoding="utf-8"))
    except Exception:
        processes = []

    profiles_root = Path.home() / ".hermes" / "profiles"
    profiles = sorted(p.name for p in profiles_root.iterdir() if p.is_dir()) if profiles_root.is_dir() else []

    snapshot_data = {
        "hermes_home": str(get_hermes_home()),
        "model": {
            "default": model_cfg.get("default"),
            "provider": model_cfg.get("provider"),
            "base_url": model_cfg.get("base_url"),
            "context_length": model_cfg.get("context_length"),
            "ollama_num_ctx": model_cfg.get("ollama_num_ctx"),
        },
        "runtime": {
            "terminal_backend": terminal_cfg.get("backend"),
            "terminal_cwd": terminal_cfg.get("cwd"),
            "approvals_mode": (cfg.get("approvals") or {}).get("mode"),
            "checkpoints": cfg.get("checkpoints"),
            "gateway_worktrees": gateway_cfg.get("worktrees"),
            "memory_provider": memory_cfg.get("provider"),
            "mcp_servers": sorted((cfg.get("mcp_servers") or {}).keys()),
            "profiles": profiles,
            "background_processes": len(processes) if isinstance(processes, list) else 0,
        },
        "kubernetes": kubectl,
        "ollama": _ollama_ps(str(model_cfg.get("base_url") or "")),
        "sessions": _session_stats(),
        "cron": _cron_stats(),
        "mcp_processes": _mcp_processes(),
        "hooks": _hooks_state(),
    }
    snapshot_data["alerts"] = _alerts(snapshot_data)
    return snapshot_data
