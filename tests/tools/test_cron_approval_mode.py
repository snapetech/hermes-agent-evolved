"""Tests for approvals.cron_mode — configurable approval behavior for cron jobs."""

import os
import pytest

import tools.approval as approval_module
from tools.approval import (
    _get_cron_approval_mode,
    check_all_command_guards,
    check_dangerous_command,
    detect_dangerous_command,
    extract_runtime_apt_install_packages,
    is_runtime_package_install_command,
)


@pytest.fixture(autouse=True)
def _clear_approval_state():
    approval_module._permanent_approved.clear()
    approval_module.clear_session("default")
    approval_module.clear_session("test-session")
    yield
    approval_module._permanent_approved.clear()
    approval_module.clear_session("default")
    approval_module.clear_session("test-session")


# ---------------------------------------------------------------------------
# _get_cron_approval_mode() config parsing
# ---------------------------------------------------------------------------

class TestCronApprovalModeParsing:
    def test_default_is_deny(self):
        """When no config is set, cron_mode defaults to 'deny'."""
        from unittest.mock import patch as mock_patch
        with mock_patch("hermes_cli.config.load_config", return_value={"approvals": {}}):
            assert _get_cron_approval_mode() == "deny"

    def test_explicit_deny(self):
        from unittest.mock import patch as mock_patch
        with mock_patch("hermes_cli.config.load_config", return_value={"approvals": {"cron_mode": "deny"}}):
            assert _get_cron_approval_mode() == "deny"

    def test_explicit_approve(self):
        from unittest.mock import patch as mock_patch
        with mock_patch("hermes_cli.config.load_config", return_value={"approvals": {"cron_mode": "approve"}}):
            assert _get_cron_approval_mode() == "approve"

    def test_off_maps_to_approve(self):
        """'off' is an alias for 'approve' (matches --yolo semantics)."""
        from unittest.mock import patch as mock_patch
        with mock_patch("hermes_cli.config.load_config", return_value={"approvals": {"cron_mode": "off"}}):
            assert _get_cron_approval_mode() == "approve"

    def test_allow_maps_to_approve(self):
        from unittest.mock import patch as mock_patch
        with mock_patch("hermes_cli.config.load_config", return_value={"approvals": {"cron_mode": "allow"}}):
            assert _get_cron_approval_mode() == "approve"

    def test_yes_maps_to_approve(self):
        from unittest.mock import patch as mock_patch
        with mock_patch("hermes_cli.config.load_config", return_value={"approvals": {"cron_mode": "yes"}}):
            assert _get_cron_approval_mode() == "approve"

    def test_case_insensitive(self):
        from unittest.mock import patch as mock_patch
        with mock_patch("hermes_cli.config.load_config", return_value={"approvals": {"cron_mode": "APPROVE"}}):
            assert _get_cron_approval_mode() == "approve"

    def test_unknown_value_defaults_to_deny(self):
        from unittest.mock import patch as mock_patch
        with mock_patch("hermes_cli.config.load_config", return_value={"approvals": {"cron_mode": "maybe"}}):
            assert _get_cron_approval_mode() == "deny"

    def test_config_load_failure_defaults_to_deny(self):
        """If config loading fails entirely, default to deny (safe)."""
        from unittest.mock import patch as mock_patch
        with mock_patch("hermes_cli.config.load_config", side_effect=RuntimeError("config broken")):
            assert _get_cron_approval_mode() == "deny"

    def test_yaml_boolean_false_maps_to_deny(self):
        """YAML 1.1 parses bare 'off' as False. Ensure it maps to deny."""
        from unittest.mock import patch as mock_patch
        with mock_patch("hermes_cli.config.load_config", return_value={"approvals": {"cron_mode": False}}):
            # str(False) = "False", which is not in the approve set, so deny
            assert _get_cron_approval_mode() == "deny"


# ---------------------------------------------------------------------------
# check_dangerous_command() with cron session
# ---------------------------------------------------------------------------

class TestCronDenyMode:
    """When HERMES_CRON_SESSION is set and cron_mode=deny, dangerous commands are blocked."""

    def test_dangerous_command_blocked_in_cron_deny_mode(self, monkeypatch):
        monkeypatch.setenv("HERMES_CRON_SESSION", "1")
        monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
        monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
        monkeypatch.delenv("HERMES_YOLO_MODE", raising=False)

        from unittest.mock import patch as mock_patch
        with mock_patch("tools.approval._get_cron_approval_mode", return_value="deny"):
            result = check_dangerous_command("rm -rf /tmp/stuff", "local")
            assert not result["approved"]
            assert "BLOCKED" in result["message"]
            assert "cron_mode" in result["message"]

    def test_safe_command_allowed_in_cron_deny_mode(self, monkeypatch):
        """Non-dangerous commands still work even with cron_mode=deny."""
        monkeypatch.setenv("HERMES_CRON_SESSION", "1")
        monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
        monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
        monkeypatch.delenv("HERMES_YOLO_MODE", raising=False)

        from unittest.mock import patch as mock_patch
        with mock_patch("tools.approval._get_cron_approval_mode", return_value="deny"):
            result = check_dangerous_command("ls -la", "local")
            assert result["approved"]

    def test_multiple_dangerous_patterns_blocked(self, monkeypatch):
        """All dangerous patterns are blocked, not just rm."""
        monkeypatch.setenv("HERMES_CRON_SESSION", "1")
        monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
        monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
        monkeypatch.delenv("HERMES_YOLO_MODE", raising=False)

        dangerous_commands = [
            "rm -rf /",
            "chmod 777 /etc/passwd",
            "mkfs.ext4 /dev/sda1",
            "dd if=/dev/zero of=/dev/sda",
        ]

        from unittest.mock import patch as mock_patch
        with mock_patch("tools.approval._get_cron_approval_mode", return_value="deny"):
            for cmd in dangerous_commands:
                is_dangerous, _, _ = detect_dangerous_command(cmd)
                if is_dangerous:
                    result = check_dangerous_command(cmd, "local")
                    assert not result["approved"], f"Should be blocked: {cmd}"
                    assert "BLOCKED" in result["message"]

    def test_block_message_includes_description(self, monkeypatch):
        """The block message should mention what pattern was matched."""
        monkeypatch.setenv("HERMES_CRON_SESSION", "1")
        monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
        monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
        monkeypatch.delenv("HERMES_YOLO_MODE", raising=False)

        from unittest.mock import patch as mock_patch
        with mock_patch("tools.approval._get_cron_approval_mode", return_value="deny"):
            result = check_dangerous_command("rm -rf /tmp/stuff", "local")
            assert not result["approved"]
            # Should contain the description of what was flagged
            assert "dangerous" in result["message"].lower() or "delete" in result["message"].lower()


class TestCronApproveMode:
    """When HERMES_CRON_SESSION is set and cron_mode=approve, dangerous commands pass through."""

    def test_dangerous_command_allowed_in_cron_approve_mode(self, monkeypatch):
        monkeypatch.setenv("HERMES_CRON_SESSION", "1")
        monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
        monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
        monkeypatch.delenv("HERMES_YOLO_MODE", raising=False)

        from unittest.mock import patch as mock_patch
        with mock_patch("tools.approval._get_cron_approval_mode", return_value="approve"):
            result = check_dangerous_command("rm -rf /tmp/stuff", "local")
            assert result["approved"]


# ---------------------------------------------------------------------------
# check_all_command_guards() with cron session
# ---------------------------------------------------------------------------

class TestCronDenyModeAllGuards:
    """The combined guard function also respects cron_mode."""

    def test_dangerous_command_blocked_in_combined_guard(self, monkeypatch):
        monkeypatch.setenv("HERMES_CRON_SESSION", "1")
        monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
        monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
        monkeypatch.delenv("HERMES_EXEC_ASK", raising=False)
        monkeypatch.delenv("HERMES_YOLO_MODE", raising=False)

        from unittest.mock import patch as mock_patch
        with mock_patch("tools.approval._get_cron_approval_mode", return_value="deny"):
            result = check_all_command_guards("rm -rf /tmp/stuff", "local")
            assert not result["approved"]
            assert "BLOCKED" in result["message"]

    def test_safe_command_allowed_in_combined_guard(self, monkeypatch):
        monkeypatch.setenv("HERMES_CRON_SESSION", "1")
        monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
        monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
        monkeypatch.delenv("HERMES_EXEC_ASK", raising=False)
        monkeypatch.delenv("HERMES_YOLO_MODE", raising=False)

        from unittest.mock import patch as mock_patch
        with mock_patch("tools.approval._get_cron_approval_mode", return_value="deny"):
            result = check_all_command_guards("echo hello", "local")
            assert result["approved"]

    def test_combined_guard_approve_mode(self, monkeypatch):
        monkeypatch.setenv("HERMES_CRON_SESSION", "1")
        monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
        monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
        monkeypatch.delenv("HERMES_EXEC_ASK", raising=False)
        monkeypatch.delenv("HERMES_YOLO_MODE", raising=False)

        from unittest.mock import patch as mock_patch
        with mock_patch("tools.approval._get_cron_approval_mode", return_value="approve"):
            result = check_all_command_guards("rm -rf /tmp/stuff", "local")
            assert result["approved"]


# ---------------------------------------------------------------------------
# Edge cases: cron mode interaction with other approval mechanisms
# ---------------------------------------------------------------------------

class TestCronModeInteractions:
    """Cron mode should NOT interfere with other approval bypass mechanisms."""

    def test_container_env_still_auto_approves(self, monkeypatch):
        """Docker/sandbox environments bypass approvals regardless of cron_mode."""
        monkeypatch.setenv("HERMES_CRON_SESSION", "1")
        monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
        monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
        monkeypatch.delenv("HERMES_YOLO_MODE", raising=False)

        from unittest.mock import patch as mock_patch
        with mock_patch("tools.approval._get_cron_approval_mode", return_value="deny"):
            result = check_dangerous_command("rm -rf /", "docker")
            assert result["approved"]

    def test_yolo_overrides_cron_deny(self, monkeypatch):
        """--yolo still bypasses cron_mode=deny for dangerous (non-hardline) commands."""
        monkeypatch.setenv("HERMES_CRON_SESSION", "1")
        monkeypatch.setenv("HERMES_YOLO_MODE", "1")
        monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
        monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)

        from unittest.mock import patch as mock_patch
        with mock_patch("tools.approval._get_cron_approval_mode", return_value="deny"):
            # Use a dangerous-but-not-hardline command — `rm -rf /` is now
            # hardline-blocked regardless of yolo (see test_hardline_blocklist.py).
            result = check_dangerous_command("rm -rf /tmp/stuff", "local")
            assert result["approved"]

    def test_non_cron_non_interactive_still_auto_approves(self, monkeypatch):
        """Non-cron, non-interactive sessions (e.g. scripted usage) still auto-approve."""
        monkeypatch.delenv("HERMES_CRON_SESSION", raising=False)
        monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
        monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
        monkeypatch.delenv("HERMES_YOLO_MODE", raising=False)

        result = check_dangerous_command("rm -rf /tmp/stuff", "local")
        assert result["approved"]


class TestRuntimePackageInstallApproval:
    def test_runtime_package_install_parser_accepts_simple_apt_chains(self):
        assert is_runtime_package_install_command(
            "sudo -n apt-get update && "
            "sudo -n DEBIAN_FRONTEND=noninteractive apt-get install -y "
            "--no-install-recommends ffmpeg yt-dlp"
        )
        assert is_runtime_package_install_command(
            "bash -lc 'sudo -n apt-get update && sudo -n apt-get install -y tesseract-ocr'"
        )
        assert extract_runtime_apt_install_packages(
            "sudo -n apt-get update && sudo -n apt-get install -y ffmpeg yt-dlp"
        ) == ["ffmpeg", "yt-dlp"]

    def test_runtime_package_install_parser_rejects_extra_shell_work(self):
        assert not is_runtime_package_install_command("sudo -n apt-get install -y ffmpeg && rm -rf /tmp/stuff")
        assert not is_runtime_package_install_command("sudo -n apt-get purge -y ffmpeg")
        assert not is_runtime_package_install_command("sudo -n apt-get install -y ./local.deb")
        assert extract_runtime_apt_install_packages("sudo -n apt-get install -y ./local.deb") == []

    def test_combined_guard_allows_trusted_container_apt_without_prompt(self, monkeypatch):
        monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
        monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
        monkeypatch.delenv("HERMES_EXEC_ASK", raising=False)
        monkeypatch.delenv("HERMES_YOLO_MODE", raising=False)

        result = check_all_command_guards(
            "bash -lc 'sudo -n apt-get update && sudo -n apt-get install -y tesseract-ocr'",
            "local",
        )

        assert result["approved"]
        assert result["runtime_package_install"] is True

    def test_runtime_apt_bypass_can_be_disabled(self, monkeypatch):
        monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
        monkeypatch.setenv("HERMES_ALLOW_RUNTIME_APT", "0")
        monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
        monkeypatch.delenv("HERMES_EXEC_ASK", raising=False)
        monkeypatch.delenv("HERMES_YOLO_MODE", raising=False)

        result = check_all_command_guards(
            "bash -lc 'sudo -n apt-get update && sudo -n apt-get install -y tesseract-ocr'",
            "local",
        )

        assert not result["approved"]
