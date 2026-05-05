import importlib
import sys
import types
from pathlib import Path

import yaml


def _write_user_config(home: Path, payload: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")


def test_load_config_can_ignore_user_config(monkeypatch, tmp_path):
    home = tmp_path / ".hermes"
    _write_user_config(
        home,
        {
            "model": {"provider": "anthropic"},
            "agent": {"max_turns": 7},
        },
    )
    monkeypatch.setenv("HERMES_HOME", str(home))

    import hermes_cli.config as config_mod

    importlib.reload(config_mod)
    loaded = config_mod.load_config()
    assert loaded["model"]["provider"] == "anthropic"
    assert loaded["agent"]["max_turns"] == 7

    monkeypatch.setenv("HERMES_IGNORE_USER_CONFIG", "1")
    importlib.reload(config_mod)
    ignored = config_mod.load_config()
    assert ignored["model"] == ""
    assert ignored["agent"]["max_turns"] == config_mod.DEFAULT_CONFIG["agent"]["max_turns"]


def test_load_cli_config_can_ignore_user_config(monkeypatch, tmp_path):
    home = tmp_path / ".hermes"
    _write_user_config(
        home,
        {
            "model": {"provider": "anthropic", "default": "claude-sonnet"},
            "agent": {"max_turns": 11},
        },
    )
    monkeypatch.setenv("HERMES_HOME", str(home))

    import cli as cli_mod

    cli_mod._hermes_home = home
    loaded = cli_mod.load_cli_config()
    assert loaded["model"]["provider"] == "anthropic"
    assert loaded["agent"]["max_turns"] == 11

    monkeypatch.setenv("HERMES_IGNORE_USER_CONFIG", "1")
    ignored = cli_mod.load_cli_config()
    assert ignored["model"]["provider"] == "auto"
    assert ignored["agent"]["max_turns"] == 90


def test_cmd_chat_exports_ignore_env_before_importing_cli(monkeypatch):
    import hermes_cli.main as main_mod

    captured = {}

    fake_cli = types.ModuleType("cli")

    def fake_main(**kwargs):
        captured["kwargs"] = kwargs
        captured["ignore_user_config"] = sys.modules["os"].environ.get("HERMES_IGNORE_USER_CONFIG")
        captured["ignore_rules"] = sys.modules["os"].environ.get("HERMES_IGNORE_RULES")

    fake_cli.main = fake_main

    monkeypatch.setitem(sys.modules, "cli", fake_cli)
    monkeypatch.setattr(main_mod, "_has_any_provider_configured", lambda: True)
    monkeypatch.setattr(main_mod, "_resolve_session_by_name_or_id", lambda value: value)
    monkeypatch.setattr(main_mod, "_resolve_last_session", lambda source=None: None)
    monkeypatch.setattr(main_mod, "_resolve_latest_tui_pending_turn_session", lambda: None)
    monkeypatch.setattr("hermes_cli.banner.prefetch_update_check", lambda: None)
    monkeypatch.setattr("tools.skills_sync.sync_skills", lambda quiet=True: None)

    args = types.SimpleNamespace(
        tui=False,
        continue_last=None,
        resume=None,
        yolo=False,
        source=None,
        ignore_user_config=True,
        ignore_rules=True,
        model=None,
        provider=None,
        toolsets=None,
        skills=None,
        verbose=False,
        quiet=False,
        query=None,
        image=None,
        worktree=False,
        checkpoints=False,
        pass_session_id=False,
        max_turns=None,
    )

    main_mod.cmd_chat(args)

    assert captured["ignore_user_config"] == "1"
    assert captured["ignore_rules"] == "1"
    assert captured["kwargs"]["ignore_rules"] is True


def test_hermes_cli_ignore_rules_sets_agent_skip_flags(monkeypatch):
    import cli as cli_mod

    captured = {}

    class DummyAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.session_id = kwargs["session_id"]

    monkeypatch.setattr(cli_mod, "AIAgent", DummyAgent)
    monkeypatch.setattr(cli_mod.HermesCLI, "_ensure_runtime_credentials", lambda self: True)
    monkeypatch.setattr(cli_mod, "_active_agent_ref", None, raising=False)

    cli = cli_mod.HermesCLI(ignore_rules=True)
    assert cli.prefill_messages == []
    assert cli._init_agent()
    assert captured["skip_context_files"] is True
    assert captured["skip_memory"] is True
