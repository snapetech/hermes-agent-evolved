from __future__ import annotations

import threading
import time

import yaml

from agent.llm_call_queue import acquire_llm_slot


def test_local_endpoint_slots_are_serialized(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "llm_call_queue": {
                    "enabled": True,
                    "local_max_concurrency": 1,
                    "status_interval_seconds": 1,
                }
            }
        ),
        encoding="utf-8",
    )

    entered = threading.Event()
    finished = threading.Event()

    with acquire_llm_slot(
        model="local-model",
        provider="custom",
        base_url="http://127.0.0.1:8000/v1",
        api_mode="chat_completions",
    ):

        def contender():
            with acquire_llm_slot(
                model="local-model",
                provider="custom",
                base_url="http://127.0.0.1:8000/v1",
                api_mode="chat_completions",
            ):
                entered.set()
            finished.set()

        thread = threading.Thread(target=contender)
        thread.start()
        assert not entered.wait(0.3)

    assert entered.wait(2.0)
    assert finished.wait(2.0)
    thread.join(timeout=2.0)


def test_cloud_routes_are_unlimited_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump({"llm_call_queue": {"enabled": True}}),
        encoding="utf-8",
    )

    with acquire_llm_slot(
        model="cloud-model",
        provider="anthropic",
        base_url="https://api.anthropic.com",
        api_mode="anthropic_messages",
    ):
        start = time.monotonic()
        with acquire_llm_slot(
            model="cloud-model",
            provider="anthropic",
            base_url="https://api.anthropic.com",
            api_mode="anthropic_messages",
        ):
            assert time.monotonic() - start < 0.2
