from __future__ import annotations

import json
import importlib.util
import sys
import time
from pathlib import Path


def _load_self_review():
    project_root = Path(__file__).resolve().parents[2]
    module_path = project_root / "plugins" / "level-up" / "self_review.py"
    spec = importlib.util.spec_from_file_location("test_level_up_self_review_module", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


self_review = _load_self_review()


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def test_self_review_auto_applies_branch_mismatch(monkeypatch):
    home = Path(__import__("os").environ["HERMES_HOME"])
    now = time.time()
    _append_jsonl(
        home / "level_up" / "recovery.jsonl",
        [
            {
                "ts": now - 10,
                "tool_name": "terminal",
                "category": "workspace_conflict",
                "message_excerpt": "error: pathspec 'main' did not match any file(s) known to git",
            },
            {
                "ts": now - 5,
                "tool_name": "terminal",
                "category": "workspace_conflict",
                "message_excerpt": "fatal: couldn't find remote ref main",
            },
        ],
    )

    report = self_review.run_self_review(window_days=7, min_occurrences=2)

    assert report.auto_applied == 1
    corrections = (home / "level_up" / "harvest" / "corrections.jsonl").read_text(encoding="utf-8")
    assert "Do not assume `main` or `master`" in corrections
    status = json.loads((home / "level_up" / "self_review_status.json").read_text(encoding="utf-8"))
    assert status["auto_applied"] == 1


def test_self_review_auto_applies_not_git_repo_avoid():
    home = Path(__import__("os").environ["HERMES_HOME"])
    now = time.time()
    _append_jsonl(
        home / "level_up" / "recovery.jsonl",
        [
            {
                "ts": now - 8,
                "tool_name": "terminal",
                "category": "workspace_conflict",
                "message_excerpt": "fatal: not a git repository (or any of the parent directories): .git",
            },
            {
                "ts": now - 4,
                "tool_name": "terminal",
                "category": "workspace_conflict",
                "message_excerpt": "fatal: not a git repository (or any of the parent directories): .git",
            },
        ],
    )

    report = self_review.run_self_review(window_days=7, min_occurrences=2)

    assert report.auto_applied == 1
    avoids = (home / "level_up" / "harvest" / "avoid.jsonl").read_text(encoding="utf-8")
    assert "verify it contains a `.git` directory" in avoids


def test_self_review_queues_unresolved_clusters():
    home = Path(__import__("os").environ["HERMES_HOME"])
    now = time.time()
    _append_jsonl(
        home / "level_up" / "recovery.jsonl",
        [
            {
                "ts": now - 20,
                "tool_name": "terminal",
                "category": "backend_unreachable",
                "message_excerpt": "HTTP 502: Upstream request failed: <urlopen error [Errno 111] Connection refused>",
            },
            {
                "ts": now - 10,
                "tool_name": "terminal",
                "category": "backend_unreachable",
                "message_excerpt": "HTTP 502: Upstream request failed: <urlopen error [Errno 111] Connection refused>",
            },
        ],
    )

    report = self_review.run_self_review(window_days=7, min_occurrences=2)

    assert report.queued_for_review == 1
    queue_rows = (home / "level_up" / "review_queue.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(queue_rows) == 1
    item = json.loads(queue_rows[0])
    assert item["category"] == "backend_unreachable"
    assert item["status"] == "proposed"


def test_self_review_command_reports_paths():
    home = Path(__import__("os").environ["HERMES_HOME"])
    _append_jsonl(home / "level_up" / "recovery.jsonl", [])
    text = self_review.self_review_command("7")
    assert "Self-review complete" in text
    assert "self_review_status.md" in text
    assert "review_queue.jsonl" in text
