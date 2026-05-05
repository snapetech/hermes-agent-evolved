"""Tests for the Hermes internal introspection collector."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


SCAN_PATH = Path(__file__).resolve().parent.parent / "deploy/k8s/hermes-introspection-scan.py"


def load_scan(tmp_path: Path):
    home = tmp_path / ".hermes"
    home.mkdir()
    os.environ["HERMES_HOME"] = str(home)
    os.environ["HERMES_INTROSPECTION_STATE_DIR"] = str(home / "self-improvement" / "introspection")
    os.environ["HERMES_INTROSPECTION_SESSION_DB"] = str(home / "state.db")
    spec = importlib.util.spec_from_file_location(f"hermes_introspection_scan_{tmp_path.name}", SCAN_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, home


def test_redact_hides_common_secret_shapes(tmp_path):
    scan, _ = load_scan(tmp_path)
    fake_pat = "ghp_" + "a" * 36
    fake_key = "sk-" + "b" * 32

    out = scan.redact(f"Authorization: Bearer {fake_key}; token={fake_pat}")

    assert fake_pat not in out
    assert fake_key not in out
    assert "[REDACTED]" in out


def test_classify_issue_prefers_specific_categories(tmp_path):
    scan, _ = load_scan(tmp_path)

    assert scan.classify_issue("pytest failed with AssertionError") == "test_failure"
    assert scan.classify_issue("No module named yaml") == "missing_dependency"
    assert scan.classify_issue("fatal: not a git repository") == "path_error"
    assert scan.classify_issue("request timed out after 30 seconds") == "timeout"


def test_collect_session_metrics_detects_tool_errors_and_corrections(tmp_path):
    scan, home = load_scan(tmp_path)

    from hermes_state import SessionDB

    db_path = home / "state.db"
    db = SessionDB(db_path)
    try:
        db.create_session(session_id="s1", source="cli", model="test")
        db.append_message("s1", "user", "Please run the tests")
        db.append_message(
            "s1",
            "assistant",
            "",
            tool_calls=[{"function": {"name": "terminal", "arguments": "{}"}}],
        )
        db.append_message(
            "s1",
            "tool",
            '{"success": false, "error": "pytest failed with AssertionError"}',
            tool_name="terminal",
        )
        db.append_message("s1", "user", "No, that's wrong, use scripts/run_tests.sh instead")

        metrics = scan.collect_session_metrics(db_path, window_days=1, limit=10)
    finally:
        db.close()

    assert metrics.sessions_seen == 1
    assert len(metrics.tool_errors) == 1
    assert metrics.tool_errors[0].category == "test_failure"
    assert len(metrics.user_corrections) == 1
    assert metrics.issue_counts["user_correction"] == 1


def test_memory_quality_flags_task_progress_and_long_entries(tmp_path):
    scan, home = load_scan(tmp_path)
    memory_dir = home / "memories"
    memory_dir.mkdir()
    (memory_dir / "MEMORY.md").write_text(
        "Implemented the current task today and need to finish cleanup\n§\n"
        + ("stable environment fact " * 40),
        encoding="utf-8",
    )
    (memory_dir / "USER.md").write_text("Prefers concise summaries\n", encoding="utf-8")

    evidence, counts = scan.analyze_memory_quality(memory_dir)

    assert counts["memory_entries"] == 2
    assert counts["user_entries"] == 1
    assert counts["task_progress_entries"] == 1
    assert any(item.category == "memory_noise" for item in evidence)


def test_render_report_includes_candidate_sections(tmp_path):
    scan, home = load_scan(tmp_path)
    metrics = scan.SessionMetrics(sessions_seen=1, messages_seen=4, tool_results_seen=1)
    metrics.tool_errors.append(
        scan.Evidence(
            kind="tool_error",
            category="path_error",
            summary="terminal produced path_error",
            tool_name="terminal",
            snippets=["fatal: not a git repository"],
        )
    )
    metrics.issue_counts["path_error"] = 1

    report = scan.render_report(
        metrics,
        [],
        {"memory_entries": 0, "user_entries": 0, "long_entries": 0, "task_progress_entries": 0},
        [],
        {"skills_seen": 0, "todo_markers": 0, "large_skills": 0},
        {"trajectory_files": 0, "completed_rows": 0, "failed_rows": 0},
        started_at="2026-04-21T00:00:00+00:00",
        window_days=7,
        session_db_path=home / "state.db",
    )

    assert "## Working Well" in report
    assert "## Repeated Friction" in report
    assert "## Candidate Experiments" in report
    assert "workspace/repo/path preflight" in report
