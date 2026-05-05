from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent.queue_aware_routing import QueueAwareRouteManager


def _config() -> dict:
    return {
        "enabled": True,
        "session_stickiness_seconds": 600,
        "classes": {
            "general": {
                "preferred_tags": ["general", "workhorse"],
                "keywords": [],
                "wait_for_preferred_seconds": 1,
            },
            "strong": {
                "preferred_tags": ["stronger", "quality"],
                "keywords": ["stronger", "review", "benchmark"],
                "wait_for_preferred_seconds": 4,
            },
            "utility": {
                "preferred_tags": ["utility", "json"],
                "keywords": ["json", "extract", "route"],
                "wait_for_preferred_seconds": 2,
            },
            "validator": {
                "preferred_tags": ["validator"],
                "keywords": ["verify"],
                "wait_for_preferred_seconds": 2,
            },
        },
        "routes": [
            {
                "id": "qwen35_7900_primary",
                "model": "qwen3.6-35b-a3b:iq4xs",
                "provider": "custom",
                "base_url": "http://127.0.0.1:8002/v1",
                "priority": 100,
                "tags": ["general", "workhorse", "7900"],
                "failure_domains": ["gpu:7900xt"],
                "initial_latency_seconds": 2.31,
                "max_concurrency": 1,
                "max_queue_depth": 1,
                "fallback_route_ids": ["qwen27_7900_strong", "qwen27_9070_backup", "ministral_a380"],
            },
            {
                "id": "qwen27_7900_strong",
                "model": "qwen3.6-27b:q5ks-7900",
                "provider": "custom",
                "base_url": "http://10.0.0.10:8034/v1",
                "priority": 95,
                "tags": ["stronger", "quality", "utility", "7900"],
                "failure_domains": ["gpu:7900xt", "sidecar:qwen27"],
                "initial_latency_seconds": 6.8,
                "max_concurrency": 1,
                "max_queue_depth": 1,
                "fallback_route_ids": ["qwen27_9070_backup", "qwen35_7900_primary", "ministral_a380"],
            },
            {
                "id": "qwen27_9070_backup",
                "model": "qwen3.6-27b:q5ks-9070",
                "provider": "custom",
                "base_url": "http://10.0.0.10:8035/v1",
                "priority": 80,
                "tags": ["stronger", "quality", "continuity", "9070"],
                "failure_domains": ["gpu:9070xt", "sidecar:qwen27"],
                "initial_latency_seconds": 28.72,
                "max_concurrency": 1,
                "max_queue_depth": 0,
                "fallback_route_ids": ["qwen35_7900_primary", "ministral_a380"],
            },
            {
                "id": "ministral_a380",
                "model": "ministral3-3b-instruct:q4km",
                "provider": "custom",
                "base_url": "http://127.0.0.1:8030/v1",
                "priority": 30,
                "tags": ["utility", "continuity", "a380"],
                "failure_domains": ["gpu:a380"],
                "initial_latency_seconds": 3.25,
                "max_concurrency": 1,
                "max_queue_depth": 0,
            },
        ],
    }


@pytest.mark.asyncio
async def test_general_turn_prefers_primary_workhorse():
    manager = QueueAwareRouteManager(_config())
    route = await manager.acquire_route(
        user_message="what's the status here?",
        primary_model="qwen3.6-35b-a3b:iq4xs",
        primary_runtime={"provider": "custom", "base_url": "http://127.0.0.1:8002/v1", "api_mode": "chat_completions"},
        session_key="s1",
    )
    assert route.route_id == "qwen35_7900_primary"
    assert route.request_class == "general"
    events = manager.pop_recent_events()
    assert events[-1]["event_type"] == "route_selected"
    assert events[-1]["route_id"] == "qwen35_7900_primary"


@pytest.mark.asyncio
async def test_strong_turn_prefers_27b_lane():
    manager = QueueAwareRouteManager(_config())
    route = await manager.acquire_route(
        user_message="please do a stronger review of this architecture",
        primary_model="qwen3.6-35b-a3b:iq4xs",
        primary_runtime={"provider": "custom", "base_url": "http://127.0.0.1:8002/v1", "api_mode": "chat_completions"},
        session_key="s2",
    )
    assert route.route_id == "qwen27_7900_strong"
    assert route.request_class == "strong"
    assert [entry["model"] for entry in route.fallback_chain][:2] == [
        "qwen3.6-27b:q5ks-9070",
        "qwen3.6-35b-a3b:iq4xs",
    ]


@pytest.mark.asyncio
async def test_validation_failures_escalate_to_validator_lane():
    manager = QueueAwareRouteManager(_config())
    route = await manager.acquire_route(
        user_message="please retry the patch",
        primary_model="qwen3.6-35b-a3b:iq4xs",
        primary_runtime={"provider": "custom", "base_url": "http://127.0.0.1:8002/v1", "api_mode": "chat_completions"},
        session_key="s2b",
        request_context={"validation_failure_count": 1, "formatter_failure_count": 1},
    )
    assert route.route_id == "qwen27_7900_strong"
    assert route.request_class == "validator"


@pytest.mark.asyncio
async def test_failover_cools_primary_and_pins_to_effective_backup():
    manager = QueueAwareRouteManager(_config())
    route = await manager.acquire_route(
        user_message="please do a stronger benchmark comparison",
        primary_model="qwen3.6-35b-a3b:iq4xs",
        primary_runtime={"provider": "custom", "base_url": "http://127.0.0.1:8002/v1", "api_mode": "chat_completions"},
        session_key="s3",
    )
    assert route.route_id == "qwen27_7900_strong"

    await manager.release_route(
        route,
        duration_seconds=7.0,
        success=True,
        session_key="s3",
        final_model="qwen3.6-27b:q5ks-9070",
        final_provider="custom",
        final_base_url="http://10.0.0.10:8035/v1",
    )

    snapshot = manager.snapshot()["routes"]
    assert snapshot["qwen27_7900_strong"]["state"] == "healthy"
    assert snapshot["qwen27_7900_strong"]["consecutive_failures"] == 1

    followup = await manager.acquire_route(
        user_message="continue the stronger review",
        primary_model="qwen3.6-35b-a3b:iq4xs",
        primary_runtime={"provider": "custom", "base_url": "http://127.0.0.1:8002/v1", "api_mode": "chat_completions"},
        session_key="s3",
    )
    assert followup.route_id == "qwen27_9070_backup"


@pytest.mark.asyncio
async def test_session_model_override_stays_pinned():
    manager = QueueAwareRouteManager(_config())
    route = await manager.acquire_route(
        user_message="short hello",
        primary_model="qwen3.6-27b:q5ks-9070",
        primary_runtime={"provider": "custom", "base_url": "http://10.0.0.10:8035/v1", "api_mode": "chat_completions"},
        session_key="s4",
        pinned=True,
    )
    assert route.route_id == "qwen27_9070_backup"
    assert route.routing_reason == "session_pinned_model_override"


@pytest.mark.asyncio
async def test_release_records_failover_event():
    manager = QueueAwareRouteManager(_config())
    route = await manager.acquire_route(
        user_message="please do a stronger review of this architecture",
        primary_model="qwen3.6-35b-a3b:iq4xs",
        primary_runtime={"provider": "custom", "base_url": "http://127.0.0.1:8002/v1", "api_mode": "chat_completions"},
        session_key="s5",
    )
    manager.pop_recent_events()

    await manager.release_route(
        route,
        duration_seconds=9.0,
        success=True,
        session_key="s5",
        final_model="qwen3.6-27b:q5ks-9070",
        final_provider="custom",
        final_base_url="http://10.0.0.10:8035/v1",
    )

    events = manager.pop_recent_events()
    assert any(event["event_type"] == "route_released" for event in events)
    released = next(event for event in events if event["event_type"] == "route_released")
    assert released["failover"] is True
    assert released["final_route_id"] == "qwen27_9070_backup"


@pytest.mark.asyncio
async def test_release_uses_provider_reset_window_for_cooldown():
    manager = QueueAwareRouteManager(_config())
    route = await manager.acquire_route(
        user_message="please do a stronger review of this architecture",
        primary_model="qwen3.6-35b-a3b:iq4xs",
        primary_runtime={"provider": "custom", "base_url": "http://127.0.0.1:8002/v1", "api_mode": "chat_completions"},
        session_key="s6",
    )
    reset_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    manager.pop_recent_events()

    await manager.release_route(
        route,
        duration_seconds=4.0,
        success=False,
        session_key="s6",
        failure_context={"reason": "rate_limit", "reset_at": reset_at},
    )

    snapshot = manager.snapshot()["routes"]["qwen27_7900_strong"]
    assert snapshot["state"] == "cooldown"
    assert snapshot["cooldown_until"] > 0
    events = manager.pop_recent_events()
    released = next(event for event in events if event["event_type"] == "route_released")
    assert released["reset_at"] == pytest.approx(datetime.fromisoformat(reset_at).timestamp())
    state_change = next(event for event in events if event["event_type"] == "route_state_changed")
    assert state_change["reason"] == "provider_reset_window"
