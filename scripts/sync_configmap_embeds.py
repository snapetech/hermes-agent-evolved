#!/usr/bin/env python3
"""Keep deploy/k8s/configmap.yaml inlined blocks in sync with their source files.

The configmap embeds the scout, self-edit helper, and intel source registry as
indented block scalars. Edit the standalone files under deploy/k8s/ and then run
this helper to refresh the configmap so they stay byte-for-byte identical.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONFIGMAP = ROOT / "deploy/k8s/configmap.yaml"

EMBEDS: list[tuple[str, Path]] = [
    ("bootstrap-runtime.sh", ROOT / "deploy/k8s/bootstrap-runtime.sh"),
    ("hermes-self-improvement-scan.py", ROOT / "deploy/k8s/hermes-self-improvement-scan.py"),
    ("hermes-introspection-scan.py", ROOT / "deploy/k8s/hermes-introspection-scan.py"),
    ("hermes-resource-review.py", ROOT / "deploy/k8s/hermes-resource-review.py"),
    ("hermes-self-edit.py", ROOT / "deploy/k8s/hermes-self-edit.py"),
    ("hermes-repo-sync.py", ROOT / "deploy/k8s/hermes-repo-sync.py"),
    ("hermes-edge-watch-query.py", ROOT / "deploy/k8s/hermes-edge-watch-query.py"),
    ("edge-watch-mcp.py", ROOT / "deploy/k8s/edge-watch-mcp.py"),
    ("desktop-bridge-mcp.py", ROOT / "deploy/k8s/desktop-bridge-mcp.py"),
    ("discord-wayland-monitor.py", ROOT / "deploy/k8s/discord-wayland-monitor.py"),
    ("hermes-intel-sources.yaml", ROOT / "deploy/k8s/hermes-intel-sources.yaml"),
    ("workspace-AGENTS.md", ROOT / "deploy/k8s/workspace-AGENTS.md"),
    ("workspace-GITHUB.md", ROOT / "deploy/k8s/GITHUB.md"),
    ("local-models.manifest.yaml", ROOT / "deploy/k8s/local-models.manifest.yaml"),
]

INDENT = "    "
BLOCK_START_RE = re.compile(r"^  [a-zA-Z_][a-zA-Z0-9._-]*: [|>][-+]?\s*$", re.MULTILINE)


def indent_block(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        out.append(f"{INDENT}{line}" if line else "")
    return "\n".join(out)


def replace_block(source: str, key: str, new_body: str) -> str:
    needle = f"\n  {key}: |\n"
    start = source.find(needle)
    if start == -1:
        raise SystemExit(f"key not found in configmap: {key}")
    body_start = start + len(needle)
    remainder = source[body_start:]
    end_in_remainder = None
    for match in BLOCK_START_RE.finditer(remainder):
        end_in_remainder = match.start()
        break
    if end_in_remainder is None:
        end_in_remainder = len(remainder)
    trailing = remainder[end_in_remainder:]
    indented = indent_block(new_body.rstrip("\n")) + "\n"
    return source[:body_start] + indented + trailing


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    text = CONFIGMAP.read_text(encoding="utf-8")
    original = text
    for key, path in EMBEDS:
        if not path.exists():
            print(f"skip missing source: {path}", file=sys.stderr)
            continue
        new_body = path.read_text(encoding="utf-8")
        text = replace_block(text, key, new_body)
    if text == original:
        print("configmap already in sync")
        return 0
    if check_only:
        print("configmap is OUT OF SYNC with embedded sources", file=sys.stderr)
        return 1
    CONFIGMAP.write_text(text, encoding="utf-8")
    print(f"wrote {CONFIGMAP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
