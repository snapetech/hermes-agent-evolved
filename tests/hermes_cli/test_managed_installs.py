from types import SimpleNamespace
from unittest.mock import patch

from hermes_cli.config import (
    format_managed_message,
    get_managed_system,
    recommended_update_command,
    update_action_prefix,
    update_action_suffix,
    update_behind_words,
)
from hermes_cli.main import cmd_update
from tools.skills_hub import OptionalSkillSource


def test_get_managed_system_homebrew(monkeypatch):
    monkeypatch.setenv("HERMES_MANAGED", "homebrew")

    assert get_managed_system() == "Homebrew"
    assert recommended_update_command() == "brew upgrade hermes-agent"


def test_format_managed_message_homebrew(monkeypatch):
    monkeypatch.setenv("HERMES_MANAGED", "homebrew")

    message = format_managed_message("update Hermes Agent")

    assert "managed by Homebrew" in message
    assert "brew upgrade hermes-agent" in message


def test_recommended_update_command_defaults_to_hermes_update(monkeypatch):
    monkeypatch.delenv("HERMES_MANAGED", raising=False)
    monkeypatch.delenv("HERMES_UPDATE_COMMAND", raising=False)

    assert recommended_update_command() == "hermes update"


def test_update_notice_env_overrides(monkeypatch):
    monkeypatch.setenv("HERMES_UPDATE_COMMAND", "hermes-upstream-sync skill")
    monkeypatch.setenv("HERMES_UPDATE_ACTION_PREFIX", "use")
    monkeypatch.setenv("HERMES_UPDATE_ACTION_SUFFIX", "to plan an upstream sync")
    monkeypatch.setenv("HERMES_UPDATE_BEHIND_CONTEXT", "behind upstream")

    assert recommended_update_command() == "hermes-upstream-sync skill"
    assert update_action_prefix() == "use"
    assert update_action_suffix() == "to plan an upstream sync"
    assert update_behind_words(2) == ("commits", "behind upstream")


def test_cmd_update_blocks_managed_homebrew(monkeypatch, capsys):
    monkeypatch.setenv("HERMES_MANAGED", "homebrew")

    with patch("hermes_cli.main.subprocess.run") as mock_run:
        cmd_update(SimpleNamespace())

    assert not mock_run.called
    captured = capsys.readouterr()
    assert "managed by Homebrew" in captured.err
    assert "brew upgrade hermes-agent" in captured.err


def test_optional_skill_source_honors_env_override(monkeypatch, tmp_path):
    optional_dir = tmp_path / "optional-skills"
    optional_dir.mkdir()
    monkeypatch.setenv("HERMES_OPTIONAL_SKILLS", str(optional_dir))

    source = OptionalSkillSource()

    assert source._optional_dir == optional_dir
