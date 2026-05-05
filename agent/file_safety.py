"""Shared file safety rules used by both tools and ACP shims."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _hermes_home_path() -> Path:
    """Resolve the active HERMES_HOME (profile-aware) without circular imports."""
    try:
        from hermes_constants import get_hermes_home  # local import to avoid cycles
        return get_hermes_home()
    except Exception:
        return Path(os.path.expanduser("~/.hermes"))


def build_write_denied_paths(home: str) -> set[str]:
    """Return exact sensitive paths that must never be written."""
    hermes_home = _hermes_home_path()
    return {
        os.path.realpath(p)
        for p in [
            os.path.join(home, ".ssh", "authorized_keys"),
            os.path.join(home, ".ssh", "id_rsa"),
            os.path.join(home, ".ssh", "id_ed25519"),
            os.path.join(home, ".ssh", "config"),
            str(hermes_home / ".env"),
            os.path.join(home, ".hermes", ".env"),
            os.path.join(home, ".bashrc"),
            os.path.join(home, ".zshrc"),
            os.path.join(home, ".profile"),
            os.path.join(home, ".bash_profile"),
            os.path.join(home, ".zprofile"),
            os.path.join(home, ".netrc"),
            os.path.join(home, ".pgpass"),
            os.path.join(home, ".npmrc"),
            os.path.join(home, ".pypirc"),
            "/etc/sudoers",
            "/etc/passwd",
            "/etc/shadow",
        ]
    }


def build_write_denied_prefixes(home: str) -> list[str]:
    """Return sensitive directory prefixes that must never be written."""
    return [
        os.path.realpath(p) + os.sep
        for p in [
            os.path.join(home, ".ssh"),
            os.path.join(home, ".aws"),
            os.path.join(home, ".gnupg"),
            os.path.join(home, ".kube"),
            "/etc/sudoers.d",
            "/etc/systemd",
            os.path.join(home, ".docker"),
            os.path.join(home, ".azure"),
            os.path.join(home, ".config", "gh"),
        ]
    ]


def get_safe_write_root() -> Optional[str]:
    """Return the resolved HERMES_WRITE_SAFE_ROOT path, or None if unset."""
    root = os.getenv("HERMES_WRITE_SAFE_ROOT", "")
    if not root:
        return None
    try:
        return os.path.realpath(os.path.expanduser(root))
    except Exception:
        return None


def _get_repo_sync_target() -> Optional[str]:
    """Return the canonical writable repo target, if configured and present."""
    raw = os.getenv("HERMES_REPO_SYNC_TARGET", "").strip()
    if not raw:
        raw = "/opt/data/workspace/hermes-agent-private"
    try:
        target = os.path.realpath(os.path.expanduser(raw))
    except Exception:
        return None
    if not os.path.isdir(target):
        return None
    return target


def _get_read_only_repo_sources() -> list[tuple[str, str]]:
    """Return configured read-only repo sources as (raw, resolved) tuples."""
    raw_value = os.getenv("HERMES_REPO_SYNC_READ_ONLY_SOURCES", "").strip()
    if not raw_value:
        raw_value = "/opt/data/hermes-agent"
    sources: list[tuple[str, str]] = []
    for part in raw_value.split(","):
        raw = part.strip()
        if not raw:
            continue
        try:
            resolved = os.path.realpath(os.path.expanduser(raw))
        except Exception:
            continue
        sources.append((os.path.normpath(os.path.expanduser(raw)), resolved))
    return sources


def get_write_block_error(path: str) -> Optional[str]:
    """Return a specific denial reason when a write targets a protected path."""
    home = os.path.realpath(os.path.expanduser("~"))
    resolved = os.path.realpath(os.path.expanduser(str(path)))
    normalized = os.path.normpath(os.path.expanduser(str(path)))

    if resolved in build_write_denied_paths(home):
        return f"Write denied: '{path}' is a protected system/credential file."
    for prefix in build_write_denied_prefixes(home):
        if resolved.startswith(prefix):
            return f"Write denied: '{path}' is a protected system/credential file."

    safe_root = get_safe_write_root()
    if safe_root and not (resolved == safe_root or resolved.startswith(safe_root + os.sep)):
        return f"Write denied: '{path}' is outside the configured safe workspace root."

    canonical_repo = _get_repo_sync_target()
    if canonical_repo:
        for raw_source, resolved_source in _get_read_only_repo_sources():
            raw_prefix = raw_source + os.sep
            resolved_prefix = resolved_source + os.sep
            in_raw_source = normalized == raw_source or normalized.startswith(raw_prefix)
            in_resolved_source = resolved == resolved_source or resolved.startswith(resolved_prefix)
            if in_raw_source or in_resolved_source:
                if resolved == canonical_repo or resolved.startswith(canonical_repo + os.sep):
                    continue
                return (
                    f"Write denied: '{path}' is a read-only/internal Hermes repo path. "
                    f"Make durable edits in the canonical checkout at '{canonical_repo}' instead."
                )

    return None


def is_write_denied(path: str) -> bool:
    """Return True if path is blocked by the write denylist or safe root."""
    return get_write_block_error(path) is not None


def get_read_block_error(path: str) -> Optional[str]:
    """Return an error message when a read targets internal Hermes cache files."""
    resolved = Path(path).expanduser().resolve()
    hermes_home = _hermes_home_path().resolve()
    blocked_dirs = [
        hermes_home / "skills" / ".hub" / "index-cache",
        hermes_home / "skills" / ".hub",
    ]
    for blocked in blocked_dirs:
        try:
            resolved.relative_to(blocked)
        except ValueError:
            continue
        return (
            f"Access denied: {path} is an internal Hermes cache file "
            "and cannot be read directly to prevent prompt injection. "
            "Use the skills_list or skill_view tools instead."
        )
    return None
