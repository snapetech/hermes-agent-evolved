#!/usr/bin/env python3
"""Compare declared runtime package manifests with the current environment."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

APT_PACKAGE_ALIASES = {
    # Ubuntu 24.04 installs the tools through this concrete package while the
    # compatibility package name remains the clearer manifest intent.
    "dnsutils": "bind9-dnsutils",
}


def manifest_names(path: Path) -> set[str]:
    names = set()
    if not path.exists():
        return names
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("@") and "@" in line[1:]:
            name = line.rsplit("@", 1)[0].strip()
        elif "@" in line and "://" not in line:
            name = line.split("@", 1)[0].strip()
        else:
            name = re.split(r"[<>=!~\\[]", line, maxsplit=1)[0].strip()
        if name:
            names.add(name)
    return names


def run(cmd: list[str], timeout: int = 25) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}
    except Exception as exc:
        return {"ok": False, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}


def installed_apt() -> set[str]:
    result = run(["dpkg-query", "-W", "-f=${Package}\n"])
    packages = set(result["stdout"].splitlines()) if result["ok"] else set()
    for alias, concrete in APT_PACKAGE_ALIASES.items():
        if concrete in packages:
            packages.add(alias)
    return packages


def resolve_pip_python(explicit: str | None = None) -> str:
    candidates = [
        explicit,
        os.environ.get("PIP_PYTHON"),
        str(Path(os.environ["VIRTUAL_ENV"]) / "bin/python") if os.environ.get("VIRTUAL_ENV") else None,
        "/opt/data/workspace/.venv/bin/python",
        sys.executable,
        "python",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_absolute() and not path.exists():
            continue
        return candidate
    return "python"


def installed_pip(python_executable: str | None = None) -> set[str]:
    result = run([resolve_pip_python(python_executable), "-m", "pip", "list", "--format=json"])
    if not result["ok"]:
        return set()
    try:
        return {item["name"] for item in json.loads(result["stdout"])}
    except Exception:
        return set()


def installed_npm() -> set[str]:
    result = run(["npm", "list", "-g", "--depth=0", "--json"])
    if not result["stdout"]:
        return set()
    try:
        deps = json.loads(result["stdout"]).get("dependencies") or {}
        return set(deps)
    except Exception:
        return set()


def drift(pip_python: str | None = None, root: Path = ROOT) -> dict[str, Any]:
    manifests = {
        "apt": root / "deploy/k8s/apt-packages.txt",
        "pip": root / "deploy/k8s/requirements-persistent.txt",
        "npm": root / "deploy/k8s/npm-global-packages.txt",
    }
    installed = {"apt": installed_apt(), "pip": installed_pip(pip_python), "npm": installed_npm()}
    result = {}
    for ecosystem, path in manifests.items():
        declared = manifest_names(path)
        actual = installed[ecosystem]
        result[ecosystem] = {
            "declared_count": len(declared),
            "installed_count": len(actual),
            "missing_declared": sorted(declared - actual),
            "extra_installed": sorted(actual - declared),
        }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--pip-python",
        help="Python executable whose pip environment should be compared. Defaults to PIP_PYTHON, VIRTUAL_ENV, "
        "/opt/data/workspace/.venv/bin/python, then the current interpreter.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root containing deploy/k8s package manifests.",
    )
    args = parser.parse_args(argv)

    payload = drift(pip_python=args.pip_python, root=args.root)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for ecosystem, item in payload.items():
            print(f"{ecosystem}: declared={item['declared_count']} installed={item['installed_count']}")
            if item["missing_declared"]:
                print("  missing declared: " + ", ".join(item["missing_declared"][:40]))
            if item["extra_installed"]:
                print("  extra installed: " + ", ".join(item["extra_installed"][:40]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
