import importlib.util
import json
from pathlib import Path


def _load_module(monkeypatch, hermes_home: Path):
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "state_reflection_summary.py"
    spec = importlib.util.spec_from_file_location("state_reflection_summary", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_state_reflection_summary_is_bounded_and_redacts_secrets(tmp_path, monkeypatch, capsys):
    hermes_home = tmp_path / "hermes"
    harvest_dir = hermes_home / "level_up" / "harvest"
    harvest_dir.mkdir(parents=True)
    (hermes_home / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")

    secret_fact = (
        "slskd web UI is reachable internally and uses credentials "
        "admin / super-secret-password"
    )
    rows = [
        {"fact": "ordinary operational fact", "status": "new"},
        {"fact": secret_fact, "status": "new"},
        {"fact": secret_fact, "status": "new"},
        {"fact": "token: abc123 should not leak", "status": "new"},
    ]
    (harvest_dir / "facts.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows),
        encoding="utf-8",
    )
    (harvest_dir / "avoid.jsonl").write_text(
        json.dumps({"avoid": "password is hunter2", "status": "new"}) + "\n",
        encoding="utf-8",
    )
    (harvest_dir / "corrections.jsonl").write_text(
        json.dumps({"fix": "api key = sk-test-value", "status": "new"}) + "\n",
        encoding="utf-8",
    )

    module = _load_module(monkeypatch, hermes_home)
    assert module.main() == 0

    report = json.loads(capsys.readouterr().out)
    rendered = json.dumps(report)

    assert report["harvest"]["facts"]["rows"] == 4
    assert report["harvest"]["facts"]["statuses"] == {"new": 4}
    assert report["memory"]["exists"] is True
    assert "super-secret-password" not in rendered
    assert "hunter2" not in rendered
    assert "sk-test-value" not in rendered
    assert "abc123" not in rendered
    assert "[REDACTED]" in rendered
    assert len(rendered) < 5000
