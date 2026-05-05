#!/usr/bin/env python3
"""Maintain a Hermes stack inventory and check dependencies for known CVEs.

The script is intentionally conservative:

* inventory generation is local and deterministic;
* vulnerability checks use ecosystem-native audit data where available and OSV
  for package/version lookups;
* remediation is reported as proposals only.  It never edits dependency pins or
  lockfiles unless a human/agent explicitly performs a follow-up change.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _looks_like_repo(path: Path) -> bool:
    return (path / "pyproject.toml").exists() and (path / "run_agent.py").exists()


def _resolve_root() -> Path:
    explicit = os.getenv("HERMES_STACK_REPO")
    if explicit:
        return Path(explicit).expanduser().resolve()

    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if _looks_like_repo(candidate):
            return candidate

    hermes_home = os.getenv("HERMES_HOME")
    if hermes_home:
        home = Path(hermes_home).expanduser()
        for candidate in (
            home / "hermes-agent",
            home / "workspace" / "hermes-agent",
            home / "workspace" / "hermes-agent-private",
        ):
            if _looks_like_repo(candidate):
                return candidate.resolve()

    return SOURCE_ROOT


ROOT = _resolve_root()
DEFAULT_INVENTORY = ROOT / "docs" / "stack-inventory.json"
DEFAULT_REPORT = ROOT / "docs" / "stack-cve-report.md"
OSV_BATCH_URL = os.getenv("OSV_BATCH_URL", "https://api.osv.dev/v1/querybatch")
OSV_TIMEOUT = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 60) -> dict[str, Any]:
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
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "stdout": "", "stderr": ""}


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _load_pyproject() -> dict[str, Any]:
    path = ROOT / "pyproject.toml"
    if not path.exists():
        return {}
    with path.open("rb") as f:
        data = tomllib.load(f)
    project = data.get("project", {})
    optional = project.get("optional-dependencies", {})
    return {
        "dependencies": project.get("dependencies", []),
        "optional_dependencies": optional,
        "requires_python": project.get("requires-python"),
    }


def _load_requirements() -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for path in sorted(ROOT.glob("requirements*.txt")):
        lines = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if line:
                lines.append(line)
        results.append({"path": str(path.relative_to(ROOT)), "entries": lines})
    return results


def _installed_python_packages() -> list[dict[str, str]]:
    packages = []
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name")
        version = dist.version
        if name and version:
            packages.append({"name": name, "version": version, "ecosystem": "PyPI"})
    return sorted(packages, key=lambda item: item["name"].lower())


def _npm_name_from_package_path(package_path: str) -> str | None:
    prefix = "node_modules/"
    if not package_path.startswith(prefix):
        return None
    name = package_path[len(prefix) :]
    parts = name.split("/")
    if not parts:
        return None
    if parts[0].startswith("@") and len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


def _load_npm_lock(lock_path: Path) -> dict[str, Any]:
    data = _read_json(lock_path)
    packages = []
    for package_path, meta in (data.get("packages") or {}).items():
        name = _npm_name_from_package_path(package_path)
        version = meta.get("version") if isinstance(meta, dict) else None
        if name and version:
            packages.append({"name": name, "version": str(version), "ecosystem": "npm"})
    return {
        "path": str(lock_path.relative_to(ROOT)),
        "package_count": len(packages),
        "packages": sorted(packages, key=lambda item: item["name"].lower()),
    }


def _npm_locks() -> list[dict[str, Any]]:
    locks = []
    for lock_path in sorted(ROOT.glob("**/package-lock.json")):
        if "node_modules" in lock_path.parts:
            continue
        try:
            locks.append(_load_npm_lock(lock_path))
        except Exception as exc:
            locks.append({
                "path": str(lock_path.relative_to(ROOT)),
                "error": f"{type(exc).__name__}: {exc}",
                "packages": [],
            })
    return locks


def _tool_inventory() -> dict[str, Any]:
    # Static import only; avoid dynamic MCP discovery during inventory generation.
    from toolsets import TOOLSETS, _HERMES_CORE_TOOLS

    return {
        "core_tools": list(_HERMES_CORE_TOOLS),
        "toolsets": {
            name: {
                "description": meta.get("description"),
                "tools": meta.get("tools", []),
                "includes": meta.get("includes", []),
            }
            for name, meta in sorted(TOOLSETS.items())
        },
    }


def _skill_inventory() -> dict[str, Any]:
    roots = [ROOT / "skills", ROOT / "optional-skills"]
    try:
        from hermes_constants import get_hermes_home
        roots.append(get_hermes_home() / "skills")
    except Exception:
        pass

    entries = []
    for root in roots:
        if not root.exists():
            continue
        for skill in sorted(root.rglob("SKILL.md")):
            entries.append({
                "path": str(skill),
                "root": str(root),
                "name": skill.parent.name,
            })
    return {"count": len(entries), "skills": entries}


def _external_binaries() -> dict[str, str | None]:
    names = [
        "python", "pip", "node", "npm", "npx", "git", "rg", "docker", "kubectl",
        "helm", "gh", "ffmpeg", "agent-browser", "uv", "uvx",
    ]
    return {name: shutil.which(name) for name in names}


def _npm_global_packages() -> dict[str, Any]:
    npm = shutil.which("npm")
    if not npm:
        return {"available": False, "packages": []}
    result = _run([npm, "list", "-g", "--depth=0", "--json"], timeout=30)
    packages = []
    if result.get("stdout"):
        try:
            data = json.loads(result["stdout"])
            for name, meta in sorted((data.get("dependencies") or {}).items()):
                version = meta.get("version") if isinstance(meta, dict) else None
                packages.append({"name": name, "version": str(version), "ecosystem": "npm"})
        except json.JSONDecodeError:
            pass
    return {
        "available": True,
        "ok": result.get("returncode") == 0,
        "packages": packages,
        "error": result.get("error") or (result.get("stderr") or "").strip()[:1000],
    }


def _system_packages() -> dict[str, Any]:
    if shutil.which("dpkg-query"):
        result = _run(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Architecture}\n"], timeout=30)
        packages = []
        if result.get("stdout"):
            for line in result["stdout"].splitlines():
                parts = line.split("\t")
                if len(parts) == 3:
                    packages.append({"name": parts[0], "version": parts[1], "arch": parts[2], "manager": "dpkg"})
        return {"manager": "dpkg", "ok": result.get("ok"), "packages": packages}

    if shutil.which("rpm"):
        result = _run(["rpm", "-qa", "--queryformat", "%{NAME}\t%{VERSION}-%{RELEASE}\t%{ARCH}\n"], timeout=30)
        packages = []
        if result.get("stdout"):
            for line in result["stdout"].splitlines():
                parts = line.split("\t")
                if len(parts) == 3:
                    packages.append({"name": parts[0], "version": parts[1], "arch": parts[2], "manager": "rpm"})
        return {"manager": "rpm", "ok": result.get("ok"), "packages": packages}

    return {"manager": None, "ok": False, "packages": []}


def _kubernetes_images(namespace: str = "hermes") -> dict[str, Any]:
    kubectl = shutil.which("kubectl")
    if not kubectl:
        return {"available": False, "namespace": namespace, "images": []}
    template = "{range .items[*].spec.containers[*]}{.image}{\"\\n\"}{end}"
    result = _run([kubectl, "-n", namespace, "get", "pods", "-o", f"jsonpath={template}"], timeout=15)
    images = sorted({line.strip() for line in (result.get("stdout") or "").splitlines() if line.strip()})
    return {
        "available": True,
        "namespace": namespace,
        "ok": result.get("ok"),
        "images": images,
        "error": result.get("error") or (result.get("stderr") or "").strip()[:1000],
    }


def _workspace_repos() -> list[dict[str, Any]]:
    roots: list[Path] = [ROOT]
    hermes_home = os.getenv("HERMES_HOME")
    if hermes_home:
        roots.append(Path(hermes_home).expanduser() / "workspace")

    marker_names = {
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "package-lock.json",
        "go.mod",
        "Cargo.toml",
    }
    repos: dict[str, dict[str, Any]] = {}
    for root in roots:
        if not root.exists():
            continue
        children = [root] if _looks_like_repo(root) else sorted(root.iterdir())
        for child in children:
            if not child.is_dir() or child.name.startswith("."):
                continue
            manifests = sorted(name for name in marker_names if (child / name).exists())
            if manifests:
                repos[str(child.resolve())] = {"path": str(child.resolve()), "manifests": manifests}
    return sorted(repos.values(), key=lambda item: item["path"])


def _git_metadata() -> dict[str, Any]:
    if not (ROOT / ".git").exists():
        return {"tracked": False, "root": str(ROOT), "source_root": str(SOURCE_ROOT)}

    def git(args: list[str], timeout: int = 10) -> str | None:
        result = _run(["git", *args], cwd=ROOT, timeout=timeout)
        if result.get("ok"):
            return (result.get("stdout") or "").strip()
        return None

    status = git(["status", "--short"])
    upstream = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])
    ahead_behind = None
    if upstream:
        ahead_behind = git(["rev-list", "--left-right", "--count", f"{upstream}...HEAD"])

    return {
        "tracked": True,
        "root": str(ROOT),
        "source_root": str(SOURCE_ROOT),
        "branch": git(["branch", "--show-current"]),
        "head": git(["rev-parse", "HEAD"]),
        "upstream": upstream,
        "ahead_behind": ahead_behind,
        "dirty": bool(status),
        "status_short": status.splitlines() if status else [],
    }


def build_inventory() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": _now(),
        "root": str(ROOT),
        "source_root": str(SOURCE_ROOT),
        "git": _git_metadata(),
        "platform": {
            "python": sys.version.split()[0],
            "executable": sys.executable,
            "system": platform.platform(),
        },
        "python": {
            "pyproject": _load_pyproject(),
            "requirements": _load_requirements(),
            "installed": _installed_python_packages(),
        },
        "node": {"locks": _npm_locks()},
        "tools": _tool_inventory(),
        "skills": _skill_inventory(),
        "external_binaries": _external_binaries(),
        "runtime": {
            "npm_globals": _npm_global_packages(),
            "system_packages": _system_packages(),
            "kubernetes_images": _kubernetes_images(),
            "workspace_repos": _workspace_repos(),
        },
    }


def write_inventory(path: Path = DEFAULT_INVENTORY) -> dict[str, Any]:
    inventory = build_inventory()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return inventory


def _query_osv_batch(packages: list[dict[str, str]]) -> dict[str, Any]:
    queries = [
        {
            "version": pkg["version"],
            "package": {"name": pkg["name"], "ecosystem": pkg["ecosystem"]},
        }
        for pkg in packages
        if pkg.get("name") and pkg.get("version") and pkg.get("ecosystem")
    ]
    if not queries:
        return {"results": []}

    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for start in range(0, len(queries), 500):
        chunk = queries[start:start + 500]
        payload = json.dumps({"queries": chunk}).encode("utf-8")
        req = urllib.request.Request(
            OSV_BATCH_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "hermes-stack-cve-check/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=OSV_TIMEOUT) as resp:
                data = json.loads(resp.read())
                results.extend(data.get("results", []))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            errors.append(f"OSV query failed for package batch {start // 500 + 1}: {exc}")
    return {"results": results, "errors": errors}


def _npm_audit(lock: dict[str, Any]) -> dict[str, Any]:
    lock_path = ROOT / lock["path"]
    npm_dir = lock_path.parent
    if not (npm_dir / "package.json").exists():
        return {"path": lock["path"], "skipped": "missing package.json"}
    result = _run(["npm", "audit", "--json"], cwd=npm_dir, timeout=45)
    data: dict[str, Any] = {}
    if result.get("stdout"):
        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            data = {}
    meta = data.get("metadata", {}).get("vulnerabilities", {})
    return {
        "path": lock["path"],
        "ok": result.get("returncode") == 0,
        "summary": {
            "info": meta.get("info", 0),
            "low": meta.get("low", 0),
            "moderate": meta.get("moderate", 0),
            "high": meta.get("high", 0),
            "critical": meta.get("critical", 0),
            "total": meta.get("total", 0),
        },
        "vulnerabilities": data.get("vulnerabilities", {}),
        "error": result.get("error") or (result.get("stderr") or "").strip()[:1000],
    }


def audit_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    python_packages = inventory.get("python", {}).get("installed", [])
    npm_packages = [
        pkg
        for lock in inventory.get("node", {}).get("locks", [])
        for pkg in lock.get("packages", [])
    ]
    npm_packages.extend(inventory.get("runtime", {}).get("npm_globals", {}).get("packages", []))

    osv_packages = [
        {"name": p["name"], "version": p["version"], "ecosystem": p["ecosystem"]}
        for p in [*python_packages, *npm_packages]
        if p.get("name") and p.get("version") and p.get("ecosystem") in {"PyPI", "npm"}
    ]
    osv = _query_osv_batch(osv_packages)
    package_by_index = osv_packages
    osv_findings = []
    for idx, result in enumerate(osv.get("results", [])):
        vulns = result.get("vulns") or []
        if not vulns:
            continue
        package = package_by_index[idx] if idx < len(package_by_index) else {}
        for vuln in vulns:
            osv_findings.append({
                "package": package,
                "id": vuln.get("id"),
                "summary": vuln.get("summary"),
                "aliases": vuln.get("aliases", []),
                "severity": vuln.get("database_specific", {}).get("severity"),
                "modified": vuln.get("modified"),
            })

    npm_audits = [_npm_audit(lock) for lock in inventory.get("node", {}).get("locks", [])]
    npm_totals = {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0, "total": 0}
    for audit in npm_audits:
        for key in npm_totals:
            npm_totals[key] += int(audit.get("summary", {}).get(key, 0) or 0)

    return {
        "schema_version": 1,
        "generated_at": _now(),
        "inventory_generated_at": inventory.get("generated_at"),
        "git": inventory.get("git", {}),
        "runtime": inventory.get("runtime", {}),
        "osv": {
            "package_count": len(osv_packages),
            "finding_count": len(osv_findings),
            "findings": osv_findings,
            "errors": osv.get("errors", []),
        },
        "npm_audit": {
            "totals": npm_totals,
            "audits": npm_audits,
        },
        "recommendations": _recommendations(osv_findings, npm_totals),
    }


def _recommendations(osv_findings: list[dict[str, Any]], npm_totals: dict[str, int]) -> list[str]:
    recs = []
    if npm_totals.get("critical") or npm_totals.get("high"):
        recs.append("Run `npm audit` in affected directories and inspect `npm audit fix --dry-run` before applying lockfile changes.")
    if osv_findings:
        recs.append("For each OSV finding, prefer the smallest compatible dependency bump and run `scripts/run_tests.sh` before merging.")
    if not recs:
        recs.append("No known CVE findings from OSV/npm audit. Keep the weekly scheduled check enabled.")
    recs.append("Keep inventory/report updates in the checked-out repo; for code or lockfile fixes, use a branch and PR unless the operator explicitly approves a direct main push.")
    return recs


def write_report(audit: dict[str, Any], path: Path = DEFAULT_REPORT) -> None:
    lines = [
        "# Hermes Stack CVE Report",
        "",
        f"Generated: `{audit.get('generated_at')}`",
        f"Inventory: `{audit.get('inventory_generated_at')}`",
        "",
        "## Summary",
        "",
        f"- OSV packages checked: {audit['osv']['package_count']}",
        f"- OSV findings: {audit['osv']['finding_count']}",
        f"- npm audit totals: {audit['npm_audit']['totals']}",
        "",
        "## Recommendations",
        "",
    ]
    lines.extend(f"- {item}" for item in audit.get("recommendations", []))

    git = audit.get("git") or {}
    if git:
        lines.extend([
            "",
            "## Repository Durability",
            "",
            f"- Target repo: `{git.get('root')}`",
            f"- Script source: `{git.get('source_root')}`",
            f"- Branch: `{git.get('branch')}`",
            f"- HEAD: `{git.get('head')}`",
            f"- Upstream: `{git.get('upstream')}`",
            f"- Ahead/behind: `{git.get('ahead_behind')}`",
            f"- Dirty after report generation: `{git.get('dirty')}`",
        ])
        status_short = git.get("status_short") or []
        if status_short:
            lines.append("- Changed paths:")
            lines.extend(f"  - `{item}`" for item in status_short[:50])

    runtime = audit.get("runtime") or {}
    if runtime:
        npm_globals = runtime.get("npm_globals") or {}
        system_packages = runtime.get("system_packages") or {}
        k8s_images = runtime.get("kubernetes_images") or {}
        workspace_repos = runtime.get("workspace_repos") or []
        lines.extend([
            "",
            "## Runtime Inventory Layers",
            "",
            f"- npm globals: {len(npm_globals.get('packages') or [])}",
            f"- system packages ({system_packages.get('manager') or 'unknown'}): {len(system_packages.get('packages') or [])}",
            f"- Kubernetes images in `{k8s_images.get('namespace') or 'hermes'}`: {len(k8s_images.get('images') or [])}",
            f"- workspace repos with dependency manifests: {len(workspace_repos)}",
        ])
        images = k8s_images.get("images") or []
        if images:
            lines.append("- Kubernetes images:")
            lines.extend(f"  - `{image}`" for image in images[:50])

    lines.extend(["", "## OSV Findings", ""])
    findings = audit.get("osv", {}).get("findings", [])
    if not findings:
        lines.append("No OSV findings.")
    else:
        for finding in findings:
            pkg = finding.get("package", {})
            aliases = ", ".join(finding.get("aliases") or [])
            alias_part = f" {aliases}" if aliases else ""
            summary = finding.get("summary") or ""
            suffix = f" - {summary}" if summary else ""
            lines.append(
                f"- `{pkg.get('ecosystem')}/{pkg.get('name')}@{pkg.get('version')}`: "
                f"{finding.get('id')}{alias_part}{suffix}"
            )

    lines.extend(["", "## npm Audit", ""])
    for audit_item in audit.get("npm_audit", {}).get("audits", []):
        lines.append(f"- `{audit_item.get('path')}`: {audit_item.get('summary')}")

    errors = audit.get("osv", {}).get("errors", [])
    if errors:
        lines.extend(["", "## Check Errors", ""])
        lines.extend(f"- {err}" for err in errors)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def install_cron_job(schedule: str = "0 9 * * 1") -> dict[str, Any]:
    from cron.jobs import create_job, load_jobs, update_job

    name = "Hermes stack CVE checkup"
    prompt = (
        "Run the stack-cve-checkup skill against the checked-out Hermes repo, "
        "not only internal HERMES_HOME state. Prefer HERMES_STACK_REPO when set; "
        "otherwise use the repo checkout under HERMES_HOME such as "
        "/opt/data/hermes-agent. Update docs/stack-inventory.json, "
        "docs/stack-cve-report.md, and docs/stack-cve-report.json in that repo. "
        "Record meaningful Hermes-made file changes in HERMES_CHANGELOG.md. "
        "For code or lockfile remediations, create/update a branch and PR; do "
        "not push main, merge, deploy, or apply dependency updates unless the "
        "operator explicitly approves them. Propose only non-breaking fixes."
    )
    for job in load_jobs():
        if job.get("name") == name:
            updated = update_job(job["id"], {
                "prompt": prompt,
                "skills": ["stack-cve-checkup"],
                "skill": "stack-cve-checkup",
                "schedule": schedule,
            })
            return {"created": False, "updated": True, "job": updated or job}

    job = create_job(prompt=prompt, schedule=schedule, name=name, skills=["stack-cve-checkup"])
    return {"created": True, "updated": False, "job": job}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", action="store_true", help="write docs/stack-inventory.json")
    parser.add_argument("--audit", action="store_true", help="run CVE/audit checks and write report")
    parser.add_argument("--install-cron", action="store_true", help="install weekly Hermes cron job")
    parser.add_argument("--schedule", default="0 9 * * 1", help="cron schedule for --install-cron")
    parser.add_argument("--json", action="store_true", help="print machine-readable result")
    args = parser.parse_args(argv)

    if not (args.inventory or args.audit or args.install_cron):
        args.inventory = True
        args.audit = True

    result: dict[str, Any] = {}
    inventory = None
    if args.inventory or args.audit:
        inventory = write_inventory()
        result["inventory_path"] = str(DEFAULT_INVENTORY)
        result["inventory_items"] = {
            "python_installed": len(inventory.get("python", {}).get("installed", [])),
            "npm_locks": len(inventory.get("node", {}).get("locks", [])),
            "npm_globals": len(inventory.get("runtime", {}).get("npm_globals", {}).get("packages", [])),
            "system_packages": len(inventory.get("runtime", {}).get("system_packages", {}).get("packages", [])),
            "kubernetes_images": len(inventory.get("runtime", {}).get("kubernetes_images", {}).get("images", [])),
            "workspace_repos": len(inventory.get("runtime", {}).get("workspace_repos", [])),
            "skills": inventory.get("skills", {}).get("count", 0),
            "core_tools": len(inventory.get("tools", {}).get("core_tools", [])),
        }

    if args.audit:
        assert inventory is not None
        audit = audit_inventory(inventory)
        audit_json = DEFAULT_REPORT.with_suffix(".json")
        audit_json.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_report(audit)
        result["report_path"] = str(DEFAULT_REPORT)
        result["report_json_path"] = str(audit_json)
        result["osv_findings"] = audit["osv"]["finding_count"]
        result["npm_audit_totals"] = audit["npm_audit"]["totals"]
        result["recommendations"] = audit["recommendations"]

    if args.install_cron:
        result["cron"] = install_cron_job(args.schedule)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
