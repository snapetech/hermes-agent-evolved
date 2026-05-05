"""Capture and promote ephemeral runtime package installs."""

from __future__ import annotations

import json
import os
import re
import shlex
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home
from tools.approval import extract_runtime_apt_install_packages

_INSTALLS_DIR = "runtime-installs"
_LEDGERS = {
    "apt": "apt.jsonl",
    "pip": "pip.jsonl",
    "npm": "npm.jsonl",
}
_DEFAULT_PACKAGE_FILES = {
    "apt": Path("deploy/k8s/apt-packages.txt"),
    "pip": Path("deploy/k8s/requirements-persistent.txt"),
    "npm": Path("deploy/k8s/npm-global-packages.txt"),
}
_ECOSYSTEMS = tuple(_LEDGERS)
_FALSE_VALUES = {"0", "false", "no", "off"}
_PIP_VALUE_FLAGS = {
    "-c",
    "--constraint",
    "-r",
    "--requirement",
    "-i",
    "--index-url",
    "--extra-index-url",
    "--find-links",
    "-f",
    "--trusted-host",
    "--platform",
    "--python-version",
    "--implementation",
    "--abi",
    "--root",
    "--prefix",
    "--target",
    "-t",
}
_NPM_VALUE_FLAGS = {
    "--prefix",
    "--cache",
    "--registry",
    "--tag",
    "--userconfig",
    "--workspace",
    "-w",
}
_SHELL_CONTROL_TOKENS = {"|", "||", "&&", ";", "&"}
_REDIRECTION_RE = re.compile(r"^(?:\d*)[<>]|^\d*>&\d+$")


def _normalize_ecosystem(ecosystem: str) -> str:
    normalized = (ecosystem or "").strip().lower()
    if normalized not in _ECOSYSTEMS:
        raise ValueError(f"Unsupported runtime install ecosystem: {ecosystem}")
    return normalized


def _ledger_path(ecosystem: str) -> Path:
    return get_hermes_home() / _INSTALLS_DIR / _LEDGERS[_normalize_ecosystem(ecosystem)]


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _git_commit() -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=2,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return ""


def _split_shell_segments(command: str) -> list[str]:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return []
    if len(tokens) >= 3 and tokens[0] in {"bash", "sh"} and tokens[1].startswith("-") and "c" in tokens[1]:
        if len(tokens) != 3:
            return []
        return _split_shell_segments(tokens[2])
    return [part.strip() for part in command.split("&&") if part.strip()]


def _split_shell_command(command: str) -> list[list[str]]:
    try:
        return [shlex.split(part, posix=True) for part in _split_shell_segments(command)]
    except ValueError:
        return []


def _strip_sudo_and_env(tokens: list[str]) -> list[str]:
    idx = 0
    if tokens[:2] == ["sudo", "-n"]:
        idx = 2
    elif tokens[:1] == ["sudo"]:
        idx = 1
    while idx < len(tokens) and "=" in tokens[idx] and not tokens[idx].startswith("-"):
        name, _value = tokens[idx].split("=", 1)
        if name.replace("_", "").isalnum():
            idx += 1
            continue
        break
    return tokens[idx:]


def _looks_like_package_spec(token: str) -> bool:
    if not token or token.startswith("-"):
        return False
    if token in {".", ".."} or token.startswith(("./", "../", "/")):
        return False
    return True


def _is_shell_boundary(token: str) -> bool:
    return token in _SHELL_CONTROL_TOKENS or bool(_REDIRECTION_RE.match(token))


def _extract_pip_packages(tokens: list[str]) -> list[str]:
    tokens = _strip_sudo_and_env(tokens)
    if not tokens:
        return []
    if len(tokens) >= 4 and tokens[1:3] == ["-m", "pip"]:
        start = 3
    elif Path(tokens[0]).name in {"pip", "pip3"}:
        start = 1
    else:
        return []
    if len(tokens) <= start or tokens[start] != "install":
        return []

    packages: list[str] = []
    idx = start + 1
    while idx < len(tokens):
        token = tokens[idx]
        if _is_shell_boundary(token):
            break
        if token in _PIP_VALUE_FLAGS:
            # Requirements files can be large and environment-specific; leave
            # them as explicit repo files rather than flattening by command.
            if token in {"-r", "--requirement"}:
                return []
            idx += 2
            continue
        if any(token.startswith(flag + "=") for flag in _PIP_VALUE_FLAGS):
            if token.startswith(("-r=", "--requirement=")):
                return []
            idx += 1
            continue
        if token.startswith("-"):
            idx += 1
            continue
        if _looks_like_package_spec(token):
            packages.append(token)
        idx += 1
    return packages


def _extract_npm_packages(tokens: list[str]) -> list[str]:
    tokens = _strip_sudo_and_env(tokens)
    if len(tokens) < 3 or Path(tokens[0]).name != "npm" or tokens[1] not in {"install", "i", "add"}:
        return []

    global_install = False
    packages: list[str] = []
    idx = 2
    while idx < len(tokens):
        token = tokens[idx]
        if _is_shell_boundary(token):
            break
        if token in {"-g", "--global"}:
            global_install = True
            idx += 1
            continue
        if token in _NPM_VALUE_FLAGS:
            idx += 2
            continue
        if any(token.startswith(flag + "=") for flag in _NPM_VALUE_FLAGS):
            idx += 1
            continue
        if token.startswith("-"):
            idx += 1
            continue
        if _looks_like_package_spec(token):
            packages.append(token)
        idx += 1
    return packages if global_install else []


def extract_runtime_install_packages(command: str) -> dict[str, list[str]]:
    """Extract declarative package specs from supported runtime install commands."""
    installs: dict[str, list[str]] = {
        "apt": [],
        "pip": [],
        "npm": [],
    }
    for segment in _split_shell_segments(command):
        for package in extract_runtime_apt_install_packages(segment):
            if package not in installs["apt"]:
                installs["apt"].append(package)
    for tokens in _split_shell_command(command):
        for ecosystem, packages in (
            ("pip", _extract_pip_packages(tokens)),
            ("npm", _extract_npm_packages(tokens)),
        ):
            seen = set(installs[ecosystem])
            for package in packages:
                if package not in seen:
                    installs[ecosystem].append(package)
                    seen.add(package)
    return {ecosystem: packages for ecosystem, packages in installs.items() if packages}


def record_runtime_install(
    *,
    ecosystem: str,
    command: str,
    packages: list[str],
    exit_code: int,
    output: str = "",
    task_id: str | None = None,
) -> None:
    """Record a successful runtime install for later promotion."""
    ecosystem = _normalize_ecosystem(ecosystem)
    if exit_code != 0 or not packages:
        return
    if os.getenv("HERMES_RECORD_RUNTIME_INSTALLS", "1").strip().lower() in _FALSE_VALUES:
        return
    if ecosystem == "apt" and os.getenv("HERMES_RECORD_RUNTIME_APT", "1").strip().lower() in _FALSE_VALUES:
        return
    record = {
        "command": command,
        "cwd": os.getcwd(),
        "ecosystem": ecosystem,
        "exit_code": exit_code,
        "git_commit": _git_commit(),
        "host": socket.gethostname(),
        "packages": sorted(dict.fromkeys(packages)),
        "task_id": task_id or "",
        "ts": time.time(),
    }
    if output:
        record["output_preview"] = output[:1000]
    try:
        _append_jsonl(_ledger_path(ecosystem), record)
    except Exception:
        # Runtime install capture must never make a successful terminal call fail.
        pass


def record_runtime_installs(
    *,
    command: str,
    exit_code: int,
    output: str = "",
    task_id: str | None = None,
) -> None:
    for ecosystem, packages in extract_runtime_install_packages(command).items():
        record_runtime_install(
            ecosystem=ecosystem,
            command=command,
            packages=packages,
            exit_code=exit_code,
            output=output,
            task_id=task_id,
        )


def record_runtime_apt_install(
    *,
    command: str,
    packages: list[str],
    exit_code: int,
    output: str = "",
    task_id: str | None = None,
) -> None:
    """Compatibility wrapper for callers/tests that record apt directly."""
    record_runtime_install(
        ecosystem="apt",
        command=command,
        packages=packages,
        exit_code=exit_code,
        output=output,
        task_id=task_id,
    )


def read_runtime_installs(ecosystem: str, limit: int = 50) -> list[dict[str, Any]]:
    path = _ledger_path(ecosystem)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[-max(1, limit):]:
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def read_runtime_apt_installs(limit: int = 50) -> list[dict[str, Any]]:
    return read_runtime_installs("apt", limit=limit)


def _looks_like_package_repo(root: Path, ecosystem: str) -> bool:
    return (root / _DEFAULT_PACKAGE_FILES[_normalize_ecosystem(ecosystem)]).exists()


def _git_root_from_cwd() -> Path | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    root = Path(proc.stdout.strip())
    return root if root.exists() else None


def _default_repo_root(ecosystem: str) -> Path:
    """Find the durable repo checkout that owns deploy/k8s package lists.

    Cluster gateway sessions often run from ``/opt/hermes``, which is an image
    copy and not a git checkout. Promotion should target the persistent checkout
    when it is available so a later commit/PR can make the package durable.
    """
    env_root = os.getenv("HERMES_RUNTIME_PACKAGE_REPO_ROOT", "").strip()
    candidates: list[Path] = []
    if env_root:
        candidates.append(Path(env_root))
    git_root = _git_root_from_cwd()
    if git_root:
        candidates.append(git_root)
    hermes_home = get_hermes_home()
    candidates.extend(
        [
            hermes_home / "hermes-agent",
            Path("/opt/data/hermes-agent"),
            Path(os.getcwd()),
        ]
    )

    seen: set[Path] = set()
    for candidate in candidates:
        root = candidate.expanduser().resolve()
        if root in seen:
            continue
        seen.add(root)
        if _looks_like_package_repo(root, ecosystem):
            return root
    return Path(os.getcwd()).resolve()


def _repo_package_path(ecosystem: str, repo_root: str | os.PathLike[str] | None = None) -> Path:
    ecosystem = _normalize_ecosystem(ecosystem)
    root = Path(repo_root).expanduser().resolve() if repo_root else _default_repo_root(ecosystem)
    return root / _DEFAULT_PACKAGE_FILES[ecosystem]


def read_promoted_packages(ecosystem: str, repo_root: str | os.PathLike[str] | None = None) -> list[str]:
    path = _repo_package_path(ecosystem, repo_root)
    if not path.exists():
        return []
    packages: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        packages.append(stripped)
    return packages


def read_image_apt_packages(repo_root: str | os.PathLike[str] | None = None) -> list[str]:
    return read_promoted_packages("apt", repo_root)


def _package_file_header(ecosystem: str) -> list[str]:
    if ecosystem == "apt":
        return [
            "# Debian packages baked into deploy/k8s/Dockerfile.sudo.",
            "# Runtime apt installs that prove useful can be promoted here.",
            "",
        ]
    if ecosystem == "pip":
        return [
            "# Python packages installed into the persistent workspace venv.",
            "# Runtime pip installs that prove useful can be promoted here.",
            "",
        ]
    return [
        "# Global npm packages installed under the persistent Hermes home.",
        "# Runtime npm -g installs that prove useful can be promoted here.",
        "",
    ]


def _write_promoted_packages(
    ecosystem: str,
    packages: list[str],
    repo_root: str | os.PathLike[str] | None = None,
) -> Path:
    ecosystem = _normalize_ecosystem(ecosystem)
    path = _repo_package_path(ecosystem, repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = _package_file_header(ecosystem)
    body.extend(sorted(dict.fromkeys(packages)))
    path.write_text("\n".join(body).rstrip() + "\n", encoding="utf-8")
    return path


def promote_runtime_packages(
    ecosystem: str,
    packages: list[str] | None = None,
    *,
    repo_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Promote captured runtime packages into the matching deploy package file."""
    ecosystem = _normalize_ecosystem(ecosystem)
    captured: list[str] = []
    for record in read_runtime_installs(ecosystem, limit=1000):
        command = record.get("command")
        reparsed = extract_runtime_install_packages(command).get(ecosystem, []) if isinstance(command, str) else []
        record_packages = reparsed or record.get("packages") or []
        for package in record_packages:
            if isinstance(package, str):
                captured.append(package)
    requested = packages or captured
    existing = read_promoted_packages(ecosystem, repo_root)
    existing_set = set(existing)
    added = [pkg for pkg in sorted(dict.fromkeys(requested)) if pkg not in existing_set]
    if added:
        path = _write_promoted_packages(ecosystem, existing + added, repo_root)
    else:
        path = _repo_package_path(ecosystem, repo_root)
    return {
        "added": added,
        "captured": sorted(dict.fromkeys(captured)),
        "ecosystem": ecosystem,
        "package_file": str(path),
        "total": len(read_promoted_packages(ecosystem, repo_root)),
    }


def promote_runtime_apt_packages(
    packages: list[str] | None = None,
    *,
    repo_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper for apt-only promotion."""
    return promote_runtime_packages("apt", packages, repo_root=repo_root)
