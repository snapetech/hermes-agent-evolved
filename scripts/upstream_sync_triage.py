#!/usr/bin/env python3
"""Generate a selective upstream-sync triage report.

This is intentionally policy-aware: it does not recommend a blind merge.
Instead it computes overlap between the private fork and upstream, highlights
design-sensitive files, and embeds the local merge policy directly in the
report so the workflow is reproducible.

The policy frame is: assume a fresh start from current upstream, then ask
whether each local method is still what we would choose today to reach the
Snapetech deployment target.
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "docs" / "keep-local-manifest.yaml"

# Built-in defaults used when the manifest is missing. The manifest is the
# source of truth when present — see docs/keep-local-manifest.yaml.
_DEFAULT_DESIGN_SENSITIVE = (
    "run_agent.py",
    "model_tools.py",
    "toolsets.py",
    "cli.py",
    "gateway/run.py",
    "gateway/status.py",
    "hermes_cli/gateway.py",
    "hermes_cli/config.py",
    "hermes_cli/commands.py",
    "agent/prompt_builder.py",
    "tools/skills_sync.py",
    "deploy/k8s/*",
    "skills/*",
)

_DEFAULT_KEEP_LOCAL = (
    "gateway/run.py",
    "gateway/status.py",
    "hermes_cli/gateway.py",
    "agent/prompt_builder.py",
    "tools/skills_sync.py",
    "deploy/k8s/*",
)


def _load_manifest_patterns() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Read design_sensitive and keep_local patterns from the manifest.

    Falls back to built-in defaults when the manifest is missing, unreadable,
    or lacks the expected keys. Never raises — sync triage must always run.

    The manifest loader is intentionally tolerant: it accepts either PyYAML
    (preferred) or a small hand-rolled parser sufficient for the manifest's
    flat list-of-scalars-and-list-of-maps shape. This avoids making the sync
    tooling depend on PyYAML being installed in the CI runner.
    """
    if not MANIFEST_PATH.exists():
        return _DEFAULT_DESIGN_SENSITIVE, _DEFAULT_KEEP_LOCAL

    try:
        text = MANIFEST_PATH.read_text()
    except OSError:
        return _DEFAULT_DESIGN_SENSITIVE, _DEFAULT_KEEP_LOCAL

    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(text) or {}
    except Exception:
        data = _minimal_yaml_parse(text)

    design = tuple(_extract_patterns(data.get("design_sensitive", [])))
    keep = tuple(_extract_patterns(data.get("keep_local", [])))

    return (
        design or _DEFAULT_DESIGN_SENSITIVE,
        keep or _DEFAULT_KEEP_LOCAL,
    )


def _extract_patterns(entries: object) -> list[str]:
    """Accept either a list of strings or a list of {path, reason} dicts."""
    out: list[str] = []
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if isinstance(entry, str):
            out.append(entry.strip('"'))
        elif isinstance(entry, dict):
            path = entry.get("path")
            if isinstance(path, str):
                out.append(path.strip('"'))
    return out


def _minimal_yaml_parse(text: str) -> dict:
    """Parse just the two sections we need when PyYAML is not installed.

    Supports:
      section:
        - pattern
        - "pattern/with/glob/*"
        - path: some/path
          reason: ...
    """
    sections: dict[str, list] = {}
    current_section: str | None = None
    current_dict: dict | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        # Top-level section headers.
        if indent == 0 and stripped.endswith(":") and ":" in stripped:
            current_section = stripped[:-1]
            sections.setdefault(current_section, [])
            current_dict = None
            continue
        if current_section is None:
            continue
        if stripped.startswith("- "):
            rest = stripped[2:].strip()
            if rest.startswith("path:"):
                # Begin a new dict entry in this section.
                value = rest.split("path:", 1)[1].strip().strip('"')
                current_dict = {"path": value}
                sections[current_section].append(current_dict)
            else:
                # Simple scalar list entry.
                sections[current_section].append(rest.strip('"'))
                current_dict = None
        elif current_dict is not None and ":" in stripped:
            key, _, value = stripped.partition(":")
            current_dict[key.strip()] = value.strip().strip('"')
    return sections


DESIGN_SENSITIVE_PATTERNS, KEEP_LOCAL_METHOD_PATTERNS = _load_manifest_patterns()


def git(args: list[str], *, cwd: Path = ROOT) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def match_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


@dataclass(frozen=True)
class TriageData:
    private_ref: str
    upstream_ref: str
    private_sha: str
    upstream_sha: str
    merge_base: str
    private_only_count: int
    upstream_only_count: int
    private_only_commits: list[str]
    upstream_only_commits: list[str]
    upstream_diff_stat: list[str]
    overlap_files: list[str]
    design_sensitive_overlap: list[str]
    keep_local_overlap: list[str]


def collect_triage(private_ref: str, upstream_ref: str) -> TriageData:
    private_sha = git(["rev-parse", private_ref])
    upstream_sha = git(["rev-parse", upstream_ref])
    merge_base = git(["merge-base", private_ref, upstream_ref])

    left_right = git(["rev-list", "--left-right", "--count", f"{private_ref}...{upstream_ref}"])
    private_only_count, upstream_only_count = (int(part) for part in left_right.split())

    private_only_commits = lines(
        git(["log", "--oneline", f"{upstream_ref}..{private_ref}"])
    )
    upstream_only_commits = lines(
        git(["log", "--oneline", f"{private_ref}..{upstream_ref}"])
    )
    upstream_diff_stat = lines(
        git(["diff", "--stat", "--find-renames", f"{private_ref}...{upstream_ref}"])
    )

    private_changed = set(lines(git(["diff", "--name-only", f"{merge_base}..{private_ref}"])))
    upstream_changed = set(lines(git(["diff", "--name-only", f"{merge_base}..{upstream_ref}"])))
    overlap_files = sorted(private_changed & upstream_changed)
    design_sensitive_overlap = [
        path for path in overlap_files if match_any(path, DESIGN_SENSITIVE_PATTERNS)
    ]
    keep_local_overlap = [
        path for path in overlap_files if match_any(path, KEEP_LOCAL_METHOD_PATTERNS)
    ]

    return TriageData(
        private_ref=private_ref,
        upstream_ref=upstream_ref,
        private_sha=private_sha,
        upstream_sha=upstream_sha,
        merge_base=merge_base,
        private_only_count=private_only_count,
        upstream_only_count=upstream_only_count,
        private_only_commits=private_only_commits,
        upstream_only_commits=upstream_only_commits,
        upstream_diff_stat=upstream_diff_stat,
        overlap_files=overlap_files,
        design_sensitive_overlap=design_sensitive_overlap,
        keep_local_overlap=keep_local_overlap,
    )


def _section(title: str, items: Iterable[str], *, bullet: bool = True) -> list[str]:
    out = [f"## {title}", ""]
    material = list(items)
    if not material:
        out.append("- none")
    elif bullet:
        out.extend(f"- {item}" for item in material)
    else:
        out.extend(material)
    out.append("")
    return out


def render_report(data: TriageData) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: list[str] = [
        "# Upstream Sync Report",
        "",
        f"- generated_at: `{now}`",
        f"- private_ref: `{data.private_ref}`",
        f"- private_sha: `{data.private_sha}`",
        f"- upstream_ref: `{data.upstream_ref}`",
        f"- upstream_sha: `{data.upstream_sha}`",
        f"- merge_base: `{data.merge_base}`",
        f"- private_only_commits: {data.private_only_count}",
        f"- upstream_only_commits: {data.upstream_only_count}",
        "",
    ]

    out.extend(
        _section(
            "Selective Merge Policy",
            [
                "Do not blind-merge upstream into the private deployment fork.",
                "Assume a fresh start from current upstream and ask whether the local method is still what we would choose today.",
                "Keep local deployment design only where it is still intentional, required, and better than upstream for the Snapetech target.",
                "Prefer selective adaptation for gateway restart/reload behavior, pod deployment workflow, repo-first self-edit rules, and skills sync safeguards.",
                "Treat design-sensitive overlap as mandatory human review, even when the textual merge is clean.",
                "The invariant is that all required Snapetech outputs/tooling/connections still work, or newer Hermes behavior makes the custom path obsolete.",
            ],
        )
    )
    out.extend(_section("Private-only Commits", data.private_only_commits))
    out.extend(_section("Upstream-only Commits", data.upstream_only_commits[:120]))
    out.extend(_section("Files Changed On Both Sides", data.overlap_files))
    out.extend(_section("Design-Sensitive Overlap", data.design_sensitive_overlap))
    out.extend(_section("Keep-Local-Method Overlap", data.keep_local_overlap))
    out.extend(_section("Upstream File Impact", data.upstream_diff_stat[:200], bullet=False))
    out.extend(
        _section(
            "Recommended Next Step",
            [
                "Create or refresh an upstream-sync branch from the private fork main.",
                "Resolve design-sensitive overlap first.",
                "For each overlap, classify it as upstream-first, local-first, or hybrid using the fresh-upstream test.",
                "Keep the local method in keep-local files only when we would still choose it today on fresh upstream.",
                "Adapt upstream bug fixes around the local method instead of replacing it wholesale.",
                "Delete obsolete local divergence when upstream now covers the same goal cleanly.",
                "Run focused tests on touched gateway/status/skills_sync paths before widening the merge.",
            ],
        )
    )
    return "\n".join(out).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-ref", default="refs/remotes/origin/main")
    parser.add_argument("--upstream-ref", default="refs/remotes/upstream-sync/main")
    parser.add_argument("--output", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = render_report(collect_triage(args.private_ref, args.upstream_ref))
    print(report, end="")
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
