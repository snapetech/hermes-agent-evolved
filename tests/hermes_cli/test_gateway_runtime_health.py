from hermes_cli.gateway import _runtime_health_lines


def test_runtime_health_lines_include_fatal_platform_and_startup_reason(monkeypatch):
    monkeypatch.setattr(
        "gateway.status.read_runtime_status",
        lambda: {
            "gateway_state": "startup_failed",
            "exit_reason": "telegram conflict",
            "platforms": {
                "telegram": {
                    "state": "fatal",
                    "error_message": "another poller is active",
                }
            },
        },
    )

    lines = _runtime_health_lines()

    assert "⚠ telegram: another poller is active" in lines
    assert "⚠ Last startup issue: telegram conflict" in lines


def test_runtime_health_lines_show_pending_restart_and_last_reload(monkeypatch):
    monkeypatch.setattr(
        "gateway.status.read_runtime_status",
        lambda: {
            "gateway_state": "running",
            "restart_requested": False,
            "auto_restart_pending": True,
            "auto_restart_reason": "repo Python sources changed on disk",
            "last_runtime_reload_at": "2026-04-23T18:10:00+00:00",
            "platforms": {},
        },
    )

    lines = _runtime_health_lines()

    assert "⏳ Gateway restart pending when idle (repo Python sources changed on disk)" in lines
    assert "↻ Last runtime reload: 2026-04-23T18:10:00+00:00" in lines
