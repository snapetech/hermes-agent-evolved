"""Regression tests for issue #11016 split-brain session locks."""

import asyncio
from unittest.mock import MagicMock

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session import SessionSource, build_session_key


class _StubAdapter(BasePlatformAdapter):
    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def send(self, chat_id, text, **kwargs):
        return None

    async def get_chat_info(self, chat_id):
        return {}


def _make_adapter():
    config = PlatformConfig(enabled=True, token="test-token")
    adapter = _StubAdapter(config, Platform.TELEGRAM)
    adapter.sent_responses = []

    async def _mock_send_retry(chat_id, content, **kwargs):
        adapter.sent_responses.append(content)

    adapter._send_with_retry = _mock_send_retry
    return adapter


def _make_event(text="hello", chat_id="12345"):
    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id=chat_id,
        chat_type="dm",
    )
    return MessageEvent(text=text, message_type=MessageType.TEXT, source=source)


def _session_key(chat_id="12345"):
    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id=chat_id,
        chat_type="dm",
    )
    return build_session_key(source)


def _make_runner():
    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={Platform.TELEGRAM: PlatformConfig(enabled=True, token="***")}
    )
    runner.adapters = {}
    runner._running_agents = {}
    runner._running_agents_ts = {}
    runner._session_run_generation = {}
    runner._pending_messages = {}
    runner._draining = False
    runner._update_runtime_status = MagicMock()
    return runner


class TestAdapterSessionCancellation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("command_text", ["/stop", "/new", "/reset"])
    async def test_command_cancels_active_task_and_unblocks_follow_up(self, command_text):
        adapter = _make_adapter()
        sk = _session_key()
        processing_started = asyncio.Event()
        processing_cancelled = asyncio.Event()
        blocked_first_message = True

        async def _handler(event):
            nonlocal blocked_first_message
            cmd = event.get_command()
            if cmd in {"stop", "new", "reset", "model"}:
                return f"handled:{cmd}"

            if blocked_first_message:
                blocked_first_message = False
                processing_started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    processing_cancelled.set()
                    raise
            return f"handled:text:{event.text}"

        adapter._message_handler = _handler

        await adapter.handle_message(_make_event("hello world"))
        await processing_started.wait()
        await asyncio.sleep(0)

        assert sk in adapter._active_sessions
        assert sk in adapter._session_tasks

        await adapter.handle_message(_make_event(command_text))

        assert processing_cancelled.is_set()
        assert sk not in adapter._active_sessions
        assert sk not in adapter._pending_messages
        assert sk not in adapter._session_tasks
        assert any(f"handled:{command_text.lstrip('/')}" in r for r in adapter.sent_responses)

        await adapter.handle_message(_make_event("/model xiaomi/mimo-v2-pro --provider nous"))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert any("handled:model" in r for r in adapter.sent_responses)
        assert sk not in adapter._pending_messages

    @pytest.mark.asyncio
    async def test_new_keeps_guard_until_command_finishes_then_runs_follow_up(self):
        adapter = _make_adapter()
        sk = _session_key()
        processing_started = asyncio.Event()
        command_started = asyncio.Event()
        allow_command_finish = asyncio.Event()
        follow_up_processed = asyncio.Event()
        call_order = []

        async def _handler(event):
            cmd = event.get_command()
            if cmd == "new":
                call_order.append("command:start")
                command_started.set()
                await allow_command_finish.wait()
                call_order.append("command:end")
                return "handled:new"

            if event.text == "hello world":
                processing_started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    call_order.append("original:cancelled")
                    raise

            if event.text == "after reset":
                call_order.append("followup:processed")
                follow_up_processed.set()
            return f"handled:text:{event.text}"

        adapter._message_handler = _handler

        await adapter.handle_message(_make_event("hello world"))
        await processing_started.wait()

        command_task = asyncio.create_task(adapter.handle_message(_make_event("/new")))
        await command_started.wait()
        await asyncio.sleep(0)

        assert sk in adapter._active_sessions

        await adapter.handle_message(_make_event("after reset"))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert sk in adapter._active_sessions
        assert sk in adapter._pending_messages
        assert not follow_up_processed.is_set()
        assert "original:cancelled" not in call_order

        allow_command_finish.set()
        await command_task
        await asyncio.wait_for(follow_up_processed.wait(), timeout=1.0)

        assert any("handled:new" in r for r in adapter.sent_responses)
        assert call_order.index("command:end") < call_order.index("original:cancelled")
        assert call_order.index("original:cancelled") < call_order.index("followup:processed")
        assert sk not in adapter._pending_messages


class TestStaleSessionLockSelfHeal:
    @pytest.mark.asyncio
    async def test_stale_lock_with_done_task_is_healed_on_next_message(self):
        adapter = _make_adapter()
        sk = _session_key()

        async def _done():
            return None

        done_task = asyncio.create_task(_done())
        await done_task
        adapter._active_sessions[sk] = asyncio.Event()
        adapter._session_tasks[sk] = done_task

        assert adapter._session_task_is_stale(sk)

        async def _handler(event):
            return f"handled:{event.get_command() or 'text'}"

        adapter._message_handler = _handler

        await adapter.handle_message(_make_event("hello"))
        for _ in range(5):
            await asyncio.sleep(0)

        assert any("handled:text" in r for r in adapter.sent_responses)

    def test_no_owner_task_is_not_treated_as_stale(self):
        adapter = _make_adapter()
        sk = _session_key()
        adapter._active_sessions[sk] = asyncio.Event()
        assert adapter._session_task_is_stale(sk) is False
        assert adapter._heal_stale_session_lock(sk) is False

    def test_live_owner_task_is_not_stale(self):
        adapter = _make_adapter()
        sk = _session_key()

        fake_task = MagicMock()
        fake_task.done.return_value = False
        adapter._active_sessions[sk] = asyncio.Event()
        adapter._session_tasks[sk] = fake_task

        assert adapter._session_task_is_stale(sk) is False
        assert adapter._heal_stale_session_lock(sk) is False
        assert sk in adapter._active_sessions
        assert sk in adapter._session_tasks


class TestRunnerSessionGenerationGuard:
    def test_release_without_generation_behaves_as_before(self):
        runner = _make_runner()
        sk = "agent:main:telegram:dm:12345"
        runner._running_agents[sk] = "agent"
        runner._running_agents_ts[sk] = 1.0
        assert runner._release_running_agent_state(sk) is True
        assert sk not in runner._running_agents
        assert sk not in runner._running_agents_ts

    def test_release_with_current_generation_clears_slot(self):
        runner = _make_runner()
        sk = "agent:main:telegram:dm:12345"
        gen = runner._begin_session_run_generation(sk)
        runner._running_agents[sk] = "agent"
        runner._running_agents_ts[sk] = 1.0

        assert runner._release_running_agent_state(sk, run_generation=gen) is True
        assert sk not in runner._running_agents

    def test_release_with_stale_generation_blocks(self):
        runner = _make_runner()
        sk = "agent:main:telegram:dm:12345"
        stale_gen = runner._begin_session_run_generation(sk)
        runner._invalidate_session_run_generation(sk, reason="stop")
        runner._running_agents[sk] = "fresh_agent"
        runner._running_agents_ts[sk] = 2.0

        released = runner._release_running_agent_state(sk, run_generation=stale_gen)

        assert released is False
        assert runner._running_agents[sk] == "fresh_agent"
        assert runner._running_agents_ts[sk] == 2.0

    def test_is_session_run_current_tracks_bumps(self):
        runner = _make_runner()
        sk = "agent:main:telegram:dm:12345"
        gen1 = runner._begin_session_run_generation(sk)
        assert runner._is_session_run_current(sk, gen1) is True

        runner._invalidate_session_run_generation(sk, reason="test")
        assert runner._is_session_run_current(sk, gen1) is False

        gen2 = runner._begin_session_run_generation(sk)
        assert gen2 > gen1
        assert runner._is_session_run_current(sk, gen2) is True


class TestOldTaskCannotClobberNewerGuard:
    def test_release_session_guard_matches_on_event_identity(self):
        adapter = _make_adapter()
        sk = _session_key()

        old_guard = asyncio.Event()
        new_guard = asyncio.Event()
        adapter._active_sessions[sk] = new_guard

        adapter._release_session_guard(sk, guard=old_guard)

        assert adapter._active_sessions.get(sk) is new_guard

        adapter._release_session_guard(sk, guard=new_guard)
        assert sk not in adapter._active_sessions

    def test_release_session_guard_without_guard_releases_unconditionally(self):
        adapter = _make_adapter()
        sk = _session_key()
        adapter._active_sessions[sk] = asyncio.Event()
        adapter._release_session_guard(sk)
        assert sk not in adapter._active_sessions
