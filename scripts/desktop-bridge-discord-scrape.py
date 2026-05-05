#!/usr/bin/env python3
"""End-to-end desktop bridge exercise: navigate Discord to the Nous Research
``#github-tracker`` channel and OCR-scrape visible history.

Design highlights
-----------------

*Incremental*: a state file under
``~/.local/state/hermes-desktop-bridge/discord/<slug>.json`` remembers
fingerprints of lines already seen, so each re-run only emits *new* messages
since the previous scrape. Pass ``--full`` to force a complete dump.

*Minimum focus disruption*: screenshots use ``import -window <WID>`` so they
bypass focus entirely. Keyboard injection still requires a focused window on
Wayland, but the driver folds every input step into a single focus-burst:
``save_focus → activate Discord → (ctrl+k, type, Return, Page_Up × N) →
restore_focus``. The user's foreground window returns to where it was.

Usage
-----

    ./scripts/desktop-bridge-discord-scrape.py            # incremental run
    ./scripts/desktop-bridge-discord-scrape.py --full     # full dump
    ./scripts/desktop-bridge-discord-scrape.py --pages 8
    ./scripts/desktop-bridge-discord-scrape.py --background-input
    ./scripts/desktop-bridge-discord-scrape.py --no-restore-focus
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
BRIDGE_PATH = ROOT / "deploy" / "k8s" / "desktop-bridge-mcp.py"
DEFAULT_OUT = ROOT / "benchmark_runs"
STATE_ROOT = Path(os.getenv("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "hermes-desktop-bridge" / "discord"


# Lines we don't want to fingerprint or emit — system tray/panel noise and
# Discord chrome that appears on every page.
NOISE_PATTERNS = [
    re.compile(r"^[\s\W_]+$"),                          # pure symbols / dividers
    re.compile(r"Message #", re.I),                     # composer placeholder
    re.compile(r"Search .* Discord", re.I),             # search bar
    re.compile(r"^>\s*IETE"),                           # KDE panel icons OCR
    re.compile(r"Channels & Roles"),
    re.compile(r"^\s*\d+\s+New\s*$", re.I),
    re.compile(r"Mark As Read", re.I),
]


def _load_bridge():
    spec = importlib.util.spec_from_file_location("desktop_bridge_mcp", BRIDGE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BridgeClient:
    def __init__(self, base_url: str, token: str, log: list[dict[str, Any]]):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.log = log

    def call(self, name: str, args: dict[str, Any] | None = None, *, timeout: float = 30.0) -> Any:
        args = args or {}
        start = time.monotonic()
        payload = json.dumps({"name": name, "args": args}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/call",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            status = resp.status
            error: str | None = None
            result = body.get("result")
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = json.loads(exc.read().decode("utf-8"))
            error = body.get("error") or str(exc)
            result = None
        elapsed = time.monotonic() - start
        entry = {
            "name": name,
            "args": args,
            "status": status,
            "result": result,
            "error": error,
            "elapsed_s": round(elapsed, 3),
        }
        self.log.append(entry)
        if error:
            raise RuntimeError(f"{name} failed: {error}")
        return result


def start_bridge(token: str) -> tuple[ThreadingHTTPServer, int, threading.Thread]:
    bridge = _load_bridge()
    os.environ["DESKTOP_BRIDGE_TOKEN"] = token
    os.environ.setdefault("DESKTOP_BRIDGE_ALLOW_CONTROL", "1")
    os.environ.setdefault("DESKTOP_BRIDGE_ALLOWED_WINDOW_RE", "Discord")
    os.environ.setdefault("DESKTOP_BRIDGE_ARTIFACT_DIR", "/tmp/hermes-desktop-bridge")
    server = ThreadingHTTPServer(("127.0.0.1", 0), bridge.DesktopBridgeHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port, thread


def _normalize_line(raw: str) -> str:
    # Lowercase, collapse whitespace, strip leading/trailing decoration.
    s = re.sub(r"\s+", " ", raw).strip().lower()
    # Strip trailing punctuation that OCR commonly wiggles on.
    s = s.rstrip(" .·•|")
    return s


def _is_noise(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) < 6:
        return True
    if any(p.search(stripped) for p in NOISE_PATTERNS):
        return True
    # Lines that are mostly single-character rows of emoji/badge OCR.
    alnum = sum(1 for c in stripped if c.isalnum())
    if alnum < 4:
        return True
    return False


def _fingerprint(line: str) -> str:
    return hashlib.sha1(_normalize_line(line).encode("utf-8")).hexdigest()[:16]


_PR_LINE_RE = re.compile(r"(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\s+-\s+PR\s+#(?P<num>\d+)", re.I)


def extract_pr_links(lines: list[str]) -> list[dict[str, Any]]:
    """Extract GitHub PR links from OCR lines.

    Discord message links require Discord message IDs, which OCR cannot recover.
    GitHub PR links are deterministic from the visible repo + PR number.
    """
    prs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for idx, line in enumerate(lines):
        match = _PR_LINE_RE.search(line)
        if not match:
            continue
        repo = match.group("repo")
        number = match.group("num")
        key = (repo.lower(), number)
        if key in seen:
            continue
        seen.add(key)

        title = ""
        for candidate in lines[idx + 1: idx + 8]:
            stripped = candidate.strip()
            if not stripped or _is_noise(stripped) or _PR_LINE_RE.search(stripped):
                continue
            if stripped.lower() in {"summary", "verification", "events", "notes"}:
                continue
            title = stripped
            break
        prs.append({
            "repo": repo,
            "number": int(number),
            "title": title,
            "url": f"https://github.com/{repo}/pull/{number}",
        })
    return prs


def load_state(slug: str) -> dict[str, Any]:
    path = STATE_ROOT / f"{slug}.json"
    if not path.exists():
        return {"seen": [], "last_scrape_iso": None, "runs": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"seen": [], "last_scrape_iso": None, "runs": 0}


def save_state(slug: str, state: dict[str, Any]) -> Path:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    path = STATE_ROOT / f"{slug}.json"
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=6, help="Max screenshot pages to scroll back through")
    parser.add_argument("--settle-ms", type=int, default=900, help="Milliseconds to wait for UI transitions")
    parser.add_argument("--channel", default="github-tracker")
    parser.add_argument("--server", default="Nous Research", help="Server hint used only in the output metadata")
    parser.add_argument("--full", action="store_true", help="Ignore prior state and emit everything captured this run")
    parser.add_argument("--no-navigate", action="store_true", help="Skip activate+ctrl+k; scrape whatever is currently open")
    parser.add_argument("--background-input", action="store_true", help="Send keys/text to the Discord X/XWayland window id instead of activating it")
    parser.add_argument("--capture-strategy", choices=["auto", "window", "screen_crop"], default="auto",
                        help="Screenshot strategy. screen_crop avoids import -window but only works when Discord is visible on the current workspace.")
    parser.add_argument("--no-restore-focus", action="store_true", help="Do not restore the previously-focused window at the end")
    parser.add_argument("--window-class", default="discord", help="WM_CLASS substring used to find the Discord window")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--token", default=None)
    ns = parser.parse_args(argv)

    run_id = time.strftime("desktop_bridge_smoke_%Y%m%dT%H%M%SZ", time.gmtime())
    out_dir = Path(ns.out_dir).expanduser() if ns.out_dir else DEFAULT_OUT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", f"{ns.server}-{ns.channel}").strip("-").lower()
    state = load_state(slug)
    seen: set[str] = set(state.get("seen") or [])

    token = ns.token or "driver-" + hashlib.sha1(run_id.encode()).hexdigest()[:24]
    log: list[dict[str, Any]] = []
    server, port, thread = start_bridge(token)
    base_url = f"http://127.0.0.1:{port}"
    client = BridgeClient(base_url, token, log)
    settle = max(0.0, ns.settle_ms / 1000.0)

    summary: dict[str, Any] = {
        "run_id": run_id,
        "server_hint": ns.server,
        "channel": ns.channel,
        "slug": slug,
        "full_dump": ns.full,
        "pages_requested": ns.pages,
        "window_class": ns.window_class,
        "prior_seen_count": len(seen),
    }

    try:
        status = client.call("desktop.status")
        summary["status"] = {
            "session_type": status.get("session_type"),
            "desktop": status.get("desktop"),
            "input_backends": status.get("input_backends"),
        }
        print(f"[{run_id}] session={status.get('session_type')} backends={status.get('input_backends')}")

        # Resolve the Discord window id up-front so screenshots bypass focus.
        found = client.call("desktop.find_window", {"pattern": ns.window_class, "match": "class"})
        if not found.get("windows"):
            raise RuntimeError(f"no window matched class pattern {ns.window_class!r}")
        wid = found["windows"][0]["id"]
        win_title = found["windows"][0].get("title", "")
        print(f"[{run_id}] resolved discord WID={wid} title={win_title!r}")
        summary["discord_window_id"] = wid
        summary["discord_window_title"] = win_title

        key_target = {"window_id": wid} if ns.background_input else {}
        if ns.background_input:
            print(f"[{run_id}] using background window-targeted input")
        else:
            # ---- Single focus-burst covering every input action -----------------
            client.call("desktop.save_focus")
            client.call("desktop.activate_window", {"pattern": ns.window_class, "match": "class"})
            time.sleep(settle)

        if not ns.no_navigate:
            print(f"[{run_id}] ctrl+k → {ns.channel} → Return")
            client.call("desktop.hotkey", {"keys": "ctrl+k", **key_target})
            time.sleep(settle)
            client.call("desktop.type", {"text": ns.channel, "delay_ms": 12, **key_target})
            time.sleep(settle)
            client.call("desktop.hotkey", {"keys": "Return", **key_target})
            time.sleep(settle * 2)

            current = client.call("desktop.find_window", {"pattern": ns.window_class, "match": "class"})
            current_title = (current.get("windows") or [{}])[0].get("title", "")
            summary["post_navigation_title"] = current_title
            if ns.channel.lower() not in current_title.lower():
                raise RuntimeError(
                    f"navigation did not reach #{ns.channel}; Discord title is {current_title!r}"
                )

        client.call("desktop.hotkey", {"keys": "Escape", **key_target})
        time.sleep(0.2)
        client.call("desktop.hotkey", {"keys": "End", **key_target})
        time.sleep(settle)

        ocr_pages: list[tuple[int, str]] = []
        overlap_page: int | None = None
        for idx in range(ns.pages):
            shot_path = out_dir / f"page_{idx:03d}.png"
            client.call(
                "desktop.screenshot",
                {"path": str(shot_path), "format": "png", "window_id": wid, "capture_strategy": ns.capture_strategy},
                timeout=30,
            )
            ocr = client.call(
                "desktop.ocr",
                {"path": str(shot_path), "max_chars": 40000, "psm": 6},
                timeout=90,
            )
            text = ocr.get("text", "") if isinstance(ocr, dict) else ""
            (out_dir / f"page_{idx:03d}.txt").write_text(text, encoding="utf-8")
            ocr_pages.append((idx, text))

            # Incremental stop: if ≥3 non-noise lines on this page are already
            # known fingerprints, we've scrolled into previously-seen history.
            if not ns.full and seen:
                page_lines = [ln for ln in text.splitlines() if not _is_noise(ln)]
                overlap_hits = sum(1 for ln in page_lines if _fingerprint(ln) in seen)
                overlap_ratio = overlap_hits / max(1, len(page_lines))
                print(f"[{run_id}] page {idx:03d}: {len(page_lines)} signal lines, {overlap_hits} seen ({overlap_ratio:.0%})")
                if overlap_hits >= 3 and overlap_ratio >= 0.3:
                    overlap_page = idx
                    break
            else:
                print(f"[{run_id}] page {idx:03d}: {len(text)} chars")

            if idx + 1 < ns.pages:
                client.call("desktop.hotkey", {"keys": "Page_Up", **key_target})
                time.sleep(settle)

        if not ns.background_input and not ns.no_restore_focus:
            client.call("desktop.restore_focus")

        # -------- Build transcript (oldest → newest) & update state ---------------
        fresh_lines: list[str] = []
        fresh_set: set[str] = set()
        # Iterate oldest first: that's the highest idx we captured.
        for idx, text in reversed(ocr_pages):
            for raw in text.splitlines():
                if _is_noise(raw):
                    continue
                fp = _fingerprint(raw)
                if fp in fresh_set:
                    continue
                if not ns.full and fp in seen:
                    continue
                fresh_set.add(fp)
                fresh_lines.append(raw.rstrip())

        updated_state = {
            "slug": slug,
            "channel": ns.channel,
            "server": ns.server,
            "last_scrape_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "last_run_id": run_id,
            "runs": int(state.get("runs") or 0) + 1,
            # Keep the 10k newest fingerprints to bound state file growth.
            "seen": list((seen | fresh_set))[-10000:],
        }
        state_path = save_state(slug, updated_state)

        transcript = out_dir / "transcript.md"
        pr_links = extract_pr_links(fresh_lines)
        links_json = out_dir / "links.json"
        links_md = out_dir / "links.md"
        links_json.write_text(json.dumps({"pull_requests": pr_links}, indent=2, ensure_ascii=False), encoding="utf-8")
        links_md.write_text(
            "\n".join(
                [
                    f"# Extracted links — {run_id}",
                    "",
                    *(
                        f"- [{item['repo']}#{item['number']}]({item['url']})"
                        + (f" — {item['title']}" if item.get("title") else "")
                        for item in pr_links
                    ),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        transcript.write_text(
            "\n".join(
                [
                    f"# Desktop bridge scrape — {run_id}",
                    "",
                    f"- Server: `{ns.server}`",
                    f"- Channel: `{ns.channel}`",
                    f"- Mode: {'full' if ns.full else 'incremental'}",
                    f"- Pages captured: {len(ocr_pages)} (limit {ns.pages})",
                    f"- Overlap stop: page {overlap_page}" if overlap_page is not None else "- Overlap stop: n/a",
                    f"- State: `{state_path}` (runs={updated_state['runs']}, seen={len(updated_state['seen'])})",
                    f"- Extracted PR links: `{links_md}` ({len(pr_links)})",
                    "",
                    "```",
                    *fresh_lines,
                    "```",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        summary.update(
            {
                "pages_captured": len(ocr_pages),
                "overlap_stop_page": overlap_page,
                "fresh_lines": len(fresh_lines),
                "pr_links": len(pr_links),
                "state_path": str(state_path),
                "transcript_path": str(transcript),
                "links_json_path": str(links_json),
                "links_md_path": str(links_md),
                "status_at_end": "ok",
            }
        )
        print(f"[{run_id}] fresh_lines={len(fresh_lines)} pr_links={len(pr_links)} overlap_page={overlap_page} state={state_path}")
    except Exception as exc:
        summary["status_at_end"] = f"error: {exc}"
        print(f"[{run_id}] ERROR: {exc}", file=sys.stderr)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        (out_dir / "run.json").write_text(
            json.dumps({"summary": summary, "calls": log}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[{run_id}] wrote {out_dir / 'run.json'}")

    return 0 if summary.get("status_at_end") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
