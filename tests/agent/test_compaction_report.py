"""Tests for compaction-report helpers."""

import json

from agent.compaction_report import (
    build_live_compaction_data,
    format_compaction_report,
    load_session_compaction_data,
    parse_compaction_command_args,
    resolve_session_reference,
)


def test_load_session_compaction_data_reads_session_log(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    sessions = home / "sessions"
    sessions.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))

    session_id = "sess123"
    payload = {
        "compaction_metrics": {"event_count": 1, "by_source": {"admission_proxy": 1}},
        "compaction_events": [{"source": "admission_proxy", "trigger": "proxy_context_overflow_retry"}],
    }
    (sessions / f"session_{session_id}.json").write_text(json.dumps(payload), encoding="utf-8")

    data = load_session_compaction_data(session_id)

    assert data is not None
    assert data["compaction_metrics"]["event_count"] == 1
    assert data["compaction_events"][0]["trigger"] == "proxy_context_overflow_retry"


def test_build_live_compaction_data_uses_agent_metrics():
    class Agent:
        session_id = "sess-live"
        session_log_file = "/tmp/session_sess-live.json"
        _compaction_events = [{"source": "local_policy", "trigger": "preflight_recent_activity_headroom"}]

        def _build_compaction_metrics(self):
            return {
                "event_count": 1,
                "by_source": {"local_policy": 1},
                "by_trigger": {"preflight_recent_activity_headroom": 1},
            }

    data = build_live_compaction_data(Agent())

    assert data["session_id"] == "sess-live"
    assert data["compaction_metrics"]["by_source"]["local_policy"] == 1


def test_format_compaction_report_includes_recent_events():
    text = format_compaction_report(
        {
            "session_id": "sess123",
            "compaction_metrics": {
                "event_count": 2,
                "by_source": {"admission_proxy": 1, "local_policy": 1},
                "by_trigger": {
                    "proxy_context_overflow_retry": 1,
                    "preflight_recent_activity_headroom": 1,
                },
                "proxy_overflow_compactions": 1,
            },
            "compaction_events": [
                {
                    "source": "admission_proxy",
                    "trigger": "proxy_context_overflow_retry",
                    "estimated_input_tokens": 91000,
                    "max_input_tokens": 64000,
                    "timestamp": "2026-04-20T12:00:00",
                },
                {
                    "source": "local_policy",
                    "trigger": "preflight_recent_activity_headroom",
                    "pre_message_count": 42,
                    "post_message_count": 18,
                    "approx_tokens_before": 58000,
                    "approx_tokens_after": 22000,
                    "compression_attempt": 1,
                    "timestamp": "2026-04-20T12:05:00",
                },
            ],
        },
        limit=2,
        markdown=False,
    )

    assert "Compaction Report" in text
    assert "admission_proxy=1, local_policy=1" in text
    assert "91,000>64,000" in text
    assert "msgs 42->18" in text


def test_parse_compaction_command_args_supports_session_selector():
    limit, session_ref, error = parse_compaction_command_args("10 --session my-session")
    assert error is None
    assert limit == 10
    assert session_ref == "my-session"


def test_resolve_session_reference_uses_title_lookup():
    class FakeDB:
        def get_session(self, _session_id):
            return None

        def get_session_by_title(self, title):
            if title == "deploy debug":
                return {"id": "20260420_abc123"}
            return None

    resolved = resolve_session_reference(FakeDB(), "deploy debug", current_session_id="current")
    assert resolved == "20260420_abc123"
