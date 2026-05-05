import json
import urllib.error

from tools import siem_tool


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def close(self):
        return None


def test_status_fetches_es_health_indices_and_kibana(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout=20):
        calls.append((request.full_url, request.get_method(), timeout))
        if request.full_url.endswith("/_cluster/health"):
            return FakeResponse({"status": "green"})
        if "/_cat/indices" in request.full_url:
            return FakeResponse([{"index": "syslog-2026.04.21"}])
        if request.full_url.endswith("/api/status"):
            return FakeResponse({"status": {"overall": {"level": "available"}}})
        return FakeResponse({"cluster_name": "siem"})

    monkeypatch.setenv("HERMES_SIEM_ELASTICSEARCH_URL", "http://es.test:9200")
    monkeypatch.setenv("HERMES_SIEM_KIBANA_URL", "http://kb.test:5601")
    monkeypatch.setattr(siem_tool.urllib.request, "urlopen", fake_urlopen)

    result = json.loads(siem_tool._siem_query(action="status"))

    assert result["success"] is True
    assert result["elasticsearch_url"] == "http://es.test:9200"
    assert result["health"]["status"] == "green"
    assert result["indices"][0]["index"] == "syslog-2026.04.21"
    assert ("http://kb.test:5601/api/status", "GET", 10) in calls


def test_search_builds_bounded_time_query_and_compacts_hits(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout=20):
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({
            "hits": {
                "total": {"value": 1},
                "hits": [{
                    "_index": "syslog-2026.04.21",
                    "_id": "abc",
                    "_score": 1.0,
                    "_source": {
                        "@timestamp": "2026-04-21T12:00:00Z",
                        "host": {"name": "node-b"},
                        "message": "Failed password for root from 192.0.2.4",
                    },
                }],
            }
        })

    monkeypatch.setenv("HERMES_SIEM_ELASTICSEARCH_URL", "http://es.test:9200")
    monkeypatch.setattr(siem_tool.urllib.request, "urlopen", fake_urlopen)

    result = json.loads(siem_tool._siem_query(
        action="search",
        index_pattern="syslog-*",
        hours=2,
        size=9999,
        query_string="Failed password",
    ))

    assert result["success"] is True
    assert seen["url"] == "http://es.test:9200/syslog-*/_search"
    assert seen["method"] == "POST"
    assert seen["body"]["size"] == 500
    assert seen["body"]["query"]["bool"]["must"][1]["simple_query_string"]["query"] == "Failed password"
    assert result["total"] == 1
    assert result["hits"][0]["host"] == "node-b"
    assert result["hits"][0]["message"].startswith("Failed password")


def test_invalid_index_pattern_is_rejected_without_request(monkeypatch):
    called = False

    def fake_urlopen(request, timeout=20):
        nonlocal called
        called = True
        raise AssertionError("request should not be made")

    monkeypatch.setattr(siem_tool.urllib.request, "urlopen", fake_urlopen)

    result = json.loads(siem_tool._siem_query(action="search", index_pattern="../_all"))

    assert result["success"] is False
    assert "index_pattern" in result["error"]
    assert called is False


def test_api_key_header_uses_siem_env(monkeypatch):
    seen_headers = {}

    def fake_urlopen(request, timeout=20):
        seen_headers.update(dict(request.header_items()))
        return FakeResponse({"ok": True})

    monkeypatch.setenv("HERMES_SIEM_API_KEY", "abc123")
    monkeypatch.setattr(siem_tool.urllib.request, "urlopen", fake_urlopen)

    siem_tool._request_json("GET", "http://es.test:9200/")

    assert seen_headers["Authorization"] == "ApiKey abc123"


def test_http_error_is_returned_as_tool_error(monkeypatch):
    def fake_urlopen(request, timeout=20):
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            hdrs=None,
            fp=FakeResponse({"error": "forbidden"}),
        )

    monkeypatch.setenv("HERMES_SIEM_ELASTICSEARCH_URL", "http://es.test:9200")
    monkeypatch.setattr(siem_tool.urllib.request, "urlopen", fake_urlopen)

    result = json.loads(siem_tool._siem_query(action="status", include_kibana=False))

    assert result["success"] is False
    assert "HTTP 403" in result["error"]
