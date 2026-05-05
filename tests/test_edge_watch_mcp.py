from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest


MCP_PATH = Path(__file__).resolve().parent.parent / "deploy/k8s/edge-watch-mcp.py"


@pytest.fixture
def edge_mcp(tmp_path, monkeypatch):
    db = tmp_path / "hermes_watch.db"
    monkeypatch.setenv("HERMES_EDGE_WATCH_DB", str(db))
    monkeypatch.setenv("HERMES_EDGE_WATCH_REPORTS_DIR", str(tmp_path / "reports"))
    spec = importlib.util.spec_from_file_location("edge_watch_mcp", MCP_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["edge_watch_mcp"] = module
    spec.loader.exec_module(module)
    return module


def _seed(db: Path) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE findings (
              id TEXT PRIMARY KEY,
              source_family TEXT NOT NULL,
              source_name TEXT NOT NULL,
              url TEXT NOT NULL,
              title TEXT NOT NULL,
              author TEXT,
              published_at TEXT,
              seen_at TEXT NOT NULL,
              content_type TEXT NOT NULL,
              repo TEXT,
              subsystem_tags_json TEXT NOT NULL,
              platform_tags_json TEXT NOT NULL,
              artifact_tags_json TEXT NOT NULL,
              summary TEXT NOT NULL,
              evidence_snippets_json TEXT NOT NULL,
              novelty_score REAL NOT NULL,
              importance_score REAL NOT NULL,
              severity_score REAL NOT NULL,
              confidence_score REAL NOT NULL,
              final_score REAL NOT NULL,
              dedupe_cluster_id TEXT,
              related_urls_json TEXT NOT NULL,
              upstream_reference_json TEXT NOT NULL,
              raw_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO findings VALUES (
              'f1', 'github', 'GitHub Releases', 'https://example.test/release',
              'Release v1', NULL, NULL, '2099-01-01T00:00:00+00:00',
              'release', 'NousResearch/hermes-agent',
              '["gateway"]', '[]', '["new-capability"]',
              'summary', '[]', 0.7, 1.0, 0.2, 1.0, 1.0,
              'c1', '[]', '{}', '{}'
            )
            """
        )


def test_recent_returns_findings(edge_mcp):
    _seed(edge_mcp.WATCH_DB_PATH)
    rows = edge_mcp._query({"since": "1d", "limit": 5})
    assert rows[0]["title"] == "Release v1"
    assert rows[0]["subsystem_tags"] == ["gateway"]


def test_alerts_apply_default_threshold(edge_mcp):
    _seed(edge_mcp.WATCH_DB_PATH)
    rows = edge_mcp._query({"since": "1d"}, alerts=True)
    assert len(rows) == 1


def test_digest_reads_latest(edge_mcp, tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "daily-2099-01-01.md").write_text("# Digest\n", encoding="utf-8")
    payload = edge_mcp._digest({"kind": "daily"})
    assert payload["content"] == "# Digest\n"


def test_tools_list_includes_trigger(edge_mcp):
    response = edge_mcp._handle("tools/list", {})
    names = {tool["name"] for tool in response["tools"]}
    assert "edge_watch.recent" in names
    assert "edge_watch.trigger" in names
