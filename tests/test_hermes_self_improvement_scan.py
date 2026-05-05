"""Tests for the Hermes edge-watch scout script.

The scout lives at deploy/k8s/hermes-self-improvement-scan.py (it is loaded by
path inside the CronJob container, not imported as a package module), so these
tests use importlib.util to load it by path.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


SCAN_PATH = Path(__file__).resolve().parent.parent / "deploy/k8s/hermes-self-improvement-scan.py"


@pytest.fixture(scope="module")
def scout(tmp_path_factory):
    """Load the scout module with a scratch state dir so import-time paths are safe."""
    state = tmp_path_factory.mktemp("scout-state")
    os.environ["HERMES_SELF_IMPROVEMENT_STATE_DIR"] = str(state)
    spec = importlib.util.spec_from_file_location("hermes_self_improvement_scan", SCAN_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["hermes_self_improvement_scan"] = module
    spec.loader.exec_module(module)
    return module


class TestRedact:
    def test_github_pat_redacted(self, scout):
        fake_pat = "ghp_" + "a" * 36
        text = f"token: {fake_pat}"
        out = scout.redact(text)
        assert fake_pat not in out
        assert "[REDACTED]" in out

    def test_bearer_redacted(self, scout):
        fake_key = "sk-" + "A" * 32
        out = scout.redact(f"sent Bearer {fake_key} to api")
        assert fake_key not in out

    def test_authorization_bearer_redacted(self, scout):
        fake_key = "abcDEF0123456789" * 2
        out = scout.redact(f"Authorization: Bearer {fake_key}")
        assert fake_key not in out
        assert "Bearer" not in out

    def test_oauth2_url_redacted(self, scout):
        out = scout.redact("https://oauth2:secrettoken123@gitlab.example/repo.git")
        assert "secrettoken123" not in out
        assert "[REDACTED]" in out

    def test_clean_text_untouched(self, scout):
        text = "nothing sensitive here, just words"
        assert scout.redact(text) == text


class TestInferTags:
    def test_gateway_and_mcp_tags(self, scout):
        subsystem, platform, artifact = scout.infer_tags("The gateway MCP bridge crashed with an error")
        assert "gateway" in subsystem
        assert "mcp" in subsystem
        assert "bug" in artifact

    def test_discord_platform(self, scout):
        _, platform, _ = scout.infer_tags("Discord webhook fix landed")
        assert "discord" in platform

    def test_security_artifact(self, scout):
        _, _, artifact = scout.infer_tags("Token redaction patch for auth leak")
        assert "security" in artifact

    def test_no_tags_on_unrelated(self, scout):
        s, p, a = scout.infer_tags("the quick brown fox")
        assert s == [] and p == [] and a == []


class TestScoreFinding:
    def test_release_gets_boost(self, scout):
        novelty, importance, severity, confidence, final = scout.score_finding(
            "github", "release", ["gateway"], [], []
        )
        assert importance == 1.0
        assert final > 0.9

    def test_security_severity_maxed(self, scout):
        _, _, severity, _, _ = scout.score_finding(
            "github", "pr", ["gateway"], [], ["security"]
        )
        assert severity == 1.0

    def test_discord_low_importance(self, scout):
        _, importance, _, confidence, _ = scout.score_finding(
            "discord", "discord_message", ["skills"], ["discord"], []
        )
        assert importance == 0.55
        assert confidence == 0.85

    def test_official_docs_doc_change_boost(self, scout):
        _, _, _, _, final_plain = scout.score_finding(
            "official_docs", "doc_change", ["mcp"], [], []
        )
        _, _, _, _, final_feat = scout.score_finding(
            "official_docs", "doc_change", ["mcp"], [], ["new-capability"]
        )
        assert final_feat > final_plain

    def test_release_alerts_only_when_first_seen(self, scout):
        finding = {
            "content_type": "release",
            "first_seen": True,
            "raw": {},
            "final_score": 0.97,
            "artifact_tags": [],
        }

        assert scout.should_immediate_alert(finding) is True
        finding["first_seen"] = False
        assert scout.should_immediate_alert(finding) is False

    def test_docs_baseline_does_not_immediate_alert(self, scout):
        finding = {
            "content_type": "doc_change",
            "first_seen": True,
            "raw": {"marker": "new"},
            "final_score": 0.96,
            "artifact_tags": ["docs-change"],
        }

        assert scout.should_immediate_alert(finding) is False
        finding["first_seen"] = False
        finding["raw"]["marker"] = "changed"
        assert scout.should_immediate_alert(finding) is True

    def test_repeated_security_finding_does_not_realert(self, scout):
        finding = {
            "content_type": "commit",
            "first_seen": False,
            "raw": {},
            "final_score": 0.64,
            "artifact_tags": ["security"],
        }

        assert scout.should_immediate_alert(finding) is False
        finding["first_seen"] = True
        assert scout.should_immediate_alert(finding) is True


class TestIsCrosspostRelay:
    def test_webhook_plus_flag_is_relay(self, scout):
        msg = {"webhook_id": "123", "flags": 2}
        assert scout._is_crosspost_relay(msg) is True

    def test_webhook_plus_reference_is_relay(self, scout):
        msg = {"webhook_id": "123", "message_reference": {"guild_id": "4"}}
        assert scout._is_crosspost_relay(msg) is True

    def test_plain_webhook_without_flag_or_ref_is_not_relay(self, scout):
        msg = {"webhook_id": "123", "flags": 0}
        assert scout._is_crosspost_relay(msg) is False

    def test_user_message_not_relay(self, scout):
        msg = {"flags": 2}
        assert scout._is_crosspost_relay(msg) is False

    def test_garbage_flags_tolerated(self, scout):
        msg = {"webhook_id": "x", "flags": "not-a-number", "message_reference": {"guild_id": "1"}}
        assert scout._is_crosspost_relay(msg) is True


class TestExtractLinks:
    def test_plain_http_links_extracted(self, scout):
        text = "see https://example.com/a and https://example.com/b."
        links = scout._extract_links(text)
        assert "https://example.com/a" in links
        assert "https://example.com/b" in links

    def test_trailing_punctuation_stripped(self, scout):
        links = scout._extract_links("https://example.com/x.")
        assert links == ["https://example.com/x"]

    def test_embed_urls_collected(self, scout):
        msg = {"embeds": [{"url": "https://hf.co/model", "fields": [{"value": "see https://arxiv.org/abs/1"}]}]}
        links = scout._extract_links("", msg)
        assert "https://hf.co/model" in links
        assert "https://arxiv.org/abs/1" in links

    def test_duplicates_deduped(self, scout):
        links = scout._extract_links("https://x.com/a https://x.com/a")
        assert links == ["https://x.com/a"]


class TestParseFrontMatter:
    def test_parses_simple_scalar(self, scout):
        text = '---\ntitle: Hello\nsource: manual\n---\nbody text'
        meta, body = scout._parse_front_matter(text)
        assert meta == {"title": "Hello", "source": "manual"}
        assert body == "body text"

    def test_parses_list(self, scout):
        text = '---\ntags: [mcp, gateway, "provider-routing"]\n---\nbody'
        meta, _ = scout._parse_front_matter(text)
        assert meta["tags"] == ["mcp", "gateway", "provider-routing"]

    def test_no_front_matter_returned_raw(self, scout):
        meta, body = scout._parse_front_matter("no frontmatter here")
        assert meta == {}
        assert body == "no frontmatter here"

    def test_unterminated_front_matter_returned_raw(self, scout):
        text = "---\ntitle: Unclosed\nbody without end marker"
        meta, body = scout._parse_front_matter(text)
        assert meta == {}
        assert body == text


class TestParsePageSummary:
    def test_title_and_headings_extracted(self, scout):
        html = "<html><head><title>Doc Title</title></head><body><h1>Intro</h1><h2>Usage</h2></body></html>"
        title, headings = scout.parse_page_summary(html)
        assert title == "Doc Title"
        assert "Intro" in headings
        assert "Usage" in headings

    def test_duplicate_headings_collapsed(self, scout):
        html = "<h1>A</h1><h1>A</h1><h2>B</h2>"
        _, headings = scout.parse_page_summary(html)
        assert headings == ["A", "B"]

    def test_empty_html_safe(self, scout):
        title, headings = scout.parse_page_summary("")
        assert title == ""
        assert headings == []
