from datetime import datetime
from unittest.mock import MagicMock, patch

from cli import HermesCLI


def _make_cli():
    cli_obj = HermesCLI.__new__(HermesCLI)
    cli_obj.console = MagicMock()
    cli_obj.agent = MagicMock()
    cli_obj.active_mode_name = "code"
    cli_obj.system_prompt = ""
    cli_obj.personalities = {}
    cli_obj._session_db = MagicMock()
    cli_obj.session_id = "sess-1"
    cli_obj.session_start = datetime(2026, 4, 20, 12, 0)
    cli_obj.model = "openai/gpt-5.4"
    cli_obj.provider = "openai"
    cli_obj._agent_running = False
    return cli_obj


def test_mode_command_lists_modes(capsys):
    cli_obj = _make_cli()
    cli_obj._handle_mode_command("/mode")
    out = capsys.readouterr().out
    assert "Current: code" in out
    assert "architect" in out
    assert "orchestrator" in out


def test_mode_command_sets_mode_and_invalidates_agent():
    cli_obj = _make_cli()
    with patch("cli.save_config_value", return_value=True) as mock_save:
        cli_obj._handle_mode_command("/mode ask")
    assert cli_obj.active_mode_name == "ask"
    assert cli_obj.agent is None
    mock_save.assert_called_once_with("agent.mode", "ask")


def test_mode_command_unknown_mode_does_not_change_state(capsys):
    cli_obj = _make_cli()
    cli_obj._handle_mode_command("/mode nope")
    out = capsys.readouterr().out
    assert "Unknown mode" in out
    assert cli_obj.active_mode_name == "code"

