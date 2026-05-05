#!/usr/bin/env python3
"""Audit drift between the checked-in Hermes bundle and a live pod.

The report is intentionally redacted. It compares hashes, commit refs, package
manifests, cron templates, and skill manifests without exporting live secrets,
sessions, logs, or private workspace contents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CRON_SEED = ROOT / "deploy/k8s/cron-seed.example.json"
DEFAULT_SKILL_LOCK = ROOT / "deploy/k8s/skills.lock.example.json"
SECRET_RE = re.compile(
    r"(?i)(token|secret|password|authorization|api[_-]?key|id_ed25519|private[_-]?key|"
    r"discord[_-]?bot|auth\\.json|\\.env|\\.netrc)"
)
PRIVATE_VALUE_RE = re.compile(r"(?i)([A-Z0-9_]*(TOKEN|SECRET|PASSWORD|KEY)[A-Z0-9_]*=)[^\\s]+")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if SECRET_RE.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        text = PRIVATE_VALUE_RE.sub(r"\1[REDACTED]", value)
        text = re.sub(r"/home/[^/\\s`'\"]+", "/home/<user>", text)
        return text
    return value


def run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 20) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except Exception as exc:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_value(args: list[str], cwd: Path = ROOT) -> str | None:
    result = run(["git", *args], cwd=cwd, timeout=10)
    if result["ok"]:
        return result["stdout"].strip()
    return None


def repo_config_hash(configmap: Path = ROOT / "deploy/k8s/configmap.yaml") -> str | None:
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(configmap.read_text(encoding="utf-8"))
        config = data.get("data", {}).get("config.yaml")
        if isinstance(config, str):
            return sha256_text(config)
    except Exception:
        pass
    return None


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def expected_cron_names(path: Path = DEFAULT_CRON_SEED) -> list[str]:
    data = load_json(path) or {}
    return sorted(str(job.get("name")) for job in data.get("jobs", []) if job.get("name"))


def expected_skill_names(path: Path = DEFAULT_SKILL_LOCK) -> list[str]:
    data = load_json(path) or {}
    return sorted(str(item.get("name")) for item in data.get("skills", []) if item.get("name"))


def repo_skill_names() -> list[str]:
    names = set()
    for root in (ROOT / "skills", ROOT / "optional-skills"):
        if not root.exists():
            continue
        for skill in root.rglob("SKILL.md"):
            names.add(skill.parent.name)
    return sorted(names)


def kubectl(args: list[str], *, namespace: str, kubectl_cmd: str = "kubectl", timeout: int = 25) -> dict[str, Any]:
    return run([*shlex.split(kubectl_cmd), "-n", namespace, *args], timeout=timeout)


def live_exec(
    command: str,
    *,
    namespace: str,
    target: str,
    container: str,
    kubectl_cmd: str = "kubectl",
    timeout: int = 25,
) -> dict[str, Any]:
    return kubectl(
        ["exec", target, "-c", container, "--", "sh", "-lc", command],
        namespace=namespace,
        kubectl_cmd=kubectl_cmd,
        timeout=timeout,
    )


def collect_live(namespace: str, target: str, container: str, hermes_home: str, kubectl_cmd: str) -> dict[str, Any]:
    deploy = kubectl(["get", target.replace("deploy/", "deploy/"), "-o", "json"], namespace=namespace, kubectl_cmd=kubectl_cmd)
    images: dict[str, str] = {}
    if deploy["ok"] and deploy["stdout"]:
        try:
            payload = json.loads(deploy["stdout"])
            spec = payload.get("spec", {}).get("template", {}).get("spec", {})
            for section in ("initContainers", "containers"):
                for item in spec.get(section, []) or []:
                    images[item.get("name", section)] = item.get("image", "")
        except json.JSONDecodeError:
            pass

    cm = kubectl(
        ["get", "configmap", "hermes-bootstrap", "-o", "jsonpath={.data.config\\.yaml}"],
        namespace=namespace,
        kubectl_cmd=kubectl_cmd,
    )
    live_configmap_hash = sha256_text(cm["stdout"]) if cm["ok"] else None

    script = rf'''
python3 - <<'PY'
import hashlib
import json
import subprocess
from pathlib import Path

home = Path({hermes_home!r})

def run(cmd, cwd=None):
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""

def sha(path):
    p = Path(path)
    if not p.exists():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

repo = home / "hermes-agent"
upstream = run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{{upstream}}"], cwd=repo) if repo.exists() else ""
payload = {{
    "config_hash": sha(home / "config.yaml"),
    "memory_hash": sha(home / "MEMORY.md"),
    "app_commit": run(["git", "rev-parse", "HEAD"], cwd=Path("/app")),
    "data_repo_head": run(["git", "rev-parse", "HEAD"], cwd=repo) if repo.exists() else "",
    "data_repo_branch": run(["git", "branch", "--show-current"], cwd=repo) if repo.exists() else "",
    "data_repo_upstream": upstream,
    "data_repo_ahead_behind": run(["git", "rev-list", "--left-right", "--count", f"{{upstream}}...HEAD"], cwd=repo) if upstream else "",
    "data_repo_dirty": bool(run(["git", "status", "--short"], cwd=repo)) if repo.exists() else False,
    "cron_names": [],
    "skill_names": [],
}}
jobs = home / "cron/jobs.json"
if jobs.exists():
    data = json.loads(jobs.read_text())
    payload["cron_names"] = sorted(j.get("name") for j in data.get("jobs", []) if j.get("name"))
skills = home / "skills"
if skills.exists():
    payload["skill_names"] = sorted(p.parent.name for p in skills.rglob("SKILL.md"))
print(json.dumps(payload))
PY
'''
    state = live_exec(script, namespace=namespace, target=target, container=container, kubectl_cmd=kubectl_cmd, timeout=30)
    parsed: dict[str, Any] = {}
    if state["ok"] and state["stdout"]:
        try:
            parsed = json.loads(state["stdout"])
        except json.JSONDecodeError:
            parsed = {"parse_error": state["stdout"][:1000]}
    else:
        parsed = {"error": state["stderr"][:1000]}

    parsed["images"] = images
    parsed["configmap_config_hash"] = live_configmap_hash
    return parsed


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    local = {
        "root": str(ROOT),
        "head": git_value(["rev-parse", "HEAD"]),
        "branch": git_value(["branch", "--show-current"]),
        "upstream": git_value(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]),
        "repo_config_hash": repo_config_hash(),
        "expected_cron_names": expected_cron_names(Path(args.cron_seed)),
        "expected_skill_names": expected_skill_names(Path(args.skill_lock)),
        "repo_skill_count": len(repo_skill_names()),
    }

    live = {} if args.skip_live else collect_live(
        args.namespace,
        args.target,
        args.container,
        args.hermes_home,
        args.kubectl,
    )
    findings = []

    if live:
        image_values = " ".join(live.get("images", {}).values())
        local_head = local.get("head")
        app_commit = live.get("app_commit")
        if local_head and local_head[:8] not in image_values and app_commit != local_head:
            findings.append({
                "severity": "warn",
                "area": "image",
                "message": "Live image/app commit does not match local repo HEAD.",
            })
        if live.get("data_repo_ahead_behind"):
            left, _, right = str(live["data_repo_ahead_behind"]).partition("\t")
            if left and left != "0":
                findings.append({
                    "severity": "error",
                    "area": "persistent_repo",
                    "message": f"Persistent repo is behind its upstream by {left} commits.",
                })
            if right and right != "0":
                findings.append({
                    "severity": "warn",
                    "area": "persistent_repo",
                    "message": f"Persistent repo is ahead of its upstream by {right} commits.",
                })
        if local_head and live.get("data_repo_head") and live.get("data_repo_head") != local_head:
            findings.append({
                "severity": "warn",
                "area": "persistent_repo",
                "message": "Persistent repo HEAD does not match local repo HEAD.",
            })
        if live.get("data_repo_dirty"):
            findings.append({
                "severity": "warn",
                "area": "persistent_repo",
                "message": "Persistent repo has uncommitted changes.",
            })
        if local.get("repo_config_hash") and live.get("configmap_config_hash") != local.get("repo_config_hash"):
            findings.append({
                "severity": "error",
                "area": "configmap",
                "message": "Live hermes-bootstrap config.yaml differs from repo deploy/k8s/configmap.yaml.",
            })
        if live.get("config_hash") and live.get("configmap_config_hash") != live.get("config_hash"):
            findings.append({
                "severity": "error",
                "area": "config",
                "message": "Live /opt/data/config.yaml differs from mounted ConfigMap config.yaml.",
            })

        cron_missing = sorted(set(local["expected_cron_names"]) - set(live.get("cron_names", [])))
        if cron_missing:
            findings.append({
                "severity": "warn",
                "area": "cron",
                "message": "Expected seeded cron jobs are missing in live pod.",
                "items": cron_missing,
            })
        skill_missing = sorted(set(local["expected_skill_names"]) - set(live.get("skill_names", [])))
        if skill_missing:
            findings.append({
                "severity": "warn",
                "area": "skills",
                "message": "Expected seeded skills are missing in live pod.",
                "items": skill_missing,
            })

    return redact({"local": local, "live": live, "findings": findings})


def markdown(report: dict[str, Any]) -> str:
    lines = ["# Hermes Live Reproducibility Audit", ""]
    lines.append("## Summary")
    lines.append("")
    findings = report.get("findings", [])
    if findings:
        for item in findings:
            suffix = ""
            if item.get("items"):
                suffix = " " + ", ".join(f"`{x}`" for x in item["items"])
            lines.append(f"- **{item.get('severity')}** `{item.get('area')}`: {item.get('message')}{suffix}")
    else:
        lines.append("- No reproducibility drift findings.")

    local = report.get("local", {})
    live = report.get("live", {})
    lines.extend([
        "",
        "## Local Repo",
        "",
        f"- Root: `{local.get('root')}`",
        f"- Branch: `{local.get('branch')}`",
        f"- HEAD: `{local.get('head')}`",
        f"- Config hash: `{local.get('repo_config_hash')}`",
        f"- Repo skill count: `{local.get('repo_skill_count')}`",
        "",
        "## Live Pod",
        "",
    ])
    if live:
        lines.extend([
            f"- Images: `{live.get('images')}`",
            f"- App commit: `{live.get('app_commit')}`",
            f"- Persistent repo HEAD: `{live.get('data_repo_head')}`",
            f"- Persistent repo upstream: `{live.get('data_repo_upstream')}`",
            f"- Persistent repo ahead/behind: `{live.get('data_repo_ahead_behind')}`",
            f"- Persistent repo dirty: `{live.get('data_repo_dirty')}`",
            f"- ConfigMap config hash: `{live.get('configmap_config_hash')}`",
            f"- /opt/data config hash: `{live.get('config_hash')}`",
            f"- Cron jobs: `{len(live.get('cron_names') or [])}`",
            f"- Skills: `{len(live.get('skill_names') or [])}`",
        ])
    else:
        lines.append("- Live collection skipped.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default="hermes")
    parser.add_argument("--target", default="deploy/hermes-gateway")
    parser.add_argument("--container", default="gateway")
    parser.add_argument("--hermes-home", default="/opt/data")
    parser.add_argument("--kubectl", default=os.getenv("KUBECTL", "kubectl"), help="kubectl command, e.g. 'sudo kubectl'")
    parser.add_argument("--cron-seed", default=str(DEFAULT_CRON_SEED))
    parser.add_argument("--skill-lock", default=str(DEFAULT_SKILL_LOCK))
    parser.add_argument("--skip-live", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    report = build_report(args)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n" if args.json else markdown(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 1 if any(item.get("severity") == "error" for item in report.get("findings", [])) else 0


if __name__ == "__main__":
    raise SystemExit(main())
