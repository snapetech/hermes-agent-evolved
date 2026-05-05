from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent
from gateway.session import SessionEntry, SessionSource, build_session_key


def _make_source() -> SessionSource:
    return SessionSource(
        platform=Platform.TELEGRAM,
        user_id="u1",
        chat_id="c1",
        user_name="tester",
        chat_type="dm",
    )


def _make_event(text: str) -> MessageEvent:
    return MessageEvent(text=text, source=_make_source(), message_id="m1")


def _make_runner():
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={Platform.TELEGRAM: PlatformConfig(enabled=True, token="tok")}
    )
    adapter = MagicMock()
    adapter.send = AsyncMock()
    runner.adapters = {Platform.TELEGRAM: adapter}
    runner._voice_mode = {}
    runner.hooks = SimpleNamespace(emit=AsyncMock(), loaded_hooks=False)
    runner._session_model_overrides = {}
    runner._session_modes = {}
    runner._pending_messages = {}
    runner._pending_approvals = {}
    runner._running_agents = {}
    runner._session_db = MagicMock()
    runner._session_db.get_session_title.return_value = None
    runner._agent_cache = {}
    runner._agent_cache_lock = None
    runner.session_store = MagicMock()
    session_key = build_session_key(_make_source())
    session_entry = SessionEntry(
        session_key=session_key,
        session_id="sess-1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
        total_tokens=0,
    )
    runner.session_store.get_or_create_session.return_value = session_entry
    runner._evict_cached_agent = lambda _sk: None
    return runner


@pytest.mark.asyncio
async def test_mode_command_lists_modes():
    runner = _make_runner()
    result = await runner._handle_mode_command(_make_event("/mode"))
    assert "Current mode" in result
    assert "`code`" in result
    assert "`debug`" in result


@pytest.mark.asyncio
async def test_mode_command_sets_session_mode():
    runner = _make_runner()
    result = await runner._handle_mode_command(_make_event("/mode ask"))
    session_key = build_session_key(_make_source())
    assert runner._session_modes[session_key] == "ask"
    assert "Mode set to `ask`" in result


@pytest.mark.asyncio
async def test_status_command_includes_mode():
    runner = _make_runner()
    session_key = build_session_key(_make_source())
    runner._session_modes[session_key] = "review"
    result = await runner._handle_status_command(_make_event("/status"))
    assert "**Mode:** `review`" in result

