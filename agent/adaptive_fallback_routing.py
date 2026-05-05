"""Automatic local -> free -> paid fallback-chain builder."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


_DEFAULT_FREE_CANDIDATES: tuple[dict[str, str], ...] = (
    {"provider": "kilocode", "model": "kilo-auto/free"},
    {"provider": "kilocode", "model": "openrouter/free"},
    {"provider": "kilocode", "model": "x-ai/grok-code-fast-1:optimized:free"},
    {"provider": "kilocode", "model": "stepfun/step-3.5-flash:free"},
    {"provider": "kilocode", "model": "nvidia/nemotron-3-super-120b-a12b:free"},
)

_DEFAULT_PAID_CANDIDATES: tuple[dict[str, str], ...] = (
    {"provider": "kilocode", "model": "moonshotai/kimi-k2.6"},
    {"provider": "anthropic", "model": "claude-sonnet-4.6"},
    {"provider": "openai-codex", "model": "gpt-5.3-codex"},
)


def _candidate_list(value: Any, default: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return [dict(item) for item in default]
    out: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "").strip().lower()
        model = str(item.get("model") or "").strip()
        if provider and model:
            out.append({"provider": provider, "model": model})
    return out or [dict(item) for item in default]


def build_fallback_chain(
    primary: Dict[str, Any],
    routing_config: Optional[Dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build an ordered fallback chain from routing policy + live availability.

    The primary model/runtime remains unchanged. This function only builds the
    backup chain that ``AIAgent`` will rotate through on quota / rate-limit /
    connection failures.
    """
    cfg = routing_config or {}
    if not bool(cfg.get("enabled")):
        return []

    free_first = bool(cfg.get("free_first", True))
    dynamic_kilo_catalog = bool(cfg.get("dynamic_kilo_catalog", True))

    free_candidates = _candidate_list(cfg.get("free_candidates"), _DEFAULT_FREE_CANDIDATES)
    paid_candidates = _candidate_list(cfg.get("paid_candidates"), _DEFAULT_PAID_CANDIDATES)
    ordered_candidates = (free_candidates + paid_candidates) if free_first else (paid_candidates + free_candidates)

    from hermes_cli.models import provider_model_ids
    from hermes_cli.runtime_provider import resolve_runtime_provider

    kilo_catalog: Optional[set[str]] = None
    seen: set[tuple[str, str, str]] = set()
    chain: list[dict[str, Any]] = []

    primary_provider = str(primary.get("provider") or "").strip().lower()
    primary_model = str(primary.get("model") or "").strip()
    primary_base_url = str(primary.get("base_url") or "").strip()

    for candidate in ordered_candidates:
        provider = candidate["provider"]
        model = candidate["model"]

        try:
            runtime = resolve_runtime_provider(requested=provider)
        except Exception:
            continue
        if not runtime.get("api_key"):
            continue

        if provider == "kilocode" and dynamic_kilo_catalog:
            if kilo_catalog is None:
                kilo_catalog = set(provider_model_ids("kilocode") or [])
            if kilo_catalog and model not in kilo_catalog:
                continue

        base_url = str(runtime.get("base_url") or "").strip()
        signature = (provider, model, base_url)
        if signature in seen:
            continue
        if (
            provider == primary_provider
            and model == primary_model
            and (not base_url or base_url == primary_base_url)
        ):
            continue

        seen.add(signature)
        chain.append(
            {
                "provider": provider,
                "model": model,
                "base_url": base_url,
                "api_key": runtime.get("api_key") or "",
            }
        )

    return chain
