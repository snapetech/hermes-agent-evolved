import argparse
import json
from pathlib import Path


def test_audit_report_skip_live_is_redacted():
    from scripts import audit_live_reproducibility as audit

    args = argparse.Namespace(
        namespace="hermes",
        target="deploy/hermes-gateway",
        container="gateway",
        hermes_home="/opt/data",
        cron_seed=str(audit.DEFAULT_CRON_SEED),
        skill_lock=str(audit.DEFAULT_SKILL_LOCK),
        skip_live=True,
    )

    report = audit.build_report(args)

    assert report["local"]["root"].endswith("hermes-agent")
    assert report["live"] == {}
    assert "findings" in report


def test_audit_report_flags_persistent_repo_head_drift(monkeypatch):
    from scripts import audit_live_reproducibility as audit

    local_head = "a" * 40
    monkeypatch.setattr(audit, "git_value", lambda args, cwd=audit.ROOT: local_head if args == ["rev-parse", "HEAD"] else "")
    monkeypatch.setattr(audit, "repo_config_hash", lambda: "config-hash")
    monkeypatch.setattr(audit, "expected_cron_names", lambda path: [])
    monkeypatch.setattr(audit, "expected_skill_names", lambda path: [])
    monkeypatch.setattr(audit, "repo_skill_names", lambda: [])
    monkeypatch.setattr(
        audit,
        "collect_live",
        lambda *args, **kwargs: {
            "images": {"gateway": f"hermes-agent-sudo:git-{local_head}"},
            "app_commit": "",
            "data_repo_head": "b" * 40,
            "data_repo_ahead_behind": "0\t0",
            "data_repo_dirty": False,
            "configmap_config_hash": "config-hash",
            "config_hash": "config-hash",
            "cron_names": [],
            "skill_names": [],
        },
    )
    args = argparse.Namespace(
        namespace="hermes",
        target="deploy/hermes-gateway",
        container="gateway",
        hermes_home="/opt/data",
        kubectl="kubectl",
        cron_seed=str(audit.DEFAULT_CRON_SEED),
        skill_lock=str(audit.DEFAULT_SKILL_LOCK),
        skip_live=False,
    )

    report = audit.build_report(args)

    assert any(item["area"] == "persistent_repo" for item in report["findings"])


def test_seed_cron_jobs_dry_run(tmp_path, monkeypatch):
    from scripts import seed_cron_jobs

    manifest = tmp_path / "cron.json"
    manifest.write_text(
        json.dumps({
            "jobs": [{
                "name": "Example job",
                "schedule": "0 9 * * 1",
                "prompt": "hello",
                "skills": ["stack-cve-checkup"],
            }]
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr("cron.jobs.load_jobs", lambda: [])
    results = seed_cron_jobs.seed_jobs(manifest, dry_run=True)

    assert results == [{"name": "Example job", "action": "create", "dry_run": True}]


def test_default_cron_seed_includes_nightly_local_llm_review():
    from scripts import audit_live_reproducibility as audit
    import json

    names = audit.expected_cron_names(audit.DEFAULT_CRON_SEED)

    assert "Hermes nightly local LLM review" in names
    payload = json.loads(audit.DEFAULT_CRON_SEED.read_text(encoding="utf-8"))
    llm_job = next(job for job in payload["jobs"] if job["name"] == "Hermes nightly local LLM review")
    assert "self-improvement/local-llm-nightly/reports/YYYY-MM-DD.md" in llm_job["prompt"]
    assert "self-improvement/local-llm-nightly/reports/latest.md" in llm_job["prompt"]
    assert "self-improvement/local-llm-nightly/state.json" in llm_job["prompt"]
    assert "scripts/local_llm_nightly_state.py reconcile" in llm_job["prompt"]
    assert "scripts/local_llm_nightly_state.py begin --phase startup" in llm_job["prompt"]


def test_default_cron_seed_includes_local_llm_approval_handoff():
    from scripts import audit_live_reproducibility as audit
    import json

    names = audit.expected_cron_names(audit.DEFAULT_CRON_SEED)

    assert "Hermes local LLM approval handoff" in names
    payload = json.loads(audit.DEFAULT_CRON_SEED.read_text(encoding="utf-8"))
    handoff_job = next(job for job in payload["jobs"] if job["name"] == "Hermes local LLM approval handoff")
    assert handoff_job["deliver"] == "local,email:keith@snape.tech"
    assert "scripts/local_llm_handoff_packet.py" in handoff_job["prompt"]
    assert "llm-handoff/YYYY-MM-DD-<slug>" in handoff_job["prompt"]


def test_skill_lock_includes_local_llm_skills():
    from scripts import audit_live_reproducibility as audit

    names = audit.expected_skill_names(audit.DEFAULT_SKILL_LOCK)

    assert "hermes-local-llm-nightly" in names
    assert "hermes-local-llm-promotion-handoff" in names


def test_install_skill_manifest_dry_run(tmp_path):
    from scripts import install_skill_manifest

    source = tmp_path / "repo" / "skills" / "security" / "demo" / "SKILL.md"
    source.parent.mkdir(parents=True)
    source.write_text("---\nname: demo\n---\n", encoding="utf-8")

    manifest = tmp_path / "skills.json"
    manifest.write_text(
        json.dumps({"skills": [{"name": "demo", "repo_path": str(source.relative_to(tmp_path / "repo"))}]}),
        encoding="utf-8",
    )

    old_root = install_skill_manifest.ROOT
    install_skill_manifest.ROOT = tmp_path / "repo"
    try:
        results = install_skill_manifest.install_manifest(manifest, dest_home=tmp_path / "home", dry_run=True)
    finally:
        install_skill_manifest.ROOT = old_root

    assert results[0]["action"] == "install"
    assert results[0]["dest"].endswith("skills/security/demo/SKILL.md")


def test_runtime_manifest_names_strip_versions(tmp_path):
    from scripts.check_runtime_package_drift import manifest_names

    path = tmp_path / "packages.txt"
    path.write_text("requests>=2\n@openai/codex@0.121.0\nmcporter@0.9.0\npytest # comment\n[]\n", encoding="utf-8")

    assert manifest_names(path) == {"requests", "@openai/codex", "mcporter", "pytest"}


def test_runtime_apt_aliases_include_compatibility_names(monkeypatch):
    from scripts import check_runtime_package_drift

    monkeypatch.setattr(
        check_runtime_package_drift,
        "run",
        lambda *_args, **_kwargs: {"ok": True, "stdout": "bind9-dnsutils\ncurl\n", "stderr": ""},
    )

    assert "dnsutils" in check_runtime_package_drift.installed_apt()


def test_runtime_pip_python_prefers_virtualenv(tmp_path, monkeypatch):
    from scripts.check_runtime_package_drift import resolve_pip_python

    venv = tmp_path / ".venv"
    python = venv / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    monkeypatch.delenv("PIP_PYTHON", raising=False)
    monkeypatch.setenv("VIRTUAL_ENV", str(venv))

    assert resolve_pip_python() == str(python)
