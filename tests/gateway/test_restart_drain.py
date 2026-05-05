import asyncio
import shutil
import subprocess
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

import gateway.run as gateway_run
from agent.queue_aware_routing import RouteSelection
from gateway.platforms.base import MessageEvent, MessageType
from gateway.restart import DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT
from gateway.session import SessionEntry, build_session_key
from tests.gateway.restart_test_helpers import make_restart_runner, make_restart_source


@pytest.mark.asyncio
async def test_restart_command_while_busy_requests_drain_without_interrupt(monkeypatch):
    # Ensure INVOCATION_ID is NOT set — systemd sets this in service mode,
    # which changes the restart call signature.
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    runner, _adapter = make_restart_runner()
    runner.request_restart = MagicMock(return_value=True)
    event = MessageEvent(
        text="/restart",
        message_type=MessageType.TEXT,
        source=make_restart_source(),
        message_id="m1",
    )
    session_key = build_session_key(event.source)
    running_agent = MagicMock()
    runner._running_agents[session_key] = running_agent

    result = await runner._handle_message(event)

    assert result == "⏳ Draining 1 active agent(s) before restart..."
    running_agent.interrupt.assert_not_called()
    runner.request_restart.assert_called_once_with(detached=True, via_service=False)


@pytest.mark.asyncio
async def test_restart_idle_command_arms_deferred_restart_without_interrupt(monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    runner, _adapter = make_restart_runner()
    runner.request_restart = MagicMock(return_value=True)
    event = MessageEvent(
        text="/restart idle",
        message_type=MessageType.TEXT,
        source=make_restart_source(),
        message_id="m1b",
    )
    session_key = build_session_key(event.source)
    running_agent = MagicMock()
    runner._running_agents[session_key] = running_agent
    runner._running_turns[session_key] = {"started_at": time.time()}

    result = await runner._handle_message(event)

    assert "Restart armed." in result
    assert "idle boundary" in result
    running_agent.interrupt.assert_not_called()
    runner.request_restart.assert_not_called()
    assert runner._pending_auto_restart_reason == "manual restart requested by user at next idle boundary"


@pytest.mark.asyncio
async def test_drain_queue_mode_queues_follow_up_without_interrupt():
    runner, adapter = make_restart_runner()
    runner._draining = True
    runner._restart_requested = True
    runner._busy_input_mode = "queue"

    event = MessageEvent(
        text="follow up",
        message_type=MessageType.TEXT,
        source=make_restart_source(),
        message_id="m2",
    )
    session_key = build_session_key(event.source)
    adapter._active_sessions[session_key] = asyncio.Event()

    await adapter.handle_message(event)

    assert session_key in adapter._pending_messages
    assert adapter._pending_messages[session_key].text == "follow up"
    assert not adapter._active_sessions[session_key].is_set()
    assert any("queued for the next turn" in message for message in adapter.sent)


@pytest.mark.asyncio
async def test_draining_rejects_new_session_messages():
    runner, _adapter = make_restart_runner()
    runner._draining = True
    runner._restart_requested = True

    event = MessageEvent(
        text="hello",
        message_type=MessageType.TEXT,
        source=make_restart_source("fresh"),
        message_id="m3",
    )

    result = await runner._handle_message(event)

    assert result == "⏳ Gateway is restarting and is not accepting new work right now."


def test_load_busy_input_mode_prefers_env_then_config_then_default(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.delenv("HERMES_GATEWAY_BUSY_INPUT_MODE", raising=False)

    assert gateway_run.GatewayRunner._load_busy_input_mode() == "interrupt"

    (tmp_path / "config.yaml").write_text(
        "display:\n  busy_input_mode: queue\n", encoding="utf-8"
    )
    assert gateway_run.GatewayRunner._load_busy_input_mode() == "queue"

    (tmp_path / "config.yaml").write_text(
        "display:\n  busy_input_mode: steer\n", encoding="utf-8"
    )
    assert gateway_run.GatewayRunner._load_busy_input_mode() == "steer"

    monkeypatch.setenv("HERMES_GATEWAY_BUSY_INPUT_MODE", "interrupt")
    assert gateway_run.GatewayRunner._load_busy_input_mode() == "interrupt"

    monkeypatch.setenv("HERMES_GATEWAY_BUSY_INPUT_MODE", "steer")
    assert gateway_run.GatewayRunner._load_busy_input_mode() == "steer"

    # Unknown values fall through to the safe default
    monkeypatch.setenv("HERMES_GATEWAY_BUSY_INPUT_MODE", "bogus")
    assert gateway_run.GatewayRunner._load_busy_input_mode() == "interrupt"


def test_load_restart_drain_timeout_prefers_env_then_config_then_default(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.delenv("HERMES_RESTART_DRAIN_TIMEOUT", raising=False)

    assert (
        gateway_run.GatewayRunner._load_restart_drain_timeout()
        == DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT
    )

    (tmp_path / "config.yaml").write_text(
        "agent:\n  restart_drain_timeout: 12\n", encoding="utf-8"
    )
    assert gateway_run.GatewayRunner._load_restart_drain_timeout() == 12.0

    monkeypatch.setenv("HERMES_RESTART_DRAIN_TIMEOUT", "7")
    assert gateway_run.GatewayRunner._load_restart_drain_timeout() == 7.0

    monkeypatch.setenv("HERMES_RESTART_DRAIN_TIMEOUT", "invalid")
    assert (
        gateway_run.GatewayRunner._load_restart_drain_timeout()
        == DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT
    )
    assert "Invalid restart_drain_timeout" in caplog.text


@pytest.mark.asyncio
async def test_request_restart_is_idempotent():
    runner, _adapter = make_restart_runner()
    runner.stop = AsyncMock()

    assert runner.request_restart(detached=True, via_service=False) is True
    first_task = next(iter(runner._background_tasks))
    assert runner.request_restart(detached=True, via_service=False) is False

    await first_task

    runner.stop.assert_awaited_once_with(
        restart=True, detached_restart=True, service_restart=False
    )


@pytest.mark.asyncio
async def test_schedule_auto_code_restart_emits_pending_hook(monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    runner, _adapter = make_restart_runner()
    runner._running_turns["session-1"] = {"started_at": time.time()}
    runner.request_restart = MagicMock(return_value=True)

    runner._schedule_auto_code_restart("repo Python sources changed on disk")
    await asyncio.gather(*list(runner._background_tasks))

    runner.hooks.emit.assert_any_await(
        "gateway:restart_pending",
        {
            "reason": "repo Python sources changed on disk",
            "active_agents": 0,
            "gateway_state": "running",
        },
    )


@pytest.mark.asyncio
async def test_apply_runtime_reload_emits_runtime_reload_hook(monkeypatch):
    runner, _adapter = make_restart_runner()
    monkeypatch.setattr("gateway.run.load_gateway_config", lambda: runner.config)
    monkeypatch.setattr("hermes_cli.config.reload_env", lambda: 2)
    monkeypatch.setattr("agent.skill_commands.scan_skill_commands", lambda: {"alpha": "beta"})
    monkeypatch.setattr("agent.prompt_builder.clear_skills_system_prompt_cache", lambda: None)
    monkeypatch.setattr(
        "tools.skills_sync.sync_skills",
        lambda quiet=True: {"copied": ["a"], "updated": ["b"], "user_modified": ["c"]},
    )
    runner._load_prefill_messages = lambda: []
    runner._load_ephemeral_system_prompt = lambda: None
    runner._load_reasoning_config = lambda: None
    runner._load_service_tier = lambda: None
    runner._load_show_reasoning = lambda: False
    runner._load_busy_input_mode = lambda: "interrupt"
    runner._load_restart_drain_timeout = lambda: 60.0
    runner._load_provider_routing = lambda: {}
    runner._load_fallback_model = lambda: None
    runner._load_adaptive_fallback_routing = lambda: False
    runner._load_smart_model_routing = lambda: False
    runner._load_warm_standby_enabled = lambda: False
    runner._load_gateway_worktree_config = lambda: {}

    stats = await runner._apply_runtime_reload()
    await asyncio.gather(*list(runner._background_tasks))

    assert stats == {
        "env_count": 2,
        "skill_command_count": 1,
        "copied_count": 1,
        "updated_count": 1,
        "user_modified_count": 1,
    }


def test_extract_validation_request_context_counts_failures():
    messages = [
        {
            "role": "tool",
            "content": '{"success": true, "validation": {"status": "error", "lint": {"status": "ok"}, "formatter": {"status": "error"}}}',
        },
        {
            "role": "tool",
            "content": '{"success": true, "validation": {"a.py": {"status": "ok", "lint": {"status": "error"}, "formatter": {"status": "ok"}}}}',
        },
    ]

    context = gateway_run._extract_validation_request_context(messages)

    assert context == {
        "validator_escalation": True,
        "validation_failed": True,
        "validated_files": 2,
        "validation_failure_count": 1,
        "formatter_failure_count": 1,
        "lint_failure_count": 1,
        "captured_at": pytest.approx(context["captured_at"]),
    }


def test_should_apply_validation_request_context_only_for_repair_followups():
    context = {
        "validator_escalation": True,
        "validation_failure_count": 1,
        "captured_at": 100.0,
    }

    assert gateway_run._should_apply_validation_request_context(
        "please retry that patch",
        context,
        now=150.0,
    )
    assert gateway_run._should_apply_validation_request_context(
        "fix it",
        context,
        now=150.0,
    )
    assert not gateway_run._should_apply_validation_request_context(
        "what's the status of the cluster?",
        context,
        now=150.0,
    )
    assert not gateway_run._should_apply_validation_request_context(
        "tell me about qwen 3.6 quality",
        context,
        now=150.0,
    )


def test_should_apply_validation_request_context_expires():
    context = {
        "validator_escalation": True,
        "validation_failure_count": 1,
        "captured_at": 100.0,
    }

    assert not gateway_run._should_apply_validation_request_context(
        "retry that patch",
        context,
        now=2000.0,
    )


def test_should_apply_validation_request_context_honors_custom_policy():
    context = {
        "validator_escalation": True,
        "validation_failure_count": 1,
        "captured_at": 100.0,
    }
    policy = {
        "enabled": True,
        "ttl_seconds": 30,
        "repair_keywords": ["repair-now"],
        "short_followup_keywords": ["again"],
        "short_followup_max_words": 2,
    }

    assert gateway_run._should_apply_validation_request_context(
        "repair-now",
        context,
        now=110.0,
        policy=policy,
    )
    assert not gateway_run._should_apply_validation_request_context(
        "retry that patch",
        context,
        now=110.0,
        policy=policy,
    )
    assert not gateway_run._should_apply_validation_request_context(
        "again please now",
        context,
        now=110.0,
        policy=policy,
    )
    assert not gateway_run._should_apply_validation_request_context(
        "repair-now",
        context,
        now=140.0,
        policy=policy,
    )


@pytest.mark.asyncio
async def test_resolve_turn_agent_route_consumes_session_validation_context():
    runner, _adapter = make_restart_runner()
    runner._session_validation_contexts = {
        "sess-1": {
            "validator_escalation": True,
            "validation_failure_count": 1,
            "formatter_failure_count": 1,
        }
    }
    runner._resolve_turn_agent_route = gateway_run.GatewayRunner._resolve_turn_agent_route.__get__(
        runner, gateway_run.GatewayRunner
    )
    runner._normalize_fallback_chain_value = gateway_run.GatewayRunner._normalize_fallback_chain_value
    runner._resolve_turn_agent_config = lambda user_message, model, runtime_kwargs: {
        "model": model,
        "runtime": dict(runtime_kwargs),
        "signature": (
            model,
            runtime_kwargs.get("provider"),
            runtime_kwargs.get("base_url"),
            runtime_kwargs.get("api_mode"),
            runtime_kwargs.get("command"),
            tuple(runtime_kwargs.get("args") or []),
        ),
    }
    runner._build_effective_fallback_chain = lambda _model, _runtime: []
    runner._resolve_managed_route_runtime = lambda selection: (dict(selection.runtime), selection.model)
    runner._flush_route_manager_events = lambda: None

    fake_manager = MagicMock()
    fake_manager.enabled = True
    fake_manager.acquire_route = AsyncMock(
        return_value=RouteSelection(
            route_id="validator-route",
            model="validator:model",
            runtime={
                "provider": "custom",
                "base_url": "http://127.0.0.1:9000/v1",
                "api_mode": "chat_completions",
                "api_key": "no-key-required",
                "requested_provider": "custom",
                "resolve_runtime": False,
                "command": None,
                "args": [],
                "credential_pool": None,
            },
            fallback_chain=[],
            request_class="validator",
            routing_reason="validation_escalation",
        )
    )
    runner._route_manager = fake_manager

    route = await runner._resolve_turn_agent_route(
        "please retry the patch",
        "baseline:model",
        {
            "provider": "custom",
            "base_url": "http://127.0.0.1:8001/v1",
            "api_mode": "chat_completions",
        },
        session_key="sess-1",
    )

    fake_manager.acquire_route.assert_awaited_once()
    kwargs = fake_manager.acquire_route.await_args.kwargs
    assert kwargs["request_context"]["validation_failure_count"] == 1
    assert route["request_class"] == "validator"
    assert route["validation_request_context"]["formatter_failure_count"] == 1
    assert runner._session_validation_contexts == {}


@pytest.mark.asyncio
async def test_resolve_turn_agent_route_suppresses_validation_context_for_unrelated_turn():
    runner, _adapter = make_restart_runner()
    runner._session_validation_contexts = {
        "sess-1": {
            "validator_escalation": True,
            "validation_failure_count": 1,
            "formatter_failure_count": 1,
            "captured_at": time.time(),
        }
    }
    runner._resolve_turn_agent_route = gateway_run.GatewayRunner._resolve_turn_agent_route.__get__(
        runner, gateway_run.GatewayRunner
    )
    runner._normalize_fallback_chain_value = gateway_run.GatewayRunner._normalize_fallback_chain_value
    runner._resolve_turn_agent_config = lambda user_message, model, runtime_kwargs: {
        "model": model,
        "runtime": dict(runtime_kwargs),
        "signature": (
            model,
            runtime_kwargs.get("provider"),
            runtime_kwargs.get("base_url"),
            runtime_kwargs.get("api_mode"),
            runtime_kwargs.get("command"),
            tuple(runtime_kwargs.get("args") or []),
        ),
    }
    runner._build_effective_fallback_chain = lambda _model, _runtime: []
    runner._resolve_managed_route_runtime = lambda selection: (dict(selection.runtime), selection.model)
    runner._flush_route_manager_events = lambda: None

    fake_manager = MagicMock()
    fake_manager.enabled = True
    fake_manager.acquire_route = AsyncMock(
        return_value=RouteSelection(
            route_id="general-route",
            model="baseline:model",
            runtime={
                "provider": "custom",
                "base_url": "http://127.0.0.1:8001/v1",
                "api_mode": "chat_completions",
                "api_key": "no-key-required",
                "requested_provider": "custom",
                "resolve_runtime": False,
                "command": None,
                "args": [],
                "credential_pool": None,
            },
            fallback_chain=[],
            request_class="general",
            routing_reason="normal_turn",
        )
    )
    runner._route_manager = fake_manager

    route = await runner._resolve_turn_agent_route(
        "what's the status of the cluster?",
        "baseline:model",
        {
            "provider": "custom",
            "base_url": "http://127.0.0.1:8001/v1",
            "api_mode": "chat_completions",
        },
        session_key="sess-1",
    )

    kwargs = fake_manager.acquire_route.await_args.kwargs
    assert kwargs["request_context"] is None
    assert route["validation_request_context"] is None
    assert "sess-1" in runner._session_validation_contexts


def test_clear_session_boundary_security_state_clears_validation_context():
    runner, _adapter = make_restart_runner()
    runner._session_validation_contexts = {"sess-2": {"validation_failure_count": 1}}

    runner._clear_session_boundary_security_state("sess-2")

    assert runner._session_validation_contexts == {}


def test_auto_code_restart_requests_immediately_when_idle(monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    runner, _adapter = make_restart_runner()
    runner.request_restart = MagicMock(return_value=True)

    runner._schedule_auto_code_restart("repo Python sources changed on disk")

    runner.request_restart.assert_called_once_with(detached=True, via_service=False)
    assert runner._pending_auto_restart_reason is None


def test_auto_code_restart_defers_until_gateway_is_idle(monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    runner, _adapter = make_restart_runner()
    runner.request_restart = MagicMock(return_value=True)
    runner._running_turns["session-1"] = {"started_at": time.time()}

    runner._schedule_auto_code_restart("repo Python sources changed on disk")

    runner.request_restart.assert_not_called()
    assert runner._pending_auto_restart_reason == "repo Python sources changed on disk"

    runner._running_turns.clear()
    assert runner._maybe_request_pending_auto_restart() is True
    runner.request_restart.assert_called_once_with(detached=True, via_service=False)
    assert runner._pending_auto_restart_reason is None


def test_auto_code_restart_uses_service_restart_when_under_systemd(monkeypatch):
    monkeypatch.setenv("INVOCATION_ID", "svc-1")
    runner, _adapter = make_restart_runner()
    runner.request_restart = MagicMock(return_value=True)

    runner._schedule_auto_code_restart("repo Python sources changed on disk")

    runner.request_restart.assert_called_once_with(detached=False, via_service=True)
    assert runner._pending_auto_restart_reason is None


@pytest.mark.asyncio
async def test_restart_idle_restarts_immediately_when_gateway_is_idle(monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    runner, _adapter = make_restart_runner()
    runner.request_restart = MagicMock(return_value=True)

    event = MessageEvent(
        text="/restart idle",
        message_type=MessageType.TEXT,
        source=make_restart_source(),
        message_id="m-idle",
    )

    result = await runner._handle_restart_command(event)

    assert result == "♻ Restart armed. Gateway is idle, restarting now."
    runner.request_restart.assert_called_once_with(detached=True, via_service=False)
    assert runner._pending_auto_restart_reason is None


@pytest.mark.asyncio
async def test_launch_detached_restart_command_uses_setsid(monkeypatch):
    runner, _adapter = make_restart_runner()
    popen_calls = []

    monkeypatch.setattr(gateway_run, "_resolve_hermes_bin", lambda: ["/usr/bin/hermes"])
    monkeypatch.setattr(gateway_run.os, "getpid", lambda: 321)
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/setsid" if cmd == "setsid" else None)

    def fake_popen(cmd, **kwargs):
        popen_calls.append((cmd, kwargs))
        return MagicMock()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    await runner._launch_detached_restart_command()

    assert len(popen_calls) == 1
    cmd, kwargs = popen_calls[0]
    assert cmd[:2] == ["/usr/bin/setsid", "bash"]
    assert "gateway restart" in cmd[-1]
    assert "kill -0 321" in cmd[-1]
    assert kwargs["start_new_session"] is True
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL


# ── Shutdown notification tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_shutdown_notification_sent_to_active_sessions():
    """Active sessions receive a notification when the gateway starts shutting down."""
    runner, adapter = make_restart_runner()
    source = make_restart_source(chat_id="999", chat_type="dm")
    session_key = f"agent:main:telegram:dm:999"
    runner._running_agents[session_key] = MagicMock()

    await runner._notify_active_sessions_of_shutdown()

    assert len(adapter.sent) == 1
    assert "shutting down" in adapter.sent[0]
    assert "interrupted" in adapter.sent[0]


@pytest.mark.asyncio
async def test_shutdown_notification_says_restarting_when_restart_requested():
    """When _restart_requested is True, the message says 'restarting' and mentions /retry."""
    runner, adapter = make_restart_runner()
    runner._restart_requested = True
    session_key = "agent:main:telegram:dm:999"
    runner._running_agents[session_key] = MagicMock()

    await runner._notify_active_sessions_of_shutdown()

    assert len(adapter.sent) == 1
    assert "restarting" in adapter.sent[0]
    assert "resume" in adapter.sent[0]


@pytest.mark.asyncio
async def test_shutdown_notification_deduplicates_per_chat():
    """Multiple sessions in the same chat only get one notification."""
    runner, adapter = make_restart_runner()
    # Two sessions (different users) in the same chat
    runner._running_agents["agent:main:telegram:group:chat1:u1"] = MagicMock()
    runner._running_agents["agent:main:telegram:group:chat1:u2"] = MagicMock()

    await runner._notify_active_sessions_of_shutdown()

    assert len(adapter.sent) == 1


@pytest.mark.asyncio
async def test_shutdown_notification_skipped_when_no_active_agents():
    """No notification is sent when there are no active agents."""
    runner, adapter = make_restart_runner()

    await runner._notify_active_sessions_of_shutdown()

    assert len(adapter.sent) == 0


@pytest.mark.asyncio
async def test_shutdown_notification_ignores_pending_sentinels():
    """Pending sentinels (not-yet-started agents) don't trigger notifications."""
    from gateway.run import _AGENT_PENDING_SENTINEL

    runner, adapter = make_restart_runner()
    runner._running_agents["agent:main:telegram:dm:999"] = _AGENT_PENDING_SENTINEL

    await runner._notify_active_sessions_of_shutdown()

    assert len(adapter.sent) == 0


@pytest.mark.asyncio
async def test_shutdown_notification_send_failure_does_not_block():
    """If sending a notification fails, the method still completes."""
    runner, adapter = make_restart_runner()
    adapter.send = AsyncMock(side_effect=Exception("network error"))
    session_key = "agent:main:telegram:dm:999"
    runner._running_agents[session_key] = MagicMock()

    # Should not raise
    await runner._notify_active_sessions_of_shutdown()


@pytest.mark.asyncio
async def test_shutdown_notification_uses_persisted_origin_for_colon_ids():
    """Shutdown notifications should route from persisted origin, not reparsed keys."""
    runner, adapter = make_restart_runner()
    adapter.send = AsyncMock()
    source = make_restart_source(chat_id="!room123:example.org", chat_type="group")
    source.platform = gateway_run.Platform.MATRIX
    session_key = build_session_key(source)
    runner._running_agents[session_key] = MagicMock()
    runner.session_store._entries = {
        session_key: SessionEntry(
            session_key=session_key,
            session_id="sess-1",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            origin=source,
            platform=source.platform,
            chat_type=source.chat_type,
        )
    }
    runner.adapters = {gateway_run.Platform.MATRIX: adapter}

    await runner._notify_active_sessions_of_shutdown()

    assert adapter.send.await_count == 1
    assert adapter.send.await_args.args[0] == "!room123:example.org"
