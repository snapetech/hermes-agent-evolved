import importlib
from pathlib import Path


def _fake_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "pyproject.toml").write_text("[project]\nname = 'fake-hermes'\n", encoding="utf-8")
    (path / "run_agent.py").write_text("# fake repo marker\n", encoding="utf-8")
    return path


def test_stack_repo_env_overrides_source_root(monkeypatch, tmp_path):
    repo = _fake_repo(tmp_path / "mounted-hermes")
    monkeypatch.setenv("HERMES_STACK_REPO", str(repo))

    import scripts.stack_cve_check as stack_cve_check

    stack_cve_check = importlib.reload(stack_cve_check)
    assert stack_cve_check.ROOT == repo.resolve()
    assert stack_cve_check.DEFAULT_INVENTORY == repo / "docs" / "stack-inventory.json"


def test_report_includes_repository_durability(monkeypatch, tmp_path):
    import scripts.stack_cve_check as stack_cve_check

    report_path = tmp_path / "stack-cve-report.md"
    audit = {
        "generated_at": "2026-04-21T00:00:00+00:00",
        "inventory_generated_at": "2026-04-21T00:00:00+00:00",
        "git": {
            "root": "/opt/data/hermes-agent",
            "source_root": "/app",
            "branch": "main",
            "head": "abc123",
            "upstream": "origin/main",
            "ahead_behind": "0\t1",
            "dirty": True,
            "status_short": ["M docs/stack-cve-report.md"],
        },
        "osv": {"package_count": 0, "finding_count": 0, "findings": []},
        "npm_audit": {"totals": {}, "audits": []},
        "recommendations": [],
    }

    stack_cve_check.write_report(audit, report_path)

    text = report_path.read_text(encoding="utf-8")
    assert "## Repository Durability" in text
    assert "Target repo: `/opt/data/hermes-agent`" in text
    assert "Script source: `/app`" in text
    assert "`M docs/stack-cve-report.md`" in text


def test_install_cron_updates_existing_job(monkeypatch, tmp_path):
    import cron.jobs as jobs
    import scripts.stack_cve_check as stack_cve_check

    cron_dir = tmp_path / "cron"
    monkeypatch.setattr(jobs, "CRON_DIR", cron_dir)
    monkeypatch.setattr(jobs, "OUTPUT_DIR", cron_dir / "output")
    monkeypatch.setattr(jobs, "JOBS_FILE", cron_dir / "jobs.json")

    first = stack_cve_check.install_cron_job("0 9 * * 1")
    second = stack_cve_check.install_cron_job("0 10 * * 1")

    assert first["created"] is True
    assert second["created"] is False
    assert second["updated"] is True
    assert "checked-out Hermes repo" in second["job"]["prompt"]
    assert second["job"]["schedule"]["expr"] == "0 10 * * 1"
    assert second["job"]["skills"] == ["stack-cve-checkup"]
