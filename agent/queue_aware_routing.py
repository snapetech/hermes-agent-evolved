"""Queue-aware local route manager for Hermes gateway.

This module implements a lightweight endpoint picker for heterogeneous local
LLM routes. It tracks route health, active in-flight turns, simple EWMA latency,
session stickiness, cooldown/probation states, and ordered failover chains.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

from utils import is_truthy_value

logger = logging.getLogger(__name__)


_DEFAULT_COMPLEX_KEYWORDS = (
    "stronger",
    "think harder",
    "harder",
    "careful",
    "review",
    "architecture",
    "benchmark",
    "compare",
    "analysis",
    "analyze",
    "deep",
    "thorough",
    "plan",
    "investigate",
    "debug",
    "refactor",
    "design",
)

_DEFAULT_UTILITY_KEYWORDS = (
    "json",
    "route",
    "routing",
    "classify",
    "classification",
    "extract",
    "schema",
    "approval",
    "risk",
    "status summary",
    "summarize",
    "summary",
)

_DEFAULT_VALIDATOR_KEYWORDS = (
    "verify",
    "validation",
    "validator",
    "double-check",
    "double check",
    "second opinion",
    "cross-check",
)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    return is_truthy_value(value, default=default)


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_text_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


@dataclass
class RouteState:
    route_id: str
    model: str
    provider: str
    base_url: str
    api_mode: str = "chat_completions"
    api_key: str = "no-key-required"
    requested_provider: str = ""
    resolve_runtime: bool = False
    enabled: bool = True
    priority: int = 0
    tags: set[str] = field(default_factory=set)
    failure_domains: set[str] = field(default_factory=set)
    fallback_route_ids: list[str] = field(default_factory=list)
    max_concurrency: int = 1
    max_queue_depth: int = 0
    initial_latency_seconds: float = 5.0
    cooldown_seconds: float = 45.0
    healthcheck_path: str = "/models"
    healthcheck_enabled: bool = True
    state: str = "healthy"  # healthy | recovering | cooldown | draining | unavailable
    active_requests: int = 0
    queued_requests: int = 0
    ewma_latency_seconds: float = 0.0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    cooldown_until: float = 0.0
    recovering_since: float = 0.0
    health_error: str = ""
    unhealthy_after_failures: int = 2
    recover_after_successes: int = 2
    probation_seconds: float = 30.0
    canary_every_n: int = 5
    recovering_assignments: int = 0
    last_assigned_at: float = 0.0

    def signature(self) -> tuple[str, str, str]:
        return (self.model, self.provider, self.base_url.rstrip("/"))

    def estimated_latency(self) -> float:
        return self.ewma_latency_seconds or self.initial_latency_seconds or 5.0

    def expected_wait_seconds(self) -> float:
        if self.active_requests < self.max_concurrency:
            return 0.0
        slots_ahead = max(1, self.active_requests - self.max_concurrency + 1)
        return slots_ahead * (self.estimated_latency() / max(1, self.max_concurrency))


@dataclass
class RouteSelection:
    route_id: str
    model: str
    runtime: Dict[str, Any]
    fallback_chain: list[dict[str, Any]]
    request_class: str
    routing_reason: str
    queue_wait_seconds: float = 0.0
    routed_by_manager: bool = True


class QueueAwareRouteManager:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.enabled = _coerce_bool(cfg.get("enabled"), False)
        self.default_request_class = str(cfg.get("default_request_class") or "general").strip().lower() or "general"
        self.health_check_interval_seconds = _coerce_float(cfg.get("health_check_interval_seconds"), 20.0)
        self.health_check_timeout_seconds = _coerce_float(cfg.get("health_check_timeout_seconds"), 3.0)
        self.session_stickiness_seconds = _coerce_float(cfg.get("session_stickiness_seconds"), 1800.0)
        self._classes = self._normalize_classes(cfg.get("classes") or {})
        self._lock = asyncio.Lock()
        self._conditions: dict[str, asyncio.Condition] = {}
        self._session_pins: dict[str, dict[str, Any]] = {}
        self._routes: dict[str, RouteState] = {}
        self._route_order: list[str] = []
        self._recent_events: deque[dict[str, Any]] = deque(maxlen=200)
        self._build_routes(cfg.get("routes") or [])

    def _record_event(self, event_type: str, **payload: Any) -> None:
        event = {
            "ts": time.time(),
            "event_type": event_type,
            **payload,
        }
        self._recent_events.append(event)

    def pop_recent_events(self) -> list[dict[str, Any]]:
        events = list(self._recent_events)
        self._recent_events.clear()
        return events

    def _normalize_classes(self, classes: Dict[str, Any]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        defaults = {
            "general": {
                "preferred_tags": ["general", "workhorse"],
                "keywords": [],
                "wait_for_preferred_seconds": 2.0,
            },
            "strong": {
                "preferred_tags": ["stronger", "quality"],
                "keywords": list(_DEFAULT_COMPLEX_KEYWORDS),
                "wait_for_preferred_seconds": 8.0,
            },
            "utility": {
                "preferred_tags": ["utility", "json"],
                "keywords": list(_DEFAULT_UTILITY_KEYWORDS),
                "wait_for_preferred_seconds": 4.0,
            },
            "validator": {
                "preferred_tags": ["validator"],
                "keywords": list(_DEFAULT_VALIDATOR_KEYWORDS),
                "wait_for_preferred_seconds": 4.0,
            },
        }
        for name, default in defaults.items():
            raw = classes.get(name) if isinstance(classes, dict) else None
            block = raw if isinstance(raw, dict) else {}
            normalized[name] = {
                "preferred_tags": [tag.strip().lower() for tag in _normalize_text_list(block.get("preferred_tags"))] or default["preferred_tags"],
                "keywords": [kw.strip().lower() for kw in _normalize_text_list(block.get("keywords"))] or default["keywords"],
                "wait_for_preferred_seconds": _coerce_float(
                    block.get("wait_for_preferred_seconds"),
                    float(default["wait_for_preferred_seconds"]),
                ),
            }
        return normalized

    def _build_routes(self, routes: Iterable[dict[str, Any]]) -> None:
        self._routes = {}
        self._route_order = []
        self._conditions = {}
        for raw in routes:
            if not isinstance(raw, dict):
                continue
            route_id = str(raw.get("id") or "").strip()
            model = str(raw.get("model") or "").strip()
            provider = str(raw.get("provider") or "").strip().lower()
            base_url = str(raw.get("base_url") or "").strip().rstrip("/")
            if not route_id or not model or not provider or not base_url:
                continue
            route = RouteState(
                route_id=route_id,
                model=model,
                provider=provider,
                base_url=base_url,
                api_mode=str(raw.get("api_mode") or "chat_completions").strip() or "chat_completions",
                api_key=str(raw.get("api_key") or "no-key-required").strip() or "no-key-required",
                requested_provider=str(raw.get("requested_provider") or provider).strip().lower() or provider,
                resolve_runtime=_coerce_bool(raw.get("resolve_runtime"), provider != "custom"),
                enabled=_coerce_bool(raw.get("enabled"), True),
                priority=_coerce_int(raw.get("priority"), 0),
                tags={tag.strip().lower() for tag in _normalize_text_list(raw.get("tags"))},
                failure_domains={tag.strip().lower() for tag in _normalize_text_list(raw.get("failure_domains"))},
                fallback_route_ids=_normalize_text_list(raw.get("fallback_route_ids")),
                max_concurrency=max(1, _coerce_int(raw.get("max_concurrency"), 1)),
                max_queue_depth=max(0, _coerce_int(raw.get("max_queue_depth"), 0)),
                initial_latency_seconds=max(0.1, _coerce_float(raw.get("initial_latency_seconds"), 5.0)),
                cooldown_seconds=max(1.0, _coerce_float(raw.get("cooldown_seconds"), 45.0)),
                healthcheck_path=str(raw.get("healthcheck_path") or "/models").strip() or "/models",
                healthcheck_enabled=_coerce_bool(raw.get("healthcheck_enabled"), provider == "custom"),
                state="draining" if _coerce_bool(raw.get("draining"), False) else "healthy",
                unhealthy_after_failures=max(1, _coerce_int(raw.get("unhealthy_after_failures"), 2)),
                recover_after_successes=max(1, _coerce_int(raw.get("recover_after_successes"), 2)),
                probation_seconds=max(0.0, _coerce_float(raw.get("probation_seconds"), 30.0)),
                canary_every_n=max(1, _coerce_int(raw.get("canary_every_n"), 5)),
            )
            self._routes[route_id] = route
            self._route_order.append(route_id)
            self._conditions[route_id] = asyncio.Condition()

        self._route_order.sort(
            key=lambda route_id: (
                -self._routes[route_id].priority,
                self._routes[route_id].route_id,
            )
        )

    def classify_request(
        self,
        user_message: str,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        context = request_context if isinstance(request_context, dict) else {}
        forced = str(context.get("force_request_class") or "").strip().lower()
        if forced in self._classes:
            return forced
        if any(
            _coerce_bool(context.get(key), False)
            for key in (
                "validation_failed",
                "validator_escalation",
                "has_validation_failures",
            )
        ):
            return "validator"
        if any(
            _coerce_int(context.get(key), 0) > 0
            for key in (
                "validation_failure_count",
                "formatter_failure_count",
                "lint_failure_count",
            )
        ):
            return "validator"
        lowered = str(user_message or "").strip().lower()
        if not lowered:
            return self.default_request_class
        for name in ("validator", "utility", "strong"):
            cfg = self._classes.get(name) or {}
            keywords = cfg.get("keywords") or []
            if any(keyword in lowered for keyword in keywords):
                return name
        return self.default_request_class

    def _refresh_route_state_locked(self, route: RouteState, now: float) -> None:
        if route.state == "cooldown" and now >= route.cooldown_until:
            old_state = route.state
            route.state = "recovering"
            if not route.recovering_since:
                route.recovering_since = now
            route.consecutive_successes = 0
            route.health_error = ""
            self._record_event(
                "route_state_changed",
                route_id=route.route_id,
                old_state=old_state,
                new_state=route.state,
                reason="cooldown_expired",
            )
        elif route.state == "recovering":
            if (
                route.consecutive_successes >= route.recover_after_successes
                and route.recovering_since
                and now - route.recovering_since >= route.probation_seconds
            ):
                old_state = route.state
                route.state = "healthy"
                route.health_error = ""
                self._record_event(
                    "route_state_changed",
                    route_id=route.route_id,
                    old_state=old_state,
                    new_state=route.state,
                    reason="probation_passed",
                )

    def _route_available_locked(self, route: RouteState, now: float, *, excluded: set[str]) -> bool:
        self._refresh_route_state_locked(route, now)
        if route.route_id in excluded or not route.enabled:
            return False
        if route.state in {"draining", "unavailable"}:
            return False
        if route.state == "cooldown":
            return False
        if route.state == "recovering":
            route.recovering_assignments += 1
            if route.recovering_assignments % route.canary_every_n != 1:
                return False
        return True

    def _preferred_tags_for_class(self, request_class: str) -> set[str]:
        cfg = self._classes.get(request_class) or self._classes.get(self.default_request_class) or {}
        preferred = {tag.strip().lower() for tag in cfg.get("preferred_tags") or []}
        if request_class == "validator":
            strong_cfg = self._classes.get("strong") or {}
            preferred.update(
                tag.strip().lower() for tag in strong_cfg.get("preferred_tags") or []
            )
            preferred.update({"validator", "stronger", "quality"})
        return preferred

    def _wait_budget_for_class(self, request_class: str) -> float:
        cfg = self._classes.get(request_class) or self._classes.get(self.default_request_class) or {}
        return max(0.0, _coerce_float(cfg.get("wait_for_preferred_seconds"), 0.0))

    def _route_preference_score(self, route: RouteState, preferred_tags: set[str]) -> int:
        overlap = len(route.tags & preferred_tags)
        continuity_penalty = -100 if "continuity" in route.tags else 0
        return overlap * 1000 + route.priority + continuity_penalty

    def _fallback_chain_for_route_locked(self, selected_route_id: str) -> list[dict[str, Any]]:
        selected = self._routes.get(selected_route_id)
        if not selected:
            return []
        fallback_ids = selected.fallback_route_ids or [
            route_id for route_id in self._route_order if route_id != selected_route_id
        ]
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for route_id in fallback_ids:
            route = self._routes.get(route_id)
            if not route or route.route_id == selected_route_id or route.route_id in seen:
                continue
            if route.state in {"draining", "unavailable"}:
                continue
            seen.add(route.route_id)
            out.append(
                {
                    "provider": route.provider,
                    "model": route.model,
                    "base_url": route.base_url,
                    "api_key": route.api_key or "no-key-required",
                }
            )
        return out

    def match_route(self, model: str, provider: str, base_url: str) -> Optional[str]:
        signature = (str(model or "").strip(), str(provider or "").strip().lower(), str(base_url or "").strip().rstrip("/"))
        for route_id, route in self._routes.items():
            if route.signature() == signature:
                return route_id
        return None

    def _build_passthrough_selection(self, model: str, runtime: Dict[str, Any], request_class: str, reason: str) -> RouteSelection:
        return RouteSelection(
            route_id="",
            model=model,
            runtime={
                "api_key": runtime.get("api_key"),
                "base_url": runtime.get("base_url"),
                "provider": runtime.get("provider"),
                "api_mode": runtime.get("api_mode"),
                "command": runtime.get("command"),
                "args": list(runtime.get("args") or []),
                "credential_pool": runtime.get("credential_pool"),
            },
            fallback_chain=[],
            request_class=request_class,
            routing_reason=reason,
            routed_by_manager=False,
        )

    async def acquire_route(
        self,
        *,
        user_message: str,
        primary_model: str,
        primary_runtime: Dict[str, Any],
        session_key: Optional[str],
        pinned: bool = False,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> RouteSelection:
        request_class = self.classify_request(user_message, request_context=request_context)
        if not self.enabled or not self._routes:
            return self._build_passthrough_selection(primary_model, primary_runtime, request_class, "queue_routing_disabled")

        pinned_route_id = self.match_route(
            primary_model,
            str(primary_runtime.get("provider") or ""),
            str(primary_runtime.get("base_url") or ""),
        )
        if pinned and pinned_route_id:
            async with self._lock:
                route = self._routes[pinned_route_id]
                route.active_requests += 1
                route.last_assigned_at = time.monotonic()
            return RouteSelection(
                route_id=route.route_id,
                model=route.model,
                runtime={
                    "api_key": route.api_key,
                    "base_url": route.base_url,
                    "provider": route.provider,
                    "requested_provider": route.requested_provider,
                    "api_mode": route.api_mode,
                    "resolve_runtime": route.resolve_runtime,
                    "command": None,
                    "args": [],
                    "credential_pool": None,
                },
                fallback_chain=self._fallback_chain_for_route_locked(route.route_id),
                request_class=request_class,
                routing_reason="session_pinned_model_override",
            )
        if pinned and not pinned_route_id:
            return self._build_passthrough_selection(primary_model, primary_runtime, request_class, "unknown_pinned_model")

        preferred_tags = self._preferred_tags_for_class(request_class)
        wait_budget = self._wait_budget_for_class(request_class)
        excluded: set[str] = set()

        while True:
            queued_route_id = ""
            queue_wait_seconds = 0.0
            async with self._lock:
                now = time.monotonic()
                sticky_route_id = ""
                if session_key:
                    pin = self._session_pins.get(session_key)
                    if pin and float(pin.get("expires_at") or 0.0) > now:
                        sticky_route_id = str(pin.get("route_id") or "")
                    elif pin:
                        self._session_pins.pop(session_key, None)

                candidates: list[tuple[int, float, RouteState]] = []
                for route_id in self._route_order:
                    route = self._routes[route_id]
                    if not self._route_available_locked(route, now, excluded=excluded):
                        continue
                    preference = self._route_preference_score(route, preferred_tags)
                    if sticky_route_id and route_id == sticky_route_id:
                        preference += 5000
                    finish = route.expected_wait_seconds() + route.estimated_latency()
                    candidates.append((preference, finish, route))

                if not candidates:
                    if pinned_route_id and pinned_route_id not in excluded:
                        route = self._routes[pinned_route_id]
                        route.active_requests += 1
                        route.last_assigned_at = now
                        selection = RouteSelection(
                            route_id=route.route_id,
                            model=route.model,
                            runtime={
                                "api_key": route.api_key,
                                "base_url": route.base_url,
                                "provider": route.provider,
                                "requested_provider": route.requested_provider,
                                "api_mode": route.api_mode,
                                "resolve_runtime": route.resolve_runtime,
                                "command": None,
                                "args": [],
                                "credential_pool": None,
                            },
                            fallback_chain=self._fallback_chain_for_route_locked(route.route_id),
                            request_class=request_class,
                            routing_reason="fallback_to_primary_route",
                        )
                        if session_key:
                            self._session_pins[session_key] = {
                                "route_id": route.route_id,
                                "expires_at": now + self.session_stickiness_seconds,
                            }
                        self._record_event(
                            "route_selected",
                            route_id=route.route_id,
                            request_class=request_class,
                            reason="fallback_to_primary_route",
                            queue_wait_seconds=0.0,
                            session_key=session_key or "",
                        )
                        return selection
                    return self._build_passthrough_selection(primary_model, primary_runtime, request_class, "no_eligible_route")

                candidates.sort(key=lambda item: (-item[0], item[1], item[2].route_id))
                preference, _, route = candidates[0]

                if route.active_requests < route.max_concurrency:
                    route.active_requests += 1
                    route.last_assigned_at = now
                    if session_key:
                        self._session_pins[session_key] = {
                            "route_id": route.route_id,
                            "expires_at": now + self.session_stickiness_seconds,
                        }
                    self._record_event(
                        "route_selected",
                        route_id=route.route_id,
                        request_class=request_class,
                        reason=f"class={request_class};route={route.route_id};score={preference}",
                        queue_wait_seconds=0.0,
                        session_key=session_key or "",
                    )
                    return RouteSelection(
                        route_id=route.route_id,
                        model=route.model,
                        runtime={
                            "api_key": route.api_key,
                            "base_url": route.base_url,
                            "provider": route.provider,
                            "requested_provider": route.requested_provider,
                            "api_mode": route.api_mode,
                            "resolve_runtime": route.resolve_runtime,
                            "command": None,
                            "args": [],
                            "credential_pool": None,
                        },
                        fallback_chain=self._fallback_chain_for_route_locked(route.route_id),
                        request_class=request_class,
                        routing_reason=f"class={request_class};route={route.route_id};score={preference}",
                    )

                wait_seconds = route.expected_wait_seconds()
                if wait_seconds <= wait_budget and route.queued_requests < route.max_queue_depth:
                    route.queued_requests += 1
                    queued_route_id = route.route_id
                    queue_wait_seconds = max(0.1, wait_seconds)
                    self._record_event(
                        "route_queued",
                        route_id=route.route_id,
                        request_class=request_class,
                        queue_wait_seconds=queue_wait_seconds,
                        session_key=session_key or "",
                    )
                else:
                    self._record_event(
                        "route_rejected",
                        route_id=route.route_id,
                        request_class=request_class,
                        reason="queue_budget_exceeded",
                        expected_wait_seconds=wait_seconds,
                        session_key=session_key or "",
                    )
                    excluded.add(route.route_id)
                    continue

            condition = self._conditions[queued_route_id]
            timed_out = False
            try:
                async with condition:
                    await asyncio.wait_for(condition.wait(), timeout=queue_wait_seconds)
            except asyncio.TimeoutError:
                timed_out = True
            finally:
                async with self._lock:
                    route = self._routes.get(queued_route_id)
                    if route:
                        route.queued_requests = max(0, route.queued_requests - 1)
            if timed_out:
                excluded.add(queued_route_id)

    async def release_route(
        self,
        selection: Optional[RouteSelection],
        *,
        duration_seconds: float,
        success: bool,
        session_key: Optional[str],
        final_model: Optional[str] = None,
        final_provider: Optional[str] = None,
        final_base_url: Optional[str] = None,
        failure_context: Optional[dict[str, Any]] = None,
    ) -> None:
        if not selection or not selection.routed_by_manager or not selection.route_id:
            return
        final_route_id = self.match_route(
            final_model or selection.model,
            final_provider or str(selection.runtime.get("provider") or ""),
            final_base_url or str(selection.runtime.get("base_url") or ""),
        )
        notify_route_id = ""
        async with self._lock:
            now = time.monotonic()
            selected = self._routes.get(selection.route_id)
            if selected:
                selected.active_requests = max(0, selected.active_requests - 1)
                notify_route_id = selected.route_id
                latency = max(0.1, duration_seconds)
                normalized_reset_at = self._normalize_reset_at(
                    (failure_context or {}).get("reset_at")
                    or (failure_context or {}).get("resets_at")
                    or (failure_context or {}).get("retry_until")
                )
                if final_route_id and final_route_id != selection.route_id:
                    selected.consecutive_failures += 1
                    selected.consecutive_successes = 0
                elif success:
                    selected.consecutive_failures = 0
                    selected.consecutive_successes += 1
                    if selected.ewma_latency_seconds <= 0:
                        selected.ewma_latency_seconds = latency
                    else:
                        selected.ewma_latency_seconds = (selected.ewma_latency_seconds * 0.7) + (latency * 0.3)
                else:
                    selected.consecutive_failures += 1
                    selected.consecutive_successes = 0

                if selected.consecutive_failures >= selected.unhealthy_after_failures:
                    old_state = selected.state
                    selected.state = "cooldown"
                    selected.cooldown_until = max(now + selected.cooldown_seconds, normalized_reset_at or 0.0)
                    selected.recovering_since = 0.0
                    selected.health_error = "recent request failures"
                    self._record_event(
                        "route_state_changed",
                        route_id=selected.route_id,
                        old_state=old_state,
                        new_state=selected.state,
                        reason="request_failures",
                    )
                elif normalized_reset_at and normalized_reset_at > now:
                    old_state = selected.state
                    selected.state = "cooldown"
                    selected.cooldown_until = normalized_reset_at
                    selected.recovering_since = 0.0
                    selected.health_error = str((failure_context or {}).get("reason") or "provider reset window")
                    self._record_event(
                        "route_state_changed",
                        route_id=selected.route_id,
                        old_state=old_state,
                        new_state=selected.state,
                        reason="provider_reset_window",
                        reset_at=normalized_reset_at,
                    )

            if final_route_id and final_route_id != selection.route_id:
                final_route = self._routes.get(final_route_id)
                if final_route:
                    final_route.consecutive_failures = 0
                    final_route.consecutive_successes += 1
                    if final_route.state == "cooldown":
                        final_route.state = "recovering"
                        final_route.recovering_since = now
                    latency = max(0.1, duration_seconds)
                    if final_route.ewma_latency_seconds <= 0:
                        final_route.ewma_latency_seconds = latency
                    else:
                        final_route.ewma_latency_seconds = (final_route.ewma_latency_seconds * 0.7) + (latency * 0.3)
                    if session_key:
                        self._session_pins[session_key] = {
                            "route_id": final_route_id,
                            "expires_at": now + self.session_stickiness_seconds,
                        }
            elif session_key and selected:
                self._session_pins[session_key] = {
                    "route_id": selected.route_id,
                    "expires_at": now + self.session_stickiness_seconds,
                }
            self._record_event(
                "route_released",
                route_id=selection.route_id,
                final_route_id=final_route_id or selection.route_id,
                success=bool(success),
                failover=bool(final_route_id and final_route_id != selection.route_id),
                duration_seconds=max(0.1, duration_seconds),
                failure_reason=(failure_context or {}).get("reason") if isinstance(failure_context, dict) else "",
                reset_at=normalized_reset_at,
                session_key=session_key or "",
            )

        if notify_route_id:
            condition = self._conditions.get(notify_route_id)
            if condition is not None:
                async with condition:
                    condition.notify(1)

    async def mark_route_cooldown(
        self,
        route_id: str,
        *,
        reason: str,
        cooldown_seconds: Optional[float] = None,
        reset_at: Any = None,
    ) -> None:
        async with self._lock:
            route = self._routes.get(route_id)
            if not route:
                return
            now = time.monotonic()
            normalized_reset_at = self._normalize_reset_at(reset_at)
            old_state = route.state
            route.state = "cooldown"
            route.cooldown_until = max(
                now + (cooldown_seconds if cooldown_seconds is not None else route.cooldown_seconds),
                normalized_reset_at or 0.0,
            )
            route.recovering_since = 0.0
            route.health_error = reason
            self._record_event(
                "route_state_changed",
                route_id=route.route_id,
                old_state=old_state,
                new_state=route.state,
                reason=reason,
                reset_at=normalized_reset_at,
            )

    async def probe_health(self) -> None:
        if not self.enabled or not self._routes:
            return
        try:
            import requests
        except Exception:
            return

        routes = list(self._routes.values())
        timeout = self.health_check_timeout_seconds

        def _probe(route: RouteState) -> tuple[str, bool, str]:
            if not route.healthcheck_enabled:
                return (route.route_id, True, "")
            url = f"{route.base_url}{route.healthcheck_path}"
            try:
                resp = requests.get(url, timeout=timeout)
                if resp.ok:
                    return (route.route_id, True, "")
                return (route.route_id, False, f"http {resp.status_code}")
            except Exception as exc:
                return (route.route_id, False, str(exc))

        results = await asyncio.gather(*[asyncio.to_thread(_probe, route) for route in routes])
        async with self._lock:
            now = time.monotonic()
            for route_id, ok, error in results:
                route = self._routes.get(route_id)
                if not route:
                    continue
                if ok:
                    route.health_error = ""
                    route.consecutive_successes += 1
                    if route.state == "unavailable":
                        old_state = route.state
                        route.state = "recovering"
                        route.recovering_since = now
                        self._record_event(
                            "route_state_changed",
                            route_id=route.route_id,
                            old_state=old_state,
                            new_state=route.state,
                            reason="health_probe_ok",
                        )
                    self._refresh_route_state_locked(route, now)
                else:
                    route.health_error = error
                    if route.state not in {"draining", "cooldown"}:
                        old_state = route.state
                        route.state = "unavailable"
                        self._record_event(
                            "route_state_changed",
                            route_id=route.route_id,
                            old_state=old_state,
                            new_state=route.state,
                            reason="health_probe_failed",
                            error=error,
                        )
                    route.consecutive_successes = 0

    def snapshot(self) -> dict[str, Any]:
        routes = {}
        for route_id, route in self._routes.items():
            routes[route_id] = {
                "state": route.state,
                "active_requests": route.active_requests,
                "queued_requests": route.queued_requests,
                "ewma_latency_seconds": route.ewma_latency_seconds,
                "consecutive_failures": route.consecutive_failures,
                "consecutive_successes": route.consecutive_successes,
                "health_error": route.health_error,
                "requested_provider": route.requested_provider,
                "cooldown_until": route.cooldown_until,
            }
        return {"enabled": self.enabled, "routes": routes, "recent_events": list(self._recent_events)}

    @staticmethod
    def _normalize_reset_at(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            numeric = float(value)
            return numeric / 1000.0 if numeric > 1_000_000_000_000 else numeric
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            try:
                numeric = float(raw)
            except ValueError:
                numeric = None
            if numeric is not None:
                return numeric / 1000.0 if numeric > 1_000_000_000_000 else numeric
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return None
        return None
