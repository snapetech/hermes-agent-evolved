from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path


def _write_state(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_begin_run_resumes_same_run(monkeypatch, tmp_path):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))

    from scripts import local_llm_nightly_state as nightly

    first = nightly.begin_run(phase="startup", run_id="2026-04-23")
    second = nightly.begin_run(phase="research", run_id="2026-04-23")

    assert first["run_id"] == "2026-04-23"
    assert second["status"] == "running"
    assert second["phase"] == "research"
    assert second["attempt_count"] == 2
    assert second["recovery"]["needs_reconciliation"] is True


def test_reconcile_flags_stale_running_and_leftover_rejected_download(monkeypatch, tmp_path):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))

    from scripts import local_llm_nightly_state as nightly

    paths = nightly.nightly_paths()
    rejected = tmp_path / "models" / "reject.gguf"
    rejected.parent.mkdir(parents=True, exist_ok=True)
    rejected.write_text("x", encoding="utf-8")
    stale = (datetime.now(UTC) - timedelta(hours=30)).isoformat()
    _write_state(
        paths.state,
        {
            "schema_version": 1,
            "run_id": "2026-04-22",
            "status": "running",
            "phase": "cleanup",
            "attempt_count": 1,
            "started_at": stale,
            "updated_at": stale,
            "ended_at": None,
            "current_candidate": "reject.gguf",
            "summary": "",
            "report_path": str(paths.reports_dir / "2026-04-22.md"),
            "latest_report_path": str(paths.latest_report),
            "recovery": {},
            "candidates": [
                {
                    "name": "reject.gguf",
                    "status": "rejected",
                    "local_path": str(rejected),
                    "notes": ["documented reject"],
                }
            ],
            "notes": [],
            "history": [],
        },
    )

    result = nightly.reconcile_state(model_dir=rejected.parent)

    issue_types = {item["type"] for item in result["issues"]}
    assert "stale_running_state" in issue_types
    assert "leftover_rejected_download" in issue_types
    assert result["state"]["status"] == "interrupted"
    assert result["state"]["recovery"]["needs_reconciliation"] is True


def test_finalize_marks_completed_and_clears_current_candidate(monkeypatch, tmp_path):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))

    from scripts import local_llm_nightly_state as nightly

    nightly.begin_run(phase="benchmark", run_id="2026-04-23")
    nightly.update_candidate(name="keep.gguf", status="benchmarked", local_path=str(tmp_path / "keep.gguf"))
    final = nightly.finalize_run(status="completed", summary="no regressions found")

    assert final["status"] == "completed"
    assert final["summary"] == "no regressions found"
    assert final["current_candidate"] is None
    assert final["recovery"]["needs_reconciliation"] is False
