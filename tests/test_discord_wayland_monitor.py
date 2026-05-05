from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONITOR = ROOT / "scripts" / "discord-wayland-monitor.py"


def _load_monitor():
    spec = importlib.util.spec_from_file_location("discord_wayland_monitor", MONITOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scrape_schema_prefers_dom_links_over_screenshots():
    monitor = _load_monitor()

    schemas = {schema["name"]: schema for schema in monitor._tool_schemas()}

    assert "discord_monitor_scrape" in schemas
    assert "href" in schemas["discord_monitor_scrape"]["description"]
    assert "since" in schemas["discord_monitor_scrape"]["inputSchema"]["properties"]
    assert "OCR" not in schemas["discord_monitor_scrape"]["description"]
    assert schemas["discord_monitor_screenshot"]["inputSchema"]["properties"]["full_page"]["default"] is False


def test_merge_scrape_pages_dedupes_messages_and_pr_links():
    monitor = _load_monitor()

    merged = monitor._merge_scrape_pages(
        [
            {
                "url": "https://discord.com/channels/g/c",
                "messages": [
                    {
                        "id": "m1",
                        "text": "PR",
                        "links": ["https://github.com/NousResearch/hermes-agent/pull/1"],
                        "github_links": ["https://github.com/NousResearch/hermes-agent/pull/1"],
                        "pull_request_links": ["https://github.com/NousResearch/hermes-agent/pull/1"],
                    }
                ],
                "links": ["https://github.com/NousResearch/hermes-agent/pull/1"],
                "github_links": ["https://github.com/NousResearch/hermes-agent/pull/1"],
                "pull_request_links": ["https://github.com/NousResearch/hermes-agent/pull/1"],
            },
            {
                "messages": [
                    {
                        "id": "m1",
                        "text": "same message",
                        "links": ["https://github.com/NousResearch/hermes-agent/pull/1"],
                        "github_links": ["https://github.com/NousResearch/hermes-agent/pull/1"],
                        "pull_request_links": ["https://github.com/NousResearch/hermes-agent/pull/1"],
                    },
                    {
                        "id": "m2",
                        "text": "issue",
                        "links": ["https://github.com/NousResearch/hermes-agent/issues/2"],
                        "github_links": ["https://github.com/NousResearch/hermes-agent/issues/2"],
                        "pull_request_links": [],
                    },
                ],
                "links": ["https://github.com/NousResearch/hermes-agent/issues/2"],
                "github_links": ["https://github.com/NousResearch/hermes-agent/issues/2"],
                "pull_request_links": [],
                "scroll": {"top": 12},
            },
        ]
    )

    assert merged["message_count"] == 2
    assert merged["github_link_count"] == 2
    assert merged["pull_request_count"] == 1
    assert merged["pull_request_links"] == ["https://github.com/NousResearch/hermes-agent/pull/1"]
    assert merged["last_scroll"] == {"top": 12}


def test_scrape_window_filters_since_and_sorts_forward():
    monitor = _load_monitor()

    merged = monitor._merge_scrape_pages(
        [
            {
                "messages": [
                    {"id": "new", "text": "new", "timestamp": "2026-04-24T02:00:00+00:00", "links": ["https://github.com/new/repo"]},
                    {"id": "old", "text": "old", "timestamp": "2026-04-22T23:00:00+00:00", "links": ["https://github.com/old/repo"]},
                    {
                        "id": "mid",
                        "text": "mid",
                        "timestamp": "2026-04-23T12:00:00+00:00",
                        "links": ["https://github.com/NousResearch/hermes-agent/pull/42"],
                        "github_links": ["https://github.com/NousResearch/hermes-agent/pull/42"],
                        "pull_request_links": ["https://github.com/NousResearch/hermes-agent/pull/42"],
                    },
                ],
            }
        ]
    )

    filtered = monitor._filter_scrape_window(
        merged,
        since=monitor._parse_datetime_bound("2026-04-23"),
        until=None,
    )

    assert [msg["id"] for msg in filtered["messages"]] == ["mid", "new"]
    assert filtered["message_count"] == 2
    assert filtered["pull_request_links"] == ["https://github.com/NousResearch/hermes-agent/pull/42"]


def test_delta_complete_requires_since_boundary_or_scroll_exhaustion():
    monitor = _load_monitor()

    assert not monitor._delta_complete(since=monitor._parse_datetime_bound("2026-04-23"), stop_reason="max_pages")
    assert monitor._delta_complete(since=monitor._parse_datetime_bound("2026-04-23"), stop_reason="since_reached")
    assert monitor._delta_complete(since=monitor._parse_datetime_bound("2026-04-23"), stop_reason="scroll_exhausted")
    assert monitor._delta_complete(since=None, stop_reason="max_pages")


def test_headless_profile_clone_excludes_chromium_lock_files(tmp_path):
    monitor = _load_monitor()
    source = tmp_path / "source-profile"
    runtime = tmp_path / "runtime"
    source.mkdir()
    (source / "Default").mkdir()
    (source / "Default" / "Cookies").write_text("cookie-db", encoding="utf-8")
    (source / "SingletonLock").write_text("old-pod", encoding="utf-8")
    (source / "Lockfile").write_text("old-pod", encoding="utf-8")

    monitor.PROFILE_DIR = source
    monitor.RUNTIME_DIR = runtime

    clone = monitor._prepare_browser_profile(visible=False)

    assert clone == runtime / "chromium-profile"
    assert (clone / "Default" / "Cookies").read_text(encoding="utf-8") == "cookie-db"
    assert not (clone / "SingletonLock").exists()
    assert not (clone / "Lockfile").exists()
    assert (source / "SingletonLock").exists()
