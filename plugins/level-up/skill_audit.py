"""Stale-skill and dead-reference audit."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from hermes_constants import get_hermes_home


_URL_RE = re.compile(r"https?://[^\s)>'\"]+")
_PATH_RE = re.compile(
    r"(?<![\w:/.-])(?:~|\$HERMES_HOME|\./|\.\./)[A-Za-z0-9_./${}~@:+-]+"
    r"|(?<![\w:/.-])/(?:[A-Za-z0-9_.@:+-]+/)[A-Za-z0-9_./@:+-]*"
)


def _candidate_files() -> list[Path]:
    home = get_hermes_home()
    files = [home / "memories" / "MEMORY.md", home / "SOUL.md"]
    for root in (home / "skills", Path.cwd() / "skills", Path.cwd() / "plugins"):
        if root.exists():
            files.extend(root.rglob("SKILL.md"))
    return sorted({p.resolve() for p in files if p.exists()})


def _expand_path(raw: str, source: Path) -> Path:
    value = raw.replace("$HERMES_HOME", str(get_hermes_home()))
    value = os.path.expandvars(os.path.expanduser(value))
    path = Path(value)
    if not path.is_absolute():
        path = (source.parent / path).resolve()
    return path


def _url_ok(url: str) -> tuple[bool, str]:
    req = Request(url, method="HEAD", headers={"User-Agent": "hermes-skill-audit"})
    try:
        with urlopen(req, timeout=5) as resp:
            return 200 <= resp.status < 400, f"HTTP {resp.status}"
    except HTTPError as exc:
        if exc.code == 405:
            try:
                req = Request(url, method="GET", headers={"User-Agent": "hermes-skill-audit"})
                with urlopen(req, timeout=5) as resp:
                    return 200 <= resp.status < 400, f"HTTP {resp.status}"
            except Exception as inner:
                return False, str(inner)
        return False, f"HTTP {exc.code}"
    except (URLError, TimeoutError) as exc:
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)


def _iter_refs(path: Path) -> Iterable[tuple[str, str]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    for match in _PATH_RE.finditer(text):
        raw = match.group(0).rstrip(".,;:")
        if raw.startswith("//"):
            continue
        yield "path", raw
    for match in _URL_RE.finditer(text):
        yield "url", match.group(0).rstrip(".,;:")


def skill_audit_command(raw_args: str = "") -> str:
    """`/skill-audit [--urls]` -- report stale file and URL references."""
    check_urls = "--urls" in (raw_args or "").split()
    missing_paths: list[str] = []
    bad_urls: list[str] = []
    scanned = 0

    for file_path in _candidate_files():
        scanned += 1
        for kind, raw in _iter_refs(file_path):
            if kind == "path":
                expanded = _expand_path(raw, file_path)
                if not expanded.exists():
                    missing_paths.append(f"{file_path}: `{raw}`")
            elif check_urls:
                ok, detail = _url_ok(raw)
                if not ok:
                    bad_urls.append(f"{file_path}: `{raw}` ({detail})")

    if not missing_paths and not bad_urls:
        suffix = " and URLs" if check_urls else ""
        return f"Skill audit clean: scanned {scanned} files{suffix}."

    lines = [f"Skill audit found stale references in {scanned} files:"]
    if missing_paths:
        lines.append("Missing local paths:")
        lines.extend(f"- {item}" for item in missing_paths[:50])
        if len(missing_paths) > 50:
            lines.append(f"- ... {len(missing_paths) - 50} more")
    if bad_urls:
        lines.append("Broken URLs:")
        lines.extend(f"- {item}" for item in bad_urls[:30])
        if len(bad_urls) > 30:
            lines.append(f"- ... {len(bad_urls) - 30} more")
    return "\n".join(lines)
