from agent.adaptive_fallback_routing import build_fallback_chain


def test_build_fallback_chain_orders_free_then_paid(monkeypatch):
    runtimes = {
        "kilocode": {
            "provider": "kilocode",
            "api_key": "kilo-key",
            "base_url": "https://api.kilo.ai/api/gateway",
        },
        "anthropic": {
            "provider": "anthropic",
            "api_key": "anthropic-key",
            "base_url": "https://api.anthropic.com",
        },
        "openai-codex": {
            "provider": "openai-codex",
            "api_key": "codex-key",
            "base_url": "https://api.openai.com/v1",
        },
    }

    monkeypatch.setattr(
        "hermes_cli.runtime_provider.resolve_runtime_provider",
        lambda requested=None, **kwargs: runtimes[requested],
    )
    monkeypatch.setattr(
        "hermes_cli.models.provider_model_ids",
        lambda provider, force_refresh=False: [
            "kilo-auto/free",
            "openrouter/free",
            "moonshotai/kimi-k2.6",
        ] if provider == "kilocode" else [],
    )

    primary = {
        "provider": "custom",
        "model": "qwen3.6-35b-a3b:iq4xs",
        "base_url": "http://127.0.0.1:8002/v1",
    }
    config = {"enabled": True}

    chain = build_fallback_chain(primary, config)

    assert [entry["model"] for entry in chain] == [
        "kilo-auto/free",
        "openrouter/free",
        "moonshotai/kimi-k2.6",
        "claude-sonnet-4.6",
        "gpt-5.3-codex",
    ]


def test_build_fallback_chain_skips_unavailable_or_duplicate_candidates(monkeypatch):
    runtimes = {
        "kilocode": {
            "provider": "kilocode",
            "api_key": "kilo-key",
            "base_url": "https://api.kilo.ai/api/gateway",
        },
        "anthropic": {
            "provider": "anthropic",
            "api_key": "",
            "base_url": "https://api.anthropic.com",
        },
    }

    monkeypatch.setattr(
        "hermes_cli.runtime_provider.resolve_runtime_provider",
        lambda requested=None, **kwargs: runtimes[requested],
    )
    monkeypatch.setattr(
        "hermes_cli.models.provider_model_ids",
        lambda provider, force_refresh=False: ["moonshotai/kimi-k2.6"] if provider == "kilocode" else [],
    )

    primary = {
        "provider": "kilocode",
        "model": "moonshotai/kimi-k2.6",
        "base_url": "https://api.kilo.ai/api/gateway",
    }
    config = {
        "enabled": True,
        "free_candidates": [{"provider": "kilocode", "model": "missing-free"}],
        "paid_candidates": [
            {"provider": "kilocode", "model": "moonshotai/kimi-k2.6"},
            {"provider": "anthropic", "model": "claude-sonnet-4.6"},
        ],
    }

    chain = build_fallback_chain(primary, config)

    assert chain == []
