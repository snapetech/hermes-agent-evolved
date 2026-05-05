import json
import urllib.error

from tools import discord_history_tool as tool


class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()

    def close(self):
        return None


def test_discord_channel_history_reads_messages(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["auth"] = req.headers.get("Authorization")
        seen["timeout"] = timeout
        return _Resp([
            {
                "id": "102",
                "timestamp": "2026-04-21T16:02:00+00:00",
                "author": {"id": "u2", "username": "bob"},
                "content": "newer",
                "attachments": [{"id": "a1", "filename": "log.txt", "url": "https://cdn.discordapp.com/log.txt"}],
            },
            {
                "id": "101",
                "timestamp": "2026-04-21T16:01:00+00:00",
                "author": {"id": "u1", "username": "alice"},
                "content": "older",
            },
        ])

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token-123")
    monkeypatch.setattr(tool.urllib.request, "urlopen", fake_urlopen)

    result = json.loads(tool.discord_channel_history({"channel": "123456789", "limit": 2}))

    assert result["channel_id"] == "123456789"
    assert result["count"] == 2
    assert [m["id"] for m in result["messages"]] == ["101", "102"]
    assert result["messages"][1]["attachments"][0]["filename"] == "log.txt"
    assert "limit=2" in seen["url"]
    assert seen["auth"] == "Bot token-123"
    assert seen["timeout"] == 20


def test_discord_channel_history_resolves_channel_name_from_directory(tmp_path, monkeypatch):
    (tmp_path / "channel_directory.json").write_text(
        json.dumps({"discord": [{"id": "555", "name": "hermes"}]}),
        encoding="utf-8",
    )

    import hermes_constants

    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token-123")
    monkeypatch.setattr(tool.urllib.request, "urlopen", lambda *_args, **_kwargs: _Resp([]))

    result = json.loads(tool.discord_channel_history({"channel": "#hermes"}))

    assert result["channel_id"] == "555"


def test_discord_channel_history_reports_permission_error(monkeypatch):
    def fake_urlopen(req, timeout=0):
        raise urllib.error.HTTPError(
            req.full_url,
            403,
            "Forbidden",
            hdrs={},
            fp=_Resp({"message": "Missing Access"}),
        )

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token-123")
    monkeypatch.setattr(tool.urllib.request, "urlopen", fake_urlopen)

    result = json.loads(tool.discord_channel_history({"channel": "123456789"}))

    assert "error" in result
    assert "Read Message History" in result["error"]


def test_discord_channel_history_requires_channel_or_home(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token-123")
    monkeypatch.delenv("DISCORD_HOME_CHANNEL", raising=False)

    result = json.loads(tool.discord_channel_history({}))

    assert "error" in result
    assert "DISCORD_HOME_CHANNEL" in result["error"]
