"""Tests for the local desktop bridge MCP helper."""

from __future__ import annotations

import importlib.util
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BRIDGE = ROOT / "deploy" / "k8s" / "desktop-bridge-mcp.py"


def _load_bridge():
    spec = importlib.util.spec_from_file_location("desktop_bridge_mcp", BRIDGE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_status_reports_disabled_control_and_audio_by_default(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.delenv("DESKTOP_BRIDGE_ALLOW_CONTROL", raising=False)
    monkeypatch.delenv("DESKTOP_BRIDGE_ALLOW_AUDIO", raising=False)

    status = bridge.call_local_tool("desktop.status", {})

    assert status["ok"] is True
    assert status["control_enabled"] is False
    assert status["audio_enabled"] is False
    assert "xdotool" in status["commands"]
    assert "wtype" in status["commands"]
    assert "kdotool" in status["commands"]
    assert set(status["input_backends"]) == {"type", "hotkey", "move", "click"}


def test_control_tools_are_gated_by_default(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.delenv("DESKTOP_BRIDGE_ALLOW_CONTROL", raising=False)

    try:
        bridge.call_local_tool("desktop.click", {"x": 1, "y": 2})
    except RuntimeError as exc:
        assert "desktop control is disabled" in str(exc)
    else:
        raise AssertionError("desktop.click should require explicit control opt-in")


def test_audio_tools_are_gated_by_default(monkeypatch, tmp_path):
    bridge = _load_bridge()
    monkeypatch.delenv("DESKTOP_BRIDGE_ALLOW_AUDIO", raising=False)

    try:
        bridge.call_local_tool("desktop.audio_play", {"path": str(tmp_path / "missing.wav")})
    except RuntimeError as exc:
        assert "audio tools are disabled" in str(exc)
    else:
        raise AssertionError("desktop.audio_play should require explicit audio opt-in")


def test_mcp_lists_read_and_control_tools():
    bridge = _load_bridge()

    response = bridge._handle_mcp({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

    assert response["id"] == 1
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert "desktop.screenshot" in names
    assert "desktop.ocr" in names
    assert "desktop.click" in names
    assert "desktop.audio_capture" in names


def test_mcp_redacts_bridge_token(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setenv("DESKTOP_BRIDGE_TOKEN", "secret-token")

    result = bridge._mcp_result({"authorization": "Bearer secret-token", "nested": ["secret-token"]})
    text = result["content"][0]["text"]
    payload = json.loads(text)

    assert payload["authorization"] == "[REDACTED]"
    assert payload["nested"] == ["[REDACTED]"]
    assert "secret-token" not in text


def test_http_server_requires_token_when_bound_off_loopback(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setenv("DESKTOP_BRIDGE_HOST", "0.0.0.0")
    monkeypatch.delenv("DESKTOP_BRIDGE_TOKEN", raising=False)

    try:
        bridge.run_http()
    except RuntimeError as exc:
        assert "DESKTOP_BRIDGE_TOKEN is required" in str(exc)
    else:
        raise AssertionError("non-loopback HTTP bridge should require a token")


# --- backend selection --------------------------------------------------

def test_pick_input_backend_prefers_wtype_on_wayland(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("DESKTOP_BRIDGE_INPUT_BACKEND", "auto")

    available = {"wtype": "/usr/bin/wtype", "ydotool": "/usr/bin/ydotool", "xdotool": "/usr/bin/xdotool"}
    monkeypatch.setattr(bridge.shutil, "which", lambda name: available.get(name))

    assert bridge._pick_input_backend("type") == "wtype"
    assert bridge._pick_input_backend("hotkey") == "wtype"
    # wtype has no mouse; fallback for move/click is ydotool when available
    assert bridge._pick_input_backend("move") == "ydotool"
    assert bridge._pick_input_backend("click") == "ydotool"


def test_pick_input_backend_prefers_xdotool_on_x11(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("DESKTOP_BRIDGE_INPUT_BACKEND", "auto")

    available = {"wtype": "/usr/bin/wtype", "ydotool": "/usr/bin/ydotool", "xdotool": "/usr/bin/xdotool"}
    monkeypatch.setattr(bridge.shutil, "which", lambda name: available.get(name))

    assert bridge._pick_input_backend("type") == "xdotool"
    assert bridge._pick_input_backend("hotkey") == "xdotool"
    assert bridge._pick_input_backend("move") == "xdotool"


def test_pick_input_backend_skips_ydotool_for_hotkey(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DESKTOP_BRIDGE_INPUT_BACKEND", "auto")

    # only ydotool available — hotkey must fail rather than emit raw keycodes.
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/usr/bin/ydotool" if name == "ydotool" else None)

    assert bridge._pick_input_backend("type") == "ydotool"
    assert bridge._pick_input_backend("hotkey") is None


def test_type_routes_through_wtype_on_wayland(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setenv("DESKTOP_BRIDGE_ALLOW_CONTROL", "1")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DESKTOP_BRIDGE_INPUT_BACKEND", "auto")
    monkeypatch.delenv("DESKTOP_BRIDGE_ALLOWED_WINDOW_RE", raising=False)

    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/usr/bin/wtype" if name == "wtype" else None)

    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return {"ok": True, "exit_code": 0, "stdout": "", "stderr": "", "command": cmd}

    monkeypatch.setattr(bridge, "_run", fake_run)

    result = bridge.call_local_tool("desktop.type", {"text": "hello", "delay_ms": 7})

    assert result["backend"] == "wtype"
    assert result["typed"] == 5
    assert captured["cmd"][0] == "wtype"
    assert "-d" in captured["cmd"]
    assert "hello" in captured["cmd"]


def test_hotkey_routes_through_wtype_with_modifiers(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setenv("DESKTOP_BRIDGE_ALLOW_CONTROL", "1")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DESKTOP_BRIDGE_INPUT_BACKEND", "auto")
    monkeypatch.delenv("DESKTOP_BRIDGE_ALLOWED_WINDOW_RE", raising=False)

    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/usr/bin/wtype" if name == "wtype" else None)

    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return {"ok": True, "exit_code": 0, "stdout": "", "stderr": "", "command": cmd}

    monkeypatch.setattr(bridge, "_run", fake_run)

    bridge.call_local_tool("desktop.hotkey", {"keys": "ctrl+shift+Return"})

    cmd = captured["cmd"]
    assert cmd[0] == "wtype"
    # modifier pressed then released
    assert cmd.count("-M") == 2
    assert cmd.count("-m") == 2
    assert "-k" in cmd
    primary_idx = cmd.index("-k")
    assert cmd[primary_idx + 1] == "Return"


def test_hotkey_can_target_window_id_without_active_focus(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setenv("DESKTOP_BRIDGE_ALLOW_CONTROL", "1")
    monkeypatch.setenv("DESKTOP_BRIDGE_ALLOWED_WINDOW_RE", "Discord")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/usr/bin/xdotool" if name == "xdotool" else None)

    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        if cmd[:2] == ["xdotool", "getwindowname"]:
            return {"ok": True, "stdout": "#github-tracker | Nous Research - Discord", "exit_code": 0, "stderr": "", "command": cmd}
        if cmd[:2] == ["xdotool", "getwindowclassname"]:
            return {"ok": True, "stdout": "discord", "exit_code": 0, "stderr": "", "command": cmd}
        if cmd[:2] == ["xdotool", "getwindowpid"]:
            return {"ok": True, "stdout": "86896", "exit_code": 0, "stderr": "", "command": cmd}
        return {"ok": True, "exit_code": 0, "stdout": "", "stderr": "", "command": cmd}

    monkeypatch.setattr(bridge, "_run", fake_run)

    result = bridge.call_local_tool("desktop.hotkey", {"keys": "Page_Up", "window_id": "16777227"})

    assert result["backend"] == "xdotool-window"
    assert ["xdotool", "key", "--window", "16777227", "--clearmodifiers", "Page_Up"] in calls
    assert ["xdotool", "getactivewindow"] not in calls


def test_type_can_target_window_id_without_active_focus(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setenv("DESKTOP_BRIDGE_ALLOW_CONTROL", "1")
    monkeypatch.setenv("DESKTOP_BRIDGE_ALLOWED_WINDOW_RE", "Discord")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/usr/bin/xdotool" if name == "xdotool" else None)

    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        if cmd[:2] == ["xdotool", "getwindowname"]:
            return {"ok": True, "stdout": "#github-tracker | Nous Research - Discord", "exit_code": 0, "stderr": "", "command": cmd}
        if cmd[:2] == ["xdotool", "getwindowclassname"]:
            return {"ok": True, "stdout": "discord", "exit_code": 0, "stderr": "", "command": cmd}
        if cmd[:2] == ["xdotool", "getwindowpid"]:
            return {"ok": True, "stdout": "86896", "exit_code": 0, "stderr": "", "command": cmd}
        return {"ok": True, "exit_code": 0, "stdout": "", "stderr": "", "command": cmd}

    monkeypatch.setattr(bridge, "_run", fake_run)

    result = bridge.call_local_tool("desktop.type", {"text": "github-tracker", "delay_ms": 12, "window_id": "16777227"})

    assert result["backend"] == "xdotool-window"
    assert result["typed"] == len("github-tracker")
    assert ["xdotool", "type", "--window", "16777227", "--delay", "12", "--", "github-tracker"] in calls
    assert ["xdotool", "getactivewindow"] not in calls


def test_hotkey_accepts_space_and_comma(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setenv("DESKTOP_BRIDGE_ALLOW_CONTROL", "1")
    monkeypatch.delenv("DESKTOP_BRIDGE_ALLOWED_WINDOW_RE", raising=False)
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/usr/bin/xdotool" if name == "xdotool" else None)

    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return {"ok": True, "exit_code": 0, "stdout": "", "stderr": "", "command": cmd}

    monkeypatch.setattr(bridge, "_run", fake_run)

    bridge.call_local_tool("desktop.hotkey", {"keys": "ctrl+space"})
    assert "ctrl+space" in captured["cmd"]


def test_hotkey_rejects_shell_metacharacters(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setenv("DESKTOP_BRIDGE_ALLOW_CONTROL", "1")
    monkeypatch.delenv("DESKTOP_BRIDGE_ALLOWED_WINDOW_RE", raising=False)
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/usr/bin/xdotool" if name == "xdotool" else None)

    try:
        bridge.call_local_tool("desktop.hotkey", {"keys": "ctrl+l;rm -rf /"})
    except RuntimeError as exc:
        assert "alphanumeric" in str(exc).lower() or "unsupported" in str(exc).lower()
    else:
        raise AssertionError("shell-meta hotkey must be rejected")


def test_activate_window_rejects_shell_metacharacters(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/usr/bin/wmctrl" if name == "wmctrl" else None)

    try:
        bridge.call_local_tool("desktop.activate_window", {"pattern": "discord; rm -rf /"})
    except RuntimeError as exc:
        assert "unsupported" in str(exc).lower()
    else:
        raise AssertionError("shell-meta pattern must be rejected")


def test_activate_window_prefers_wmctrl_class(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/usr/bin/wmctrl" if name == "wmctrl" else None)

    captured: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        captured.append(cmd)
        return {"ok": True, "exit_code": 0, "stdout": "", "stderr": "", "command": cmd}

    monkeypatch.setattr(bridge, "_run", fake_run)

    result = bridge.call_local_tool("desktop.activate_window", {"pattern": "discord.discord"})
    assert result["backend"] == "wmctrl"
    assert result["match"] == "class"
    assert captured[0] == ["wmctrl", "-x", "-a", "discord.discord"]


def test_launch_app_validates_app_id(monkeypatch):
    bridge = _load_bridge()
    try:
        bridge.call_local_tool("desktop.launch_app", {"app": "discord && rm -rf /"})
    except RuntimeError as exc:
        assert "alphanumeric" in str(exc).lower()
    else:
        raise AssertionError("bad app id must be rejected")


def test_find_window_returns_xdotool_hits(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/usr/bin/xdotool" if name == "xdotool" else None)

    def fake_run(cmd, **_kwargs):
        if cmd[:3] == ["xdotool", "search", "--onlyvisible"] and "--class" in cmd:
            return {"ok": True, "stdout": "16777227\n", "exit_code": 0, "stderr": "", "command": cmd}
        if cmd[:2] == ["xdotool", "getwindowname"]:
            return {"ok": True, "stdout": "#github-tracker | Nous Research - Discord", "exit_code": 0, "stderr": "", "command": cmd}
        if cmd[:2] == ["xdotool", "getwindowpid"]:
            return {"ok": True, "stdout": "86896", "exit_code": 0, "stderr": "", "command": cmd}
        if cmd[:2] == ["xdotool", "getwindowgeometry"]:
            return {"ok": True, "stdout": "WINDOW=16777227\nX=0\nY=72\nWIDTH=3840\nHEIGHT=2088\nSCREEN=0\n", "exit_code": 0, "stderr": "", "command": cmd}
        return {"ok": False, "stdout": "", "stderr": "", "exit_code": 1, "command": cmd}

    monkeypatch.setattr(bridge, "_run", fake_run)

    found = bridge.call_local_tool("desktop.find_window", {"pattern": "discord", "match": "class"})
    assert found["count"] == 1
    w = found["windows"][0]
    assert w["id"] == "16777227"
    assert w["title"].startswith("#github-tracker")
    assert w["width"] == 3840
    assert w["match"] == "class"


def test_screenshot_window_id_prefers_xwd_without_import(monkeypatch, tmp_path):
    bridge = _load_bridge()
    tools = {"xwd": "/usr/bin/xwd", "magick": "/usr/bin/magick"}
    monkeypatch.setattr(bridge.shutil, "which", lambda name: tools.get(name))

    captured: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        captured.append(cmd)
        if cmd[0] == "/usr/bin/xwd":
            Path(cmd[-1]).write_bytes(b"xwd")
        else:
            Path(cmd[-1]).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 200)
        return {"ok": True, "stdout": "", "stderr": "", "exit_code": 0, "command": cmd}

    monkeypatch.setattr(bridge, "_run", fake_run)

    out = tmp_path / "discord.png"
    result = bridge.call_local_tool(
        "desktop.screenshot",
        {"path": str(out), "window_id": "16777227"},
    )
    assert result["mime_type"] == "image/png"
    assert captured[0][:4] == ["/usr/bin/xwd", "-silent", "-id", "16777227"]
    assert captured[1][:2] == ["/usr/bin/magick", "convert"]


def test_screenshot_window_id_blocks_import_fallback_by_default(monkeypatch, tmp_path):
    bridge = _load_bridge()
    monkeypatch.delenv("DESKTOP_BRIDGE_ALLOW_IMPORT_WINDOW_CAPTURE", raising=False)
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/usr/bin/import" if name == "import" else None)

    try:
        bridge.call_local_tool(
            "desktop.screenshot",
            {"path": str(tmp_path / "discord.png"), "window_id": "16777227"},
        )
    except RuntimeError as exc:
        assert "switch virtual desktops" in str(exc)
    else:
        raise AssertionError("import fallback should be opt-in")


def test_screenshot_screen_crop_uses_root_capture_and_geometry(monkeypatch, tmp_path):
    bridge = _load_bridge()
    monkeypatch.setenv("DISPLAY", ":0")
    tools = {
        "xdotool": "/usr/bin/xdotool",
        "spectacle": "/usr/bin/spectacle",
        "magick": "/usr/bin/magick",
    }
    monkeypatch.setattr(bridge.shutil, "which", lambda name: tools.get(name))

    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        if cmd[:3] == ["xdotool", "getwindowgeometry", "--shell"]:
            return {"ok": True, "stdout": "X=10\nY=20\nWIDTH=300\nHEIGHT=200\n", "exit_code": 0, "stderr": "", "command": cmd}
        if cmd[0] == "spectacle":
            Path(cmd[-1]).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 200)
            return {"ok": True, "stdout": "", "stderr": "", "exit_code": 0, "command": cmd}
        if cmd[0] == "/usr/bin/magick":
            Path(cmd[-1]).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 200)
            return {"ok": True, "stdout": "", "stderr": "", "exit_code": 0, "command": cmd}
        return {"ok": False, "stdout": "", "stderr": "", "exit_code": 1, "command": cmd}

    monkeypatch.setattr(bridge, "_run", fake_run)

    out = tmp_path / "discord.png"
    result = bridge.call_local_tool(
        "desktop.screenshot",
        {"path": str(out), "window_id": "16777227", "capture_strategy": "screen_crop"},
    )

    assert result["region"] == {"x": 10, "y": 20, "w": 300, "h": 200}
    assert any(call[:3] == ["xdotool", "getwindowgeometry", "--shell"] for call in calls)
    assert any(call[:3] == ["spectacle", "-n", "-b"] for call in calls)
    assert any("-crop" in call and "300x200+10+20" in call for call in calls)
    assert out.exists()


def test_screenshot_window_id_rejects_garbage(monkeypatch, tmp_path):
    bridge = _load_bridge()
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/usr/bin/import" if name == "import" else None)

    try:
        bridge.call_local_tool(
            "desktop.screenshot",
            {"path": str(tmp_path / "x.png"), "window_id": "; rm -rf /"},
        )
    except RuntimeError as exc:
        assert "window_id" in str(exc)
    else:
        raise AssertionError("invalid window_id must be rejected")


def test_focus_save_and_restore_round_trip(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setenv("DISPLAY", ":0")
    bridge._focus_stack.clear()
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/usr/bin/xdotool" if name == "xdotool" else None)

    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        if cmd == ["xdotool", "getactivewindow"]:
            return {"ok": True, "stdout": "2097152", "exit_code": 0, "stderr": "", "command": cmd}
        return {"ok": True, "stdout": "", "exit_code": 0, "stderr": "", "command": cmd}

    monkeypatch.setattr(bridge, "_run", fake_run)

    saved = bridge.call_local_tool("desktop.save_focus", {})
    assert saved == {"saved_id": "2097152", "stack_depth": 1}

    restored = bridge.call_local_tool("desktop.restore_focus", {})
    assert restored["restored_id"] == "2097152"
    assert restored["stack_depth"] == 0
    assert ["xdotool", "windowactivate", "--sync", "2097152"] in calls


def test_ocr_flags_truncation(monkeypatch, tmp_path):
    bridge = _load_bridge()
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/usr/bin/tesseract" if name == "tesseract" else None)

    image = tmp_path / "screenshot.png"
    image.write_bytes(b"not-really-a-png")

    big_text = "a" * 150
    monkeypatch.setattr(bridge, "_run", lambda cmd, **_kwargs: {"ok": True, "exit_code": 0, "stdout": big_text, "stderr": "", "command": cmd})

    result = bridge.call_local_tool("desktop.ocr", {"path": str(image), "max_chars": 100})
    assert result["truncated"] is True
    assert result["char_count"] == 100
    assert len(result["text"]) == 100


def test_init_and_print_pod_env(monkeypatch, tmp_path, capsys):
    bridge = _load_bridge()
    token_path = tmp_path / "token"

    assert bridge.cmd_init(["--path", str(token_path)]) == 0
    token = token_path.read_text().strip()
    assert len(token) == 64
    assert oct(token_path.stat().st_mode)[-3:] == "600"

    # second init without --force refuses
    assert bridge.cmd_init(["--path", str(token_path)]) == 1
    # with --force it rotates
    assert bridge.cmd_init(["--path", str(token_path), "--force"]) == 0
    new_token = token_path.read_text().strip()
    assert new_token != token

    capsys.readouterr()
    assert bridge.cmd_print_pod_env(["--url", "http://desktop.local:8765", "--token-file", str(token_path)]) == 0
    out = capsys.readouterr().out
    assert "DESKTOP_BRIDGE_URL=http://desktop.local:8765" in out
    assert f"DESKTOP_BRIDGE_TOKEN={new_token}" in out


# --- end-to-end HTTP roundtrip --------------------------------------------

def _http_json(method: str, url: str, token: str | None = None, body: dict | None = None) -> tuple[int, dict]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_http_health_tools_and_call_roundtrip(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setenv("DESKTOP_BRIDGE_TOKEN", "integration-token")

    server = ThreadingHTTPServer(("127.0.0.1", 0), bridge.DesktopBridgeHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        # /health is unauthenticated but returns status
        status, body = _http_json("GET", f"{base}/health")
        assert status == 200
        assert body["ok"] is True
        assert body["server"]["name"] == "hermes-desktop-bridge"

        # /tools requires token
        status, body = _http_json("GET", f"{base}/tools")
        assert status == 401
        status, body = _http_json("GET", f"{base}/tools", token="integration-token")
        assert status == 200
        names = {tool["name"] for tool in body["tools"]}
        assert "desktop.status" in names

        # /call requires token, executes locally
        status, body = _http_json(
            "POST",
            f"{base}/call",
            token="integration-token",
            body={"name": "desktop.status", "args": {}},
        )
        assert status == 200
        assert body["ok"] is True
        assert body["result"]["ok"] is True
        assert set(body["result"]["input_backends"]) == {"type", "hotkey", "move", "click"}

        # bogus token rejected
        status, body = _http_json(
            "POST",
            f"{base}/call",
            token="wrong",
            body={"name": "desktop.status", "args": {}},
        )
        assert status == 401

        # unknown tool surfaces a 500 with a readable error
        status, body = _http_json(
            "POST",
            f"{base}/call",
            token="integration-token",
            body={"name": "desktop.does-not-exist", "args": {}},
        )
        assert status == 500
        assert "unknown tool" in body["error"].lower()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        # give the daemon thread a tick to exit cleanly
        time.sleep(0.01)
