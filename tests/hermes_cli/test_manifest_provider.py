"""Manifest provider integration tests."""

from hermes_cli.auth import (
    PROVIDER_REGISTRY,
    resolve_api_key_provider_credentials,
    resolve_provider,
)
from hermes_cli.config import OPTIONAL_ENV_VARS
from hermes_cli.models import (
    _PROVIDER_MODELS,
    get_default_model_for_provider,
    normalize_provider,
    parse_model_input,
    validate_requested_model,
)
from agent.model_metadata import get_model_context_length


def test_manifest_provider_registry():
    assert "manifest" in PROVIDER_REGISTRY
    config = PROVIDER_REGISTRY["manifest"]
    assert config.name == "Manifest"
    assert config.auth_type == "api_key"
    assert config.api_key_env_vars == ("MANIFEST_API_KEY",)
    assert config.base_url_env_var == "MANIFEST_BASE_URL"
    assert config.inference_base_url == "http://localhost:3001/v1"


def test_manifest_env_vars_are_configurable():
    assert "MANIFEST_API_KEY" in OPTIONAL_ENV_VARS
    assert "MANIFEST_BASE_URL" in OPTIONAL_ENV_VARS


def test_manifest_aliases_and_model_catalog():
    assert normalize_provider("mnfst") == "manifest"
    assert normalize_provider("manifest.build") == "manifest"
    assert resolve_provider("manifest-build") == "manifest"
    assert _PROVIDER_MODELS["manifest"] == ["manifest/auto"]
    assert get_default_model_for_provider("manifest") == "manifest/auto"


def test_manifest_model_input_parses_provider_prefix():
    provider, model = parse_model_input("manifest:manifest/auto", "custom")
    assert provider == "manifest"
    assert model == "manifest/auto"


def test_manifest_auto_validates_without_live_models_probe():
    validation = validate_requested_model("manifest/auto", "manifest")
    assert validation["accepted"] is True
    assert validation["persist"] is True
    assert validation["recognized"] is True


def test_manifest_auto_context_length():
    assert get_model_context_length("manifest/auto", provider="manifest") == 200000


def test_manifest_runtime_credentials(monkeypatch):
    monkeypatch.setenv("MANIFEST_API_KEY", "mnfst_test_key")
    monkeypatch.setenv("MANIFEST_BASE_URL", "http://127.0.0.1:3001/v1")

    creds = resolve_api_key_provider_credentials("manifest")

    assert creds["provider"] == "manifest"
    assert creds["api_key"] == "mnfst_test_key"
    assert creds["base_url"] == "http://127.0.0.1:3001/v1"
    assert creds["source"] == "MANIFEST_API_KEY"
