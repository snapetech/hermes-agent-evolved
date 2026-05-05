"""Closed-loop self-review for the level-up plugin.

Scans recent recovery and tool-metrics data, clusters recurring problems,
auto-applies a small set of low-risk lessons, and writes a review queue for
anything that still needs operator judgment.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home


@dataclass
class Cluster:
    key: str
    tool_name: str
    category: str
    pattern: str
    count: int
    first_ts: float
    last_ts: float
    example: str
    action: str
    target_file: str = ""
    target_kind: str = ""
    target_payload: dict[str, Any] = field(default_factory=dict)
    auto_applied: bool = False


@dataclass
class SelfReviewReport:
    ts: float
    window_days: int
    recovery_events_scanned: int
    tool_metrics_scanned: int
    clusters_total: int
    auto_applied: int
    queued_for_review: int
    cluster_keys: list[str] = field(default_factory=list)


_BRANCH_MISMATCH_RE = re.compile(
    r"(pathspec.+did not match|remote branch .+ not found|couldn't find remote ref (main|master))",
    re.I,
)
_NOT_GIT_REPO_RE = re.compile(r"not a git repository", re.I)
_CONTAINER_NOT_FOUND_RE = re.compile(r'container not found \("([^"]+)"\)', re.I)
_SEND_MESSAGE_CRON_RE = re.compile(r"send_message", re.I)


def _level_up_dir() -> Path:
    path = get_hermes_home() / "level_up"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_jsonl(path: Path, *, since_ts: float | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        if since_ts is not None and float(row.get("ts") or 0.0) < since_ts:
            continue
        rows.append(row)
    return rows


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _existing_harvest_rows(name: str) -> list[dict[str, Any]]:
    return _read_jsonl(_level_up_dir() / "harvest" / name)


def _harvest_contains(name: str, *, field_name: str, value: str) -> bool:
    wanted = value.strip()
    if not wanted:
        return True
    for row in _existing_harvest_rows(name):
        if str(row.get(field_name) or "").strip() == wanted:
            return True
    return False


def _cluster_action(tool_name: str, category: str, excerpt: str) -> tuple[str, str, str, dict[str, Any]]:
    if _BRANCH_MISMATCH_RE.search(excerpt):
        fix = (
            "Do not assume `main` or `master`. Detect the actual branch with "
            "`git branch --show-current` for the local branch and "
            "`git symbolic-ref refs/remotes/origin/HEAD` or `git remote show origin` "
            "for the default remote branch before checkout/pull/push logic."
        )
        return (
            "auto_apply",
            "corrections.jsonl",
            "correction",
            {
                "context": "Git branch mismatch from assuming `main`/`master`",
                "fix": fix,
            },
        )
    if _NOT_GIT_REPO_RE.search(excerpt):
        avoid = (
            "Before running git commands in a directory, verify it contains a `.git` "
            "directory or skip it. Treat WORKFLOWS-like directories and exports as "
            "non-repos unless proven otherwise."
        )
        return (
            "auto_apply",
            "avoid.jsonl",
            "avoid",
            {
                "avoid": avoid,
            },
        )
    if category == "approval_timeout" and _SEND_MESSAGE_CRON_RE.search(excerpt):
        avoid = (
            "In cron contexts, do not call `send_message` manually. Cron delivers the "
            "final response automatically; return the result or `[SILENT]`."
        )
        return (
            "auto_apply",
            "avoid.jsonl",
            "avoid",
            {
                "avoid": avoid,
            },
        )
    if _CONTAINER_NOT_FOUND_RE.search(excerpt):
        return ("queue_review", "", "", {})
    if category in {"backend_unreachable", "backend_timeout", "context_overflow"}:
        return ("queue_review", "", "", {})
    return ("queue_review", "", "", {})


def _pattern_name(excerpt: str) -> str:
    if _BRANCH_MISMATCH_RE.search(excerpt):
        return "git_branch_mismatch"
    if _NOT_GIT_REPO_RE.search(excerpt):
        return "not_git_repo"
    if _CONTAINER_NOT_FOUND_RE.search(excerpt):
        return "rollout_container_missing"
    if _SEND_MESSAGE_CRON_RE.search(excerpt):
        return "cron_send_message"
    return "generic"


def _cluster_recovery_events(rows: list[dict[str, Any]], *, min_occurrences: int) -> list[Cluster]:
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        tool_name = str(row.get("tool_name") or "")
        category = str(row.get("category") or "unknown")
        excerpt = str(row.get("message_excerpt") or "")
        pattern = _pattern_name(excerpt)
        buckets[(tool_name, category, pattern)].append(row)

    clusters: list[Cluster] = []
    for (tool_name, category, pattern), events in buckets.items():
        if len(events) < min_occurrences:
            continue
        events_sorted = sorted(events, key=lambda item: float(item.get("ts") or 0.0))
        example = str(events_sorted[-1].get("message_excerpt") or "")[:300]
        action, target_file, target_kind, target_payload = _cluster_action(tool_name, category, example)
        clusters.append(
            Cluster(
                key=f"{tool_name}:{category}:{pattern}",
                tool_name=tool_name,
                category=category,
                pattern=pattern,
                count=len(events_sorted),
                first_ts=float(events_sorted[0].get("ts") or 0.0),
                last_ts=float(events_sorted[-1].get("ts") or 0.0),
                example=example,
                action=action,
                target_file=target_file,
                target_kind=target_kind,
                target_payload=target_payload,
            )
        )
    clusters.sort(key=lambda item: (-item.count, item.key))
    return clusters


def _apply_cluster(cluster: Cluster) -> bool:
    if cluster.action != "auto_apply" or not cluster.target_file:
        return False
    ts = time.time()
    harvest_dir = _level_up_dir() / "harvest"

    if cluster.target_kind == "correction":
        context = str(cluster.target_payload.get("context") or "").strip()
        fix = str(cluster.target_payload.get("fix") or "").strip()
        if _harvest_contains("corrections.jsonl", field_name="fix", value=fix):
            return False
        _append_jsonl(
            harvest_dir / "corrections.jsonl",
            {
                "ts": ts,
                "session_id": f"self_review_{int(ts)}",
                "context": context,
                "fix": fix,
                "status": "auto_applied",
                "source": "self_review",
                "cluster_key": cluster.key,
            },
        )
        cluster.auto_applied = True
        return True

    if cluster.target_kind == "avoid":
        avoid = str(cluster.target_payload.get("avoid") or "").strip()
        if _harvest_contains("avoid.jsonl", field_name="avoid", value=avoid):
            return False
        _append_jsonl(
            harvest_dir / "avoid.jsonl",
            {
                "ts": ts,
                "session_id": f"self_review_{int(ts)}",
                "avoid": avoid,
                "status": "auto_applied",
                "source": "self_review",
                "cluster_key": cluster.key,
            },
        )
        cluster.auto_applied = True
        return True

    return False


def _write_review_queue(clusters: list[Cluster]) -> int:
    path = _level_up_dir() / "review_queue.jsonl"
    existing = _read_jsonl(path)
    existing_keys = {str(item.get("cluster_key") or "") for item in existing}
    queued = 0
    for cluster in clusters:
        if cluster.action != "queue_review":
            continue
        if cluster.key in existing_keys:
            continue
        _append_jsonl(
            path,
            {
                "ts": time.time(),
                "cluster_key": cluster.key,
                "tool_name": cluster.tool_name,
                "category": cluster.category,
                "pattern": cluster.pattern,
                "count": cluster.count,
                "example": cluster.example,
                "status": "proposed",
                "source": "self_review",
            },
        )
        queued += 1
    return queued


def _write_status(report: SelfReviewReport, clusters: list[Cluster]) -> None:
    root = _level_up_dir()
    status_json = root / "self_review_status.json"
    status_md = root / "self_review_status.md"
    report.cluster_keys = [cluster.key for cluster in clusters]
    status_json.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Self Review Status",
        "",
        f"- Timestamp: {int(report.ts)}",
        f"- Window (days): {report.window_days}",
        f"- Recovery events scanned: {report.recovery_events_scanned}",
        f"- Tool metrics scanned: {report.tool_metrics_scanned}",
        f"- Clusters: {report.clusters_total}",
        f"- Auto-applied: {report.auto_applied}",
        f"- Queued for review: {report.queued_for_review}",
        "",
        "## Clusters",
    ]
    for cluster in clusters:
        lines.extend(
            [
                "",
                f"### {cluster.key}",
                f"- Count: {cluster.count}",
                f"- Action: {cluster.action}{' (applied)' if cluster.auto_applied else ''}",
                f"- Example: `{cluster.example[:200]}`",
            ]
        )
    status_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_self_review(*, window_days: int = 7, min_occurrences: int = 2) -> SelfReviewReport:
    cutoff = time.time() - max(1, window_days) * 86400
    recovery_rows = _read_jsonl(_level_up_dir() / "recovery.jsonl", since_ts=cutoff)
    metric_rows = _read_jsonl(_level_up_dir() / "tool_metrics.jsonl", since_ts=cutoff)

    clusters = _cluster_recovery_events(recovery_rows, min_occurrences=min_occurrences)
    auto_applied = 0
    for cluster in clusters:
        if _apply_cluster(cluster):
            auto_applied += 1
    queued = _write_review_queue(clusters)

    report = SelfReviewReport(
        ts=time.time(),
        window_days=window_days,
        recovery_events_scanned=len(recovery_rows),
        tool_metrics_scanned=len(metric_rows),
        clusters_total=len(clusters),
        auto_applied=auto_applied,
        queued_for_review=queued,
    )
    _write_status(report, clusters)
    _append_jsonl(_level_up_dir() / "self_review_runs.jsonl", asdict(report))
    return report


def self_review_command(raw_args: str = "") -> str:
    parts = [part for part in (raw_args or "").split() if part]
    try:
        window_days = max(1, min(30, int(parts[0]))) if parts else 7
    except ValueError:
        window_days = 7
    report = run_self_review(window_days=window_days)
    return (
        f"Self-review complete ({window_days}d window):\n"
        f"- recovery events scanned: {report.recovery_events_scanned}\n"
        f"- tool metrics scanned: {report.tool_metrics_scanned}\n"
        f"- clusters: {report.clusters_total}\n"
        f"- auto-applied: {report.auto_applied}\n"
        f"- review queue additions: {report.queued_for_review}\n"
        f"See `{_level_up_dir() / 'self_review_status.md'}` and "
        f"`{_level_up_dir() / 'review_queue.jsonl'}`."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Hermes level-up self-review.")
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")
    parser.add_argument(
        "--min-occurrences",
        type=int,
        default=2,
        help="Minimum repeated failures to form a cluster (default: 2)",
    )
    args = parser.parse_args(argv)
    report = run_self_review(window_days=args.days, min_occurrences=args.min_occurrences)
    print(json.dumps(asdict(report), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
