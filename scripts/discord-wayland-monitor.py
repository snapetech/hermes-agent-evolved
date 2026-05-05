#!/usr/bin/env python3
"""Run a Discord web monitor in an isolated Wayland compositor.

This keeps scraping/automation away from the operator's real KDE Wayland
workspace. Use ``login`` once to open a visible nested Weston window and log in;
then use ``start`` for a headless compositor using the same Chromium profile.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import io
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import websockets


SERVER_INFO = {"name": "hermes-discord-wayland-monitor", "version": "0.1.0"}
STATE_DIR = Path(os.getenv("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "hermes-discord-wayland-monitor"
PROFILE_DIR = Path(os.getenv("HERMES_DISCORD_MONITOR_PROFILE") or STATE_DIR / "chromium-profile")
RUNTIME_DIR = Path(os.getenv("HERMES_DISCORD_MONITOR_RUNTIME") or Path(tempfile.gettempdir()) / f"hermes-discord-wayland-{os.getuid()}")
META_PATH = STATE_DIR / "monitor.json"
DEFAULT_URL = "https://discord.com/channels/@me"
DEFAULT_PORT = 9333
NOUS_GUILD_ID = "1053877538025386074"


def _read_meta() -> dict[str, Any]:
    if not META_PATH.exists():
        return {}
    try:
        return json.loads(META_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_meta(meta: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _is_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _urlopen_json(url: str, timeout: float = 2.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _wait_for_cdp(port: int, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            return _urlopen_json(f"http://127.0.0.1:{port}/json/version", timeout=1.0)
        except Exception as exc:  # noqa: BLE001 - rendered in status if startup fails.
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(f"Chromium CDP did not become ready on port {port}: {last_error}")


def _spawn(args: list[str], *, env: dict[str, str], log_path: Path) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab")
    return subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=env,
    )


def _prepare_browser_profile(*, visible: bool) -> Path:
    if visible:
        return PROFILE_DIR

    # Headless monitoring should not open the logged-in profile directly:
    # rolling updates or parallel runs can otherwise fight Chromium's
    # Singleton* locks. Clone the profile into the runtime dir and drop locks.
    run_profile = RUNTIME_DIR / "chromium-profile"
    if run_profile.exists():
        shutil.rmtree(run_profile)
    if PROFILE_DIR.exists() and any(PROFILE_DIR.iterdir()):
        shutil.copytree(
            PROFILE_DIR,
            run_profile,
            ignore=shutil.ignore_patterns("Singleton*", "Lockfile", "Crashpad", "ShaderCache", "GrShaderCache"),
            symlinks=True,
        )
    else:
        run_profile.mkdir(parents=True, exist_ok=True)
    for pattern in ("Singleton*", "Lockfile"):
        for path in run_profile.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
    return run_profile


def cmd_start(args: argparse.Namespace) -> int:
    meta = _read_meta()
    if _is_alive(meta.get("chromium_pid")) and _is_alive(meta.get("weston_pid")):
        print(json.dumps({"ok": True, "already_running": True, **meta}, indent=2))
        return 0

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    visible = bool(args.visible)
    socket_name = args.socket
    width = int(args.width)
    height = int(args.height)
    port = int(args.port)

    env = os.environ.copy()
    if visible:
        # Nested Weston connects to the current Wayland session and opens one
        # ordinary window for first-time login. It still isolates the browser.
        runtime = Path(env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
        weston_args = [
            "weston",
            "--backend=wayland-backend.so",
            f"--socket={socket_name}",
            f"--width={width}",
            f"--height={height}",
            "--idle-time=0",
        ]
    else:
        runtime = RUNTIME_DIR
        runtime.mkdir(parents=True, exist_ok=True)
        runtime.chmod(0o700)
        env["XDG_RUNTIME_DIR"] = str(runtime)
        weston_args = [
            "weston",
            "--backend=headless-backend.so",
            f"--socket={socket_name}",
            f"--width={width}",
            f"--height={height}",
            "--idle-time=0",
        ]

    weston = _spawn(weston_args, env=env, log_path=STATE_DIR / "weston.log")
    time.sleep(1.5)
    if not _is_alive(weston.pid):
        raise RuntimeError(f"weston exited early; see {STATE_DIR / 'weston.log'}")

    browser_env = env.copy()
    browser_env["WAYLAND_DISPLAY"] = socket_name
    browser_env.pop("DISPLAY", None)
    browser_profile = _prepare_browser_profile(visible=visible)
    chromium_args = [
        "chromium",
        "--ozone-platform=wayland",
        f"--user-data-dir={browser_profile}",
        "--no-first-run",
        "--disable-dev-shm-usage",
        "--remote-allow-origins=*",
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={port}",
        args.url,
    ]
    chromium = _spawn(chromium_args, env=browser_env, log_path=STATE_DIR / "chromium.log")
    version = _wait_for_cdp(port, timeout=30)

    meta = {
        "ok": True,
        "mode": "visible" if visible else "headless",
        "weston_pid": weston.pid,
        "chromium_pid": chromium.pid,
        "runtime_dir": str(runtime),
        "wayland_display": socket_name,
        "cdp_port": port,
        "profile_dir": str(browser_profile),
        "source_profile_dir": str(PROFILE_DIR),
        "url": args.url,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "browser": version.get("Browser"),
    }
    _write_meta(meta)
    print(json.dumps(meta, indent=2))
    return 0


def cmd_stop(_args: argparse.Namespace) -> int:
    meta = _read_meta()
    stopped: list[int] = []
    for key in ("chromium_pid", "weston_pid"):
        pid = meta.get(key)
        if _is_alive(pid):
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                stopped.append(pid)
            except OSError:
                pass
    time.sleep(0.5)
    for key in ("chromium_pid", "weston_pid"):
        pid = meta.get(key)
        if _is_alive(pid):
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except OSError:
                pass
    if META_PATH.exists():
        META_PATH.unlink()
    print(json.dumps({"ok": True, "stopped": stopped}, indent=2))
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    meta = _read_meta()
    meta["weston_alive"] = _is_alive(meta.get("weston_pid"))
    meta["chromium_alive"] = _is_alive(meta.get("chromium_pid"))
    if meta.get("cdp_port") and meta["chromium_alive"]:
        try:
            meta["cdp"] = _urlopen_json(f"http://127.0.0.1:{meta['cdp_port']}/json/version")
        except Exception as exc:  # noqa: BLE001
            meta["cdp_error"] = str(exc)
    print(json.dumps(meta or {"ok": False, "running": False}, indent=2))
    return 0 if meta.get("chromium_alive") else 1


async def _cdp_call(ws_url: str, method: str, params: dict[str, Any] | None = None, msg_id: int = 1) -> Any:
    async with websockets.connect(ws_url, max_size=32 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result")


def _page_ws(port: int) -> str:
    pages = _urlopen_json(f"http://127.0.0.1:{port}/json/list")
    if not pages:
        raise RuntimeError("No Chromium tabs available")
    for page in pages:
        if page.get("type") == "page" and "discord.com" in page.get("url", ""):
            return page["webSocketDebuggerUrl"]
    return pages[0]["webSocketDebuggerUrl"]


def _read_body_text(port: int) -> str:
    ws_url = _page_ws(port)
    expr = "document.body ? document.body.innerText : ''"
    result = asyncio.run(_cdp_call(ws_url, "Runtime.evaluate", {"expression": expr, "returnByValue": True}))
    return result.get("result", {}).get("value", "")


def _evaluate_js(port: int, expr: str) -> Any:
    ws_url = _page_ws(port)
    result = asyncio.run(_cdp_call(ws_url, "Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}))
    return result.get("result", {}).get("value")


def _github_links_from_text(text: str) -> list[str]:
    return sorted(set(re.findall(r"https://github[.]com/[^\s)>\"]+", text)))


_DISCORD_COLLECT_JS = r"""
(() => {
  const linkPattern = /https:\/\/github[.]com\/[^\s)>"']+/g;
  const clean = value => (value || '').replace(/\s+/g, ' ').trim();
  const messageSelectors = [
    'li[id^="chat-messages-"]',
    '[id^="chat-messages-"]',
    '[class*="messageListItem"]',
    '[class*="messageContent"]'
  ];
  const seen = new Set();
  const messages = [];
  for (const node of document.querySelectorAll(messageSelectors.join(','))) {
    const root = node.closest('li[id^="chat-messages-"], [id^="chat-messages-"], [class*="messageListItem"]') || node;
    const text = clean(root.innerText || root.textContent || '');
    if (!text) continue;
    const anchors = Array.from(root.querySelectorAll('a[href]')).map(a => a.href).filter(Boolean);
    const textLinks = Array.from(text.matchAll(linkPattern)).map(m => m[0]);
    const links = Array.from(new Set([...anchors, ...textLinks]));
    const id = root.id || `${text.slice(0, 96)}:${links.join('|')}`;
    if (seen.has(id)) continue;
    seen.add(id);
    messages.push({
      id,
      text,
      links,
      github_links: links.filter(h => h.includes('github.com/')),
      pull_request_links: links.filter(h => h.includes('github.com/') && h.includes('/pull/')),
      timestamp: root.querySelector('time')?.getAttribute('datetime') || root.querySelector('time')?.textContent || ''
    });
  }
  const bodyText = document.body ? document.body.innerText || '' : '';
  const hrefLinks = Array.from(document.querySelectorAll('a[href]')).map(a => a.href).filter(Boolean);
  const textLinks = Array.from(bodyText.matchAll(linkPattern)).map(m => m[0]);
  const links = Array.from(new Set([...hrefLinks, ...textLinks]));
  const scoreScroller = el => {
    const id = el.id || '';
    const cls = String(el.className || '');
    const role = el.getAttribute('role') || '';
    const aria = el.getAttribute('aria-label') || '';
    const dataList = el.getAttribute('data-list-id') || '';
    let score = 0;
    if (el.querySelector('[id^="chat-messages-"]')) score += 100;
    if (dataList.includes('chat-messages')) score += 80;
    if (role === 'log') score += 60;
    if (/message|chat/i.test(aria + ' ' + cls)) score += 30;
    if (/channels|guilds|members/i.test(id + ' ' + aria + ' ' + dataList)) score -= 80;
    return score;
  };
  const scrollCandidates = Array.from(document.querySelectorAll('*')).filter(el => {
    const style = getComputedStyle(el);
    return el.scrollHeight > el.clientHeight + 40 && /(auto|scroll)/.test(style.overflowY || '');
  }).sort((a, b) => (scoreScroller(b) - scoreScroller(a)) || ((b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight)));
  const scroller = scrollCandidates[0] || document.scrollingElement || document.documentElement;
  return {
    url: location.href,
    title: document.title,
    body_chars: bodyText.length,
    messages,
    links,
    github_links: links.filter(h => h.includes('github.com/')),
    pull_request_links: links.filter(h => h.includes('github.com/') && h.includes('/pull/')),
    scroll: scroller ? {
      top: scroller.scrollTop,
      height: scroller.scrollHeight,
      client_height: scroller.clientHeight,
      selector: scroller.id ? `#${scroller.id}` : (scroller.getAttribute('data-list-id') || scroller.getAttribute('role') || scroller.getAttribute('class') || scroller.tagName),
      score: scoreScroller(scroller)
    } : null
  };
})()
"""


def _scroll_discord_chat(port: int, *, direction: str = "up", amount: float = 0.9) -> Any:
    direction_json = json.dumps(direction)
    amount_json = json.dumps(amount)
    expr = f"""
(() => {{
  const clean = value => (value || '').replace(/\\s+/g, ' ').trim();
  const scoreScroller = el => {{
    const id = el.id || '';
    const cls = String(el.className || '');
    const role = el.getAttribute('role') || '';
    const aria = el.getAttribute('aria-label') || '';
    const dataList = el.getAttribute('data-list-id') || '';
    let score = 0;
    if (el.querySelector('[id^="chat-messages-"]')) score += 100;
    if (dataList.includes('chat-messages')) score += 80;
    if (role === 'log') score += 60;
    if (/message|chat/i.test(aria + ' ' + cls)) score += 30;
    if (/channels|guilds|members/i.test(id + ' ' + aria + ' ' + dataList)) score -= 80;
    return score;
  }};
  const candidates = Array.from(document.querySelectorAll('*')).filter(el => {{
    const style = getComputedStyle(el);
    return el.scrollHeight > el.clientHeight + 40 && /(auto|scroll)/.test(style.overflowY || '');
  }}).sort((a, b) => (scoreScroller(b) - scoreScroller(a)) || ((b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight)));
  const scroller = candidates[0] || document.scrollingElement || document.documentElement;
  if (!scroller) return {{ok:false, error:'no scroll container'}};
  const before = scroller.scrollTop;
  const delta = Math.max(300, scroller.clientHeight * {amount_json});
  if ({direction_json} === 'down') scroller.scrollTop = Math.min(scroller.scrollHeight, before + delta);
  else scroller.scrollTop = Math.max(0, before - delta);
  scroller.dispatchEvent(new Event('scroll', {{bubbles:true}}));
  return {{ok:true, before, after:scroller.scrollTop, height:scroller.scrollHeight, client_height:scroller.clientHeight, score:scoreScroller(scroller), selector:scroller.id ? `#${{scroller.id}}` : (scroller.getAttribute('data-list-id') || scroller.getAttribute('role') || scroller.getAttribute('class') || scroller.tagName)}};
}})()
"""
    return _evaluate_js(port, expr)


def _jump_discord_chat_latest(port: int) -> Any:
    expr = """
(() => {
  const scoreScroller = el => {
    const id = el.id || '';
    const cls = String(el.className || '');
    const role = el.getAttribute('role') || '';
    const aria = el.getAttribute('aria-label') || '';
    const dataList = el.getAttribute('data-list-id') || '';
    let score = 0;
    if (el.querySelector('[id^="chat-messages-"]')) score += 100;
    if (dataList.includes('chat-messages')) score += 80;
    if (role === 'log') score += 60;
    if (/message|chat/i.test(aria + ' ' + cls)) score += 30;
    if (/channels|guilds|members/i.test(id + ' ' + aria + ' ' + dataList)) score -= 80;
    return score;
  };
  const candidates = Array.from(document.querySelectorAll('*')).filter(el => {
    const style = getComputedStyle(el);
    return el.scrollHeight > el.clientHeight + 40 && /(auto|scroll)/.test(style.overflowY || '');
  }).sort((a, b) => (scoreScroller(b) - scoreScroller(a)) || ((b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight)));
  const scroller = candidates[0] || document.scrollingElement || document.documentElement;
  if (!scroller) return {ok:false, error:'no scroll container'};
  const before = scroller.scrollTop;
  scroller.scrollTop = scroller.scrollHeight;
  scroller.dispatchEvent(new Event('scroll', {bubbles:true}));
  return {ok:true, before, after:scroller.scrollTop, height:scroller.scrollHeight, client_height:scroller.clientHeight, score:scoreScroller(scroller)};
})()
"""
    return _evaluate_js(port, expr)


def _parse_datetime_bound(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    lowered = raw.lower()
    now = datetime.now(timezone.utc)
    if lowered == "today":
        return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    if lowered == "yesterday":
        day = now - timedelta(days=1)
        return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _message_timestamp(message: dict[str, Any]) -> datetime | None:
    value = str(message.get("timestamp") or "").strip()
    if not value:
        return None
    try:
        return _parse_datetime_bound(value)
    except ValueError:
        return None


def _merge_scrape_pages(pages: list[dict[str, Any]]) -> dict[str, Any]:
    messages_by_key: dict[str, dict[str, Any]] = {}
    links: set[str] = set()
    github_links: set[str] = set()
    pr_links: set[str] = set()
    for page in pages:
        for link in page.get("links") or []:
            links.add(link)
        for link in page.get("github_links") or []:
            github_links.add(link)
        for link in page.get("pull_request_links") or []:
            pr_links.add(link)
        for msg in page.get("messages") or []:
            key = msg.get("id") or msg.get("text", "")[:160]
            if key and key not in messages_by_key:
                messages_by_key[key] = msg
            for link in msg.get("links") or []:
                links.add(link)
            for link in msg.get("github_links") or []:
                github_links.add(link)
            for link in msg.get("pull_request_links") or []:
                pr_links.add(link)
    messages = list(messages_by_key.values())
    messages.sort(key=lambda msg: (_message_timestamp(msg) or datetime.max.replace(tzinfo=timezone.utc), msg.get("id") or ""))
    return {
        "ok": True,
        "pages": len(pages),
        "messages": messages,
        "message_count": len(messages_by_key),
        "links": sorted(links),
        "github_links": sorted(github_links),
        "pull_request_links": sorted(pr_links),
        "github_link_count": len(github_links),
        "pull_request_count": len(pr_links),
        "first_url": pages[0].get("url") if pages else "",
        "last_scroll": pages[-1].get("scroll") if pages else None,
    }


def _filter_scrape_window(result: dict[str, Any], *, since: datetime | None, until: datetime | None) -> dict[str, Any]:
    if not since and not until:
        return result
    filtered: list[dict[str, Any]] = []
    for message in result.get("messages") or []:
        ts = _message_timestamp(message)
        if ts is None:
            continue
        if since and ts < since:
            continue
        if until and ts > until:
            continue
        filtered.append(message)
    links: set[str] = set()
    github_links: set[str] = set()
    pr_links: set[str] = set()
    for message in filtered:
        for link in message.get("links") or []:
            links.add(link)
        for link in message.get("github_links") or []:
            github_links.add(link)
        for link in message.get("pull_request_links") or []:
            pr_links.add(link)
    updated = dict(result)
    updated.update(
        {
            "messages": filtered,
            "message_count": len(filtered),
            "links": sorted(links),
            "github_links": sorted(github_links),
            "pull_request_links": sorted(pr_links),
            "github_link_count": len(github_links),
            "pull_request_count": len(pr_links),
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
        }
    )
    return updated


def _delta_complete(*, since: datetime | None, stop_reason: str) -> bool:
    return not since or stop_reason in {"since_reached", "scroll_exhausted"}


def _wait_for_body_text(port: int, *, min_chars: int = 20, timeout: float = 30.0) -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            last = _read_body_text(port)
        except Exception:  # noqa: BLE001 - Discord may be between execution contexts while loading.
            last = ""
        if len(last.strip()) >= min_chars:
            return last
        time.sleep(0.5)
    return last


def cmd_text(args: argparse.Namespace) -> int:
    meta = _read_meta()
    port = int(args.port or meta.get("cdp_port") or DEFAULT_PORT)
    timeout = float(getattr(args, "timeout", 0.0) or 0.0)
    if timeout:
        text = _wait_for_body_text(port, min_chars=int(getattr(args, "min_chars", 20)), timeout=timeout)
    else:
        text = _read_body_text(port)
    if args.output:
        Path(args.output).expanduser().write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


def cmd_scrape(args: argparse.Namespace) -> int:
    meta = _read_meta()
    port = int(args.port or meta.get("cdp_port") or DEFAULT_PORT)
    timeout = float(getattr(args, "timeout", 30.0))
    _wait_for_body_text(port, min_chars=int(getattr(args, "min_chars", 20)), timeout=timeout)
    since = _parse_datetime_bound(getattr(args, "since", None))
    until = _parse_datetime_bound(getattr(args, "until", None))
    if since:
        _jump_discord_chat_latest(port)
        time.sleep(float(args.wait))
    pages: list[dict[str, Any]] = []
    stop_reason = "max_pages"
    for idx in range(max(1, int(args.pages))):
        value = _evaluate_js(port, _DISCORD_COLLECT_JS)
        if isinstance(value, dict):
            value["page_index"] = idx
            pages.append(value)
            timestamps = [_message_timestamp(msg) for msg in value.get("messages") or []]
            timestamps = [ts for ts in timestamps if ts is not None]
            if since and timestamps and min(timestamps) < since:
                stop_reason = "since_reached"
                break
        if idx < int(args.pages) - 1:
            scroll = _scroll_discord_chat(port, direction=args.direction, amount=float(args.scroll_amount))
            time.sleep(float(args.wait))
            if isinstance(scroll, dict) and scroll.get("before") == scroll.get("after"):
                stop_reason = "scroll_exhausted"
                break
    result = _merge_scrape_pages(pages)
    result = _filter_scrape_window(result, since=since, until=until)
    result["stop_reason"] = stop_reason
    result["delta_mode"] = bool(since or until)
    result["delta_complete"] = _delta_complete(since=since, stop_reason=stop_reason)
    if args.output:
        Path(args.output).expanduser().write_text(json.dumps(result, indent=2), encoding="utf-8")
    else:
        print(json.dumps(result, indent=2))
    return 0


def cmd_screenshot(args: argparse.Namespace) -> int:
    meta = _read_meta()
    port = int(args.port or meta.get("cdp_port") or DEFAULT_PORT)
    ws_url = _page_ws(port)
    result = asyncio.run(_cdp_call(ws_url, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": bool(args.full_page)}))
    data = base64.b64decode(result["data"])
    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(json.dumps({"ok": True, "path": str(out), "bytes": len(data)}, indent=2))
    return 0


def cmd_open_server(args: argparse.Namespace) -> int:
    meta = _read_meta()
    port = int(args.port or meta.get("cdp_port") or DEFAULT_PORT)
    _wait_for_body_text(port, timeout=float(getattr(args, "timeout", 30.0)))
    ws_url = _page_ws(port)
    server_name = json.dumps(args.name)
    expr = f"""
(() => {{
  const items = Array.from(document.querySelectorAll('[role="treeitem"], [aria-label], [title], div, span'));
  const labels = e => [
    e.getAttribute('aria-label') || '',
    e.getAttribute('title') || '',
    e.innerText || ''
  ].map(s => s.trim()).filter(Boolean);
  const el = items.find(e => labels(e).some(s => s === {server_name} || s.split('\\n').includes({server_name}) || s.startsWith({server_name} + ' ')));
  if (!el) return {{ok:false, error:'server not found', name:{server_name}}};
  const target = el.closest('[role="treeitem"], a[href], [aria-label]') || el;
  target.dispatchEvent(new MouseEvent('mousedown', {{bubbles:true, button:0}}));
  target.dispatchEvent(new MouseEvent('mouseup', {{bubbles:true, button:0}}));
  target.click();
  return {{ok:true, text:(target.innerText || el.innerText || '').trim(), aria:target.getAttribute('aria-label') || el.getAttribute('aria-label')}};
}})()
"""
    result = asyncio.run(_cdp_call(ws_url, "Runtime.evaluate", {"expression": expr, "returnByValue": True}))
    value = result.get("result", {}).get("value")
    print(json.dumps(value, indent=2))
    return 0 if value and value.get("ok") else 1


def cmd_channels(args: argparse.Namespace) -> int:
    meta = _read_meta()
    port = int(args.port or meta.get("cdp_port") or DEFAULT_PORT)
    _wait_for_body_text(port, timeout=float(getattr(args, "timeout", 30.0)))
    ws_url = _page_ws(port)
    guild_id = json.dumps(args.guild_id)
    expr = f"""
Array.from(document.querySelectorAll('a[href]')).map(a => {{
  const href = a.href;
  const aria = a.getAttribute('aria-label') || '';
  const raw = (a.innerText || aria || a.title || '').trim();
  const parts = raw.split('\\n').map(s => s.trim()).filter(Boolean);
  const hrefParts = href.split('/');
  return {{
    name: (aria.match(/(?:unread,\\s*)?([^,(]+)\\s*\\(/) || [null, parts.find(p => !/^(Text|Forum|Announcements|Invite|\\d+ New)/.test(p)) || ''])[1].trim(),
    href,
    aria,
    text: raw,
    guild_id: hrefParts[hrefParts.length - 2],
    channel_id: hrefParts[hrefParts.length - 1],
  }};
}}).filter(x => x.href.includes('/channels/' + {guild_id} + '/'))
"""
    result = asyncio.run(_cdp_call(ws_url, "Runtime.evaluate", {"expression": expr, "returnByValue": True}))
    channels = result.get("result", {}).get("value") or []
    if args.output:
        Path(args.output).expanduser().write_text(json.dumps(channels, indent=2), encoding="utf-8")
    else:
        print(json.dumps(channels, indent=2))
    return 0


def cmd_goto(args: argparse.Namespace) -> int:
    meta = _read_meta()
    port = int(args.port or meta.get("cdp_port") or DEFAULT_PORT)
    _wait_for_body_text(port, timeout=float(getattr(args, "timeout", 30.0)))
    ws_url = _page_ws(port)
    href = args.href
    if not href:
        # Resolve by channel name from the currently visible server channel list.
        guild_id = json.dumps(args.guild_id)
        name = json.dumps(args.channel)
        expr = f"""
(() => {{
  const links = Array.from(document.querySelectorAll('a[href]')).map(a => {{
    const href = a.href;
    const aria = a.getAttribute('aria-label') || '';
    const raw = (a.innerText || aria || a.title || '').trim();
    const parts = raw.split('\\n').map(s => s.trim()).filter(Boolean);
    const cname = (aria.match(/(?:unread,\\s*)?([^,(]+)\\s*\\(/) || [null, parts.find(p => !/^(Text|Forum|Announcements|Invite|\\d+ New)/.test(p)) || ''])[1].trim();
    return {{name:cname, href}};
  }}).filter(x => x.href.includes('/channels/' + {guild_id} + '/'));
  const hit = links.find(x => x.name === {name});
  return hit || null;
}})()
"""
        resolved = asyncio.run(_cdp_call(ws_url, "Runtime.evaluate", {"expression": expr, "returnByValue": True}))
        hit = resolved.get("result", {}).get("value")
        if not hit:
            raise RuntimeError(f"channel not found: {args.channel}")
        href = hit["href"]
    result = asyncio.run(_cdp_call(ws_url, "Page.navigate", {"url": href}))
    if args.wait:
        time.sleep(float(args.wait))
    print(json.dumps({"ok": True, "url": href, "navigate": result}, indent=2))
    return 0


def _tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "name": "discord_monitor_start",
            "description": "Start isolated Chromium on Discord inside a nested Wayland compositor. Use visible=true for one-time login, then headless mode for unattended monitoring.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "default": DEFAULT_URL},
                    "visible": {"type": "boolean", "default": False},
                    "port": {"type": "integer", "default": DEFAULT_PORT},
                    "socket": {"type": "string", "default": "hermes-discord-monitor"},
                    "width": {"type": "integer", "default": 1440},
                    "height": {"type": "integer", "default": 1100},
                },
            },
        },
        {
            "name": "discord_monitor_stop",
            "description": "Stop the isolated Discord Wayland monitor.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "discord_monitor_status",
            "description": "Return monitor process state and Chromium DevTools endpoint metadata.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "discord_monitor_open_server",
            "description": "Click a visible Discord server in the isolated browser by server name.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "default": "Nous Research"},
                    "port": {"type": "integer"},
                    "timeout": {"type": "number", "default": 30.0},
                },
            },
        },
        {
            "name": "discord_monitor_channels",
            "description": "List visible Discord channels for a guild from the browser DOM, including channel IDs and links.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "guild_id": {"type": "string", "default": NOUS_GUILD_ID},
                    "port": {"type": "integer"},
                    "timeout": {"type": "number", "default": 30.0},
                },
            },
        },
        {
            "name": "discord_monitor_goto",
            "description": "Navigate the isolated browser to a Discord channel by channel name or full href.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string"},
                    "href": {"type": "string"},
                    "guild_id": {"type": "string", "default": NOUS_GUILD_ID},
                    "port": {"type": "integer"},
                    "wait": {"type": "number", "default": 3.0},
                    "timeout": {"type": "number", "default": 30.0},
                },
            },
        },
        {
            "name": "discord_monitor_text",
            "description": "Return document.body.innerText from the isolated Discord browser tab.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "port": {"type": "integer"},
                    "timeout": {"type": "number", "default": 0.0},
                    "min_chars": {"type": "integer", "default": 20},
                },
            },
        },
        {
            "name": "discord_monitor_scrape",
            "description": "Scroll the loaded Discord channel DOM and return structured messages, hrefs, GitHub links, and pull request links. Supports since/until delta windows; prefer this over screenshots for monitoring.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "port": {"type": "integer"},
                    "pages": {"type": "integer", "default": 8},
                    "direction": {"type": "string", "enum": ["up", "down"], "default": "up"},
                    "wait": {"type": "number", "default": 1.25},
                    "scroll_amount": {"type": "number", "default": 0.9},
                    "timeout": {"type": "number", "default": 30.0},
                    "min_chars": {"type": "integer", "default": 20},
                    "since": {"type": "string", "description": "ISO timestamp, YYYY-MM-DD, today, or yesterday. When set, start at latest messages and page upward until older messages are reached."},
                    "until": {"type": "string", "description": "Optional ISO timestamp, YYYY-MM-DD, today, or yesterday upper bound."},
                },
            },
        },
        {
            "name": "discord_monitor_screenshot",
            "description": "Capture the isolated Chromium viewport through CDP without touching the operator desktop. Use only for visual debugging; scrape/text are better for links.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "output": {"type": "string"},
                    "port": {"type": "integer"},
                    "full_page": {"type": "boolean", "default": False},
                },
                "required": ["output"],
            },
        },
    ]


def _capture_command(func: Any, args: argparse.Namespace) -> dict[str, Any]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = func(args)
    out = stdout.getvalue().strip()
    err = stderr.getvalue().strip()
    parsed: Any = None
    if out:
        try:
            parsed = json.loads(out)
        except json.JSONDecodeError:
            parsed = out
    return {"ok": exit_code == 0, "exit_code": exit_code, "data": parsed, "stdout": out, "stderr": err}


def call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "discord_monitor_start":
        ns = argparse.Namespace(
            url=args.get("url", DEFAULT_URL),
            visible=bool(args.get("visible", False)),
            socket=args.get("socket", "hermes-discord-monitor"),
            width=int(args.get("width", 1440)),
            height=int(args.get("height", 1100)),
            port=int(args.get("port", DEFAULT_PORT)),
        )
        return _capture_command(cmd_start, ns)
    if name == "discord_monitor_stop":
        return _capture_command(cmd_stop, argparse.Namespace())
    if name == "discord_monitor_status":
        return _capture_command(cmd_status, argparse.Namespace())
    if name == "discord_monitor_open_server":
        ns = argparse.Namespace(name=args.get("name", "Nous Research"), port=args.get("port"), timeout=float(args.get("timeout", 30.0)))
        return _capture_command(cmd_open_server, ns)
    if name == "discord_monitor_channels":
        ns = argparse.Namespace(
            port=args.get("port"),
            guild_id=args.get("guild_id", NOUS_GUILD_ID),
            output=None,
            timeout=float(args.get("timeout", 30.0)),
        )
        return _capture_command(cmd_channels, ns)
    if name == "discord_monitor_goto":
        ns = argparse.Namespace(
            channel=args.get("channel"),
            href=args.get("href"),
            guild_id=args.get("guild_id", NOUS_GUILD_ID),
            port=args.get("port"),
            wait=float(args.get("wait", 3.0)),
            timeout=float(args.get("timeout", 30.0)),
        )
        return _capture_command(cmd_goto, ns)
    if name == "discord_monitor_text":
        return _capture_command(
            cmd_text,
            argparse.Namespace(
                port=args.get("port"),
                output=None,
                timeout=float(args.get("timeout", 0.0)),
                min_chars=int(args.get("min_chars", 20)),
            ),
        )
    if name == "discord_monitor_scrape":
        return _capture_command(
            cmd_scrape,
            argparse.Namespace(
                port=args.get("port"),
                pages=int(args.get("pages", 8)),
                direction=args.get("direction", "up"),
                wait=float(args.get("wait", 1.25)),
                scroll_amount=float(args.get("scroll_amount", 0.9)),
                timeout=float(args.get("timeout", 30.0)),
                min_chars=int(args.get("min_chars", 20)),
                since=args.get("since"),
                until=args.get("until"),
                output=None,
            ),
        )
    if name == "discord_monitor_screenshot":
        output = args.get("output")
        if not output:
            raise ValueError("output is required")
        return _capture_command(cmd_screenshot, argparse.Namespace(port=args.get("port"), output=output, full_page=bool(args.get("full_page", False))))
    raise ValueError(f"unknown tool: {name}")


def _mcp_response(msg_id: Any, result: Any = None, error: str | None = None) -> dict[str, Any]:
    if error is not None:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32000, "message": error}}
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def serve_mcp() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            method = request.get("method")
            msg_id = request.get("id")
            params = request.get("params") or {}
            if msg_id is None:
                continue
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                }
            elif method == "tools/list":
                result = {"tools": _tool_schemas()}
            elif method == "tools/call":
                tool_result = call_tool(params.get("name", ""), params.get("arguments") or {})
                result = {
                    "content": [{"type": "text", "text": json.dumps(tool_result, indent=2)}],
                    "isError": not tool_result.get("ok", False),
                }
            else:
                sys.stdout.write(json.dumps(_mcp_response(msg_id, error=f"unsupported method: {method}")) + "\n")
                sys.stdout.flush()
                continue
            sys.stdout.write(json.dumps(_mcp_response(msg_id, result=result)) + "\n")
            sys.stdout.flush()
        except Exception as exc:  # noqa: BLE001 - stdio server must keep answering.
            msg_id = request.get("id") if isinstance(locals().get("request"), dict) else None
            sys.stdout.write(json.dumps(_mcp_response(msg_id, error=str(exc))) + "\n")
            sys.stdout.flush()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_start(name: str, visible: bool):
        p = sub.add_parser(name)
        p.set_defaults(func=cmd_start, visible=visible)
        p.add_argument("--url", default=DEFAULT_URL)
        p.add_argument("--socket", default="hermes-discord-monitor")
        p.add_argument("--width", type=int, default=1440)
        p.add_argument("--height", type=int, default=1100)
        p.add_argument("--port", type=int, default=DEFAULT_PORT)
        return p

    add_start("start", visible=False)
    add_start("login", visible=True)
    p = sub.add_parser("stop")
    p.set_defaults(func=cmd_stop)
    p = sub.add_parser("status")
    p.set_defaults(func=cmd_status)
    p = sub.add_parser("text")
    p.set_defaults(func=cmd_text)
    p.add_argument("--port", type=int)
    p.add_argument("--output")
    p.add_argument("--timeout", type=float, default=0.0, help="Wait up to this many seconds for body text before reading")
    p.add_argument("--min-chars", type=int, default=20)
    p = sub.add_parser("scrape")
    p.set_defaults(func=cmd_scrape)
    p.add_argument("--port", type=int)
    p.add_argument("--pages", type=int, default=8, help="Number of virtualized channel viewports to collect")
    p.add_argument("--direction", choices=("up", "down"), default="up")
    p.add_argument("--wait", type=float, default=1.25, help="Seconds to wait after each DOM scroll")
    p.add_argument("--scroll-amount", type=float, default=0.9, help="Fraction of the chat viewport to scroll per page")
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--min-chars", type=int, default=20)
    p.add_argument("--since", help="Delta lower bound: ISO timestamp, YYYY-MM-DD, today, or yesterday")
    p.add_argument("--until", help="Optional delta upper bound: ISO timestamp, YYYY-MM-DD, today, or yesterday")
    p.add_argument("--output")
    p = sub.add_parser("screenshot")
    p.set_defaults(func=cmd_screenshot)
    p.add_argument("--port", type=int)
    p.add_argument("--output", required=True)
    p.add_argument("--full-page", action="store_true", help="Ask Chromium for captureBeyondViewport; useful for ordinary pages, less useful for virtualized Discord history")
    p = sub.add_parser("open-server")
    p.set_defaults(func=cmd_open_server)
    p.add_argument("name", nargs="?", default="Nous Research")
    p.add_argument("--port", type=int)
    p.add_argument("--timeout", type=float, default=30.0)
    p = sub.add_parser("channels")
    p.set_defaults(func=cmd_channels)
    p.add_argument("--port", type=int)
    p.add_argument("--guild-id", default=NOUS_GUILD_ID)
    p.add_argument("--output")
    p.add_argument("--timeout", type=float, default=30.0)
    p = sub.add_parser("goto")
    p.set_defaults(func=cmd_goto)
    p.add_argument("channel", nargs="?")
    p.add_argument("--href")
    p.add_argument("--guild-id", default=NOUS_GUILD_ID)
    p.add_argument("--port", type=int)
    p.add_argument("--wait", type=float, default=3.0)
    p.add_argument("--timeout", type=float, default=30.0)
    p = sub.add_parser("mcp")
    p.set_defaults(func=lambda _args: serve_mcp())
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
