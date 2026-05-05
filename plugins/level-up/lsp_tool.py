"""Minimal LSP client exposed as a Hermes tool.

Ports the shape of claw-code-parity's `LspRegistry` into a Python
subprocess client that speaks the Language Server Protocol over
stdio. Supports a handful of high-value actions: diagnostics,
definition, references, hover, document-symbols, and workspace-symbols.

Servers are started lazily per language and kept alive for the life
of the process. Missing servers degrade gracefully — the tool returns
a clear error rather than crashing.

Configuration lives in `$HERMES_HOME/level_up/lsp.yaml`:

    servers:
      python:
        command: pyright-langserver
        args: [--stdio]
        languages: [python]
      typescript:
        command: typescript-language-server
        args: [--stdio]
        languages: [typescript, javascript, tsx, jsx]
      rust:
        command: rust-analyzer
        args: []
        languages: [rust]
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


_DEFAULT_SERVERS: dict[str, dict[str, Any]] = {
    "python":     {"command": "pyright-langserver", "args": ["--stdio"], "languages": ["python"]},
    "typescript": {"command": "typescript-language-server", "args": ["--stdio"], "languages": ["typescript", "javascript", "tsx", "jsx"]},
    "rust":       {"command": "rust-analyzer", "args": [],               "languages": ["rust"]},
    "go":         {"command": "gopls",         "args": [],               "languages": ["go"]},
}


_EXT_TO_LANG = {
    ".py": "python",
    ".ts": "typescript", ".tsx": "typescript",
    ".js": "typescript", ".jsx": "typescript",
    ".rs": "rust",
    ".go": "go",
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _load_servers() -> dict[str, dict[str, Any]]:
    cfg_path = get_hermes_home() / "level_up" / "lsp.yaml"
    if not cfg_path.exists():
        return dict(_DEFAULT_SERVERS)
    try:
        import yaml
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("level-up: failed to load lsp.yaml: %s", exc)
        return dict(_DEFAULT_SERVERS)
    merged = dict(_DEFAULT_SERVERS)
    merged.update(data.get("servers") or {})
    return merged


def _language_for_path(path: str) -> str | None:
    ext = os.path.splitext(path)[1].lower()
    return _EXT_TO_LANG.get(ext)


def _path_to_uri(path: str) -> str:
    return Path(path).resolve().as_uri()


# ---------------------------------------------------------------------------
# JSON-RPC client
# ---------------------------------------------------------------------------

class LspClient:
    """Minimal JSON-RPC 2.0 LSP client over stdio.

    One client per language server process. Requests are synchronous —
    we block on the matching response id. Notifications (fire-and-forget)
    are used for didOpen/didSave.
    """

    def __init__(self, name: str, command: str, args: list[str], root_uri: str) -> None:
        self.name = name
        self.command = command
        self.args = args
        self.root_uri = root_uri
        self._proc: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        self._next_id = 1
        self._responses: dict[int, dict[str, Any]] = {}
        self._response_event = threading.Event()
        self._initialized = False
        self._reader_thread: threading.Thread | None = None

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        if self._proc is not None:
            return
        if not shutil.which(self.command):
            raise FileNotFoundError(f"LSP server '{self.command}' not on PATH")
        self._proc = subprocess.Popen(
            [self.command, *self.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()
        self._initialize()

    def shutdown(self) -> None:
        if self._proc is None:
            return
        try:
            self._request("shutdown", None, timeout=2.0)
            self._notify("exit", None)
        except Exception:
            pass
        try:
            self._proc.terminate()
            self._proc.wait(timeout=2)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        self._proc = None

    # -- protocol -----------------------------------------------------------

    def _write(self, payload: dict[str, Any]) -> None:
        assert self._proc and self._proc.stdin
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._proc.stdin.write(header + body)
        self._proc.stdin.flush()

    def _reader_loop(self) -> None:
        assert self._proc and self._proc.stdout
        buf = b""
        while self._proc and self._proc.poll() is None:
            try:
                chunk = self._proc.stdout.read1(65536)
            except Exception:
                break
            if not chunk:
                break
            buf += chunk
            while True:
                sep = buf.find(b"\r\n\r\n")
                if sep < 0:
                    break
                header = buf[:sep].decode("ascii", errors="replace")
                length = 0
                for line in header.split("\r\n"):
                    if line.lower().startswith("content-length:"):
                        try:
                            length = int(line.split(":", 1)[1].strip())
                        except ValueError:
                            length = 0
                if length <= 0:
                    buf = buf[sep + 4 :]
                    continue
                if len(buf) < sep + 4 + length:
                    break
                body = buf[sep + 4 : sep + 4 + length]
                buf = buf[sep + 4 + length :]
                try:
                    message = json.loads(body.decode("utf-8"))
                except Exception:
                    continue
                if "id" in message and ("result" in message or "error" in message):
                    self._responses[int(message["id"])] = message
                    self._response_event.set()

    def _request(self, method: str, params: Any, timeout: float = 10.0) -> dict[str, Any]:
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
        self._write({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})

        deadline = time.time() + timeout
        while time.time() < deadline:
            if req_id in self._responses:
                return self._responses.pop(req_id)
            self._response_event.wait(timeout=0.1)
            self._response_event.clear()
        raise TimeoutError(f"LSP {method} timed out after {timeout}s")

    def _notify(self, method: str, params: Any) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    # -- high-level actions -------------------------------------------------

    def _initialize(self) -> None:
        if self._initialized:
            return
        init_params = {
            "processId": os.getpid(),
            "rootUri": self.root_uri,
            "capabilities": {
                "textDocument": {
                    "definition":     {"linkSupport": False},
                    "references":     {},
                    "documentSymbol": {},
                    "hover":          {"contentFormat": ["plaintext"]},
                    "publishDiagnostics": {},
                },
                "workspace": {
                    "symbol": {},
                    "workspaceFolders": True,
                },
            },
            "workspaceFolders": [{"uri": self.root_uri, "name": "workspace"}],
        }
        self._request("initialize", init_params, timeout=15.0)
        self._notify("initialized", {})
        self._initialized = True

    def _open(self, path: str) -> None:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = ""
        self._notify("textDocument/didOpen", {
            "textDocument": {
                "uri": _path_to_uri(path),
                "languageId": _language_for_path(path) or "plaintext",
                "version": 1,
                "text": text,
            },
        })

    def definition(self, path: str, line: int, character: int) -> Any:
        self._open(path)
        return self._request("textDocument/definition", {
            "textDocument": {"uri": _path_to_uri(path)},
            "position": {"line": line, "character": character},
        })

    def references(self, path: str, line: int, character: int) -> Any:
        self._open(path)
        return self._request("textDocument/references", {
            "textDocument": {"uri": _path_to_uri(path)},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": True},
        })

    def hover(self, path: str, line: int, character: int) -> Any:
        self._open(path)
        return self._request("textDocument/hover", {
            "textDocument": {"uri": _path_to_uri(path)},
            "position": {"line": line, "character": character},
        })

    def symbols(self, path: str) -> Any:
        self._open(path)
        return self._request("textDocument/documentSymbol", {
            "textDocument": {"uri": _path_to_uri(path)},
        })

    def workspace_symbols(self, query: str) -> Any:
        return self._request("workspace/symbol", {"query": query})


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_clients: dict[str, LspClient] = {}
_clients_lock = threading.Lock()


def _client_for_language(lang: str) -> LspClient:
    with _clients_lock:
        if lang in _clients:
            return _clients[lang]
        servers = _load_servers()
        cfg = servers.get(lang)
        if not cfg:
            raise ValueError(f"No LSP server configured for language '{lang}'")
        root = os.getenv("TERMINAL_CWD") or os.getenv("HERMES_WORKSPACE") or os.getcwd()
        client = LspClient(
            name=lang,
            command=cfg["command"],
            args=list(cfg.get("args") or []),
            root_uri=Path(root).resolve().as_uri(),
        )
        client.start()
        _clients[lang] = client
        return client


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------

LSP_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "lsp",
        "description": (
            "Query a language server for code intelligence. Actions: "
            "`definition`, `references`, `hover`, `symbols`, `workspace_symbols`. "
            "`workspace_symbols` takes only `query`; the others take `path` and "
            "`line`/`character` (0-indexed). Returns raw LSP JSON."
        ),
        "parameters": {
            "type": "object",
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["definition", "references", "hover", "symbols", "workspace_symbols"],
                },
                "path":      {"type": "string", "description": "Absolute file path"},
                "line":      {"type": "integer", "description": "0-indexed line number"},
                "character": {"type": "integer", "description": "0-indexed column number"},
                "query":     {"type": "string", "description": "Symbol query for workspace_symbols"},
                "language":  {"type": "string", "description": "Override the language detected from the path extension"},
            },
        },
    },
}


def lsp_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    args = args if isinstance(args, dict) else {}
    action = (args.get("action") or "").strip()
    if not action:
        return json.dumps({"ok": False, "error": "action is required"})

    try:
        if action == "workspace_symbols":
            lang = (args.get("language") or "").strip()
            if not lang:
                return json.dumps({"ok": False, "error": "workspace_symbols requires `language`"})
            client = _client_for_language(lang)
            result = client.workspace_symbols(str(args.get("query") or ""))
            return json.dumps({"ok": True, "result": result.get("result")})

        path = args.get("path")
        if not path:
            return json.dumps({"ok": False, "error": f"{action} requires `path`"})
        abspath = os.path.abspath(os.path.expanduser(str(path)))
        lang = (args.get("language") or _language_for_path(abspath) or "").strip()
        if not lang:
            return json.dumps({"ok": False, "error": f"Could not infer language for {abspath}"})

        client = _client_for_language(lang)

        if action == "definition":
            line = int(args.get("line", 0)); ch = int(args.get("character", 0))
            result = client.definition(abspath, line, ch)
        elif action == "references":
            line = int(args.get("line", 0)); ch = int(args.get("character", 0))
            result = client.references(abspath, line, ch)
        elif action == "hover":
            line = int(args.get("line", 0)); ch = int(args.get("character", 0))
            result = client.hover(abspath, line, ch)
        elif action == "symbols":
            result = client.symbols(abspath)
        else:
            return json.dumps({"ok": False, "error": f"Unknown action '{action}'"})

        payload = result.get("result") if isinstance(result, dict) else result
        return json.dumps({"ok": True, "result": payload})
    except FileNotFoundError as exc:
        return json.dumps({"ok": False, "error": str(exc), "hint": "Install the LSP server and retry."})
    except TimeoutError as exc:
        return json.dumps({"ok": False, "error": str(exc)})
    except Exception as exc:
        logger.debug("level-up: LSP call failed: %s", exc, exc_info=True)
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def lsp_check() -> bool:
    """Tool is always available; individual languages may fail at call time."""
    return True
