"""Cross-process admission control for main LLM calls.

Hermes can run multiple frontends at once (gateway plus one or more TUI
processes).  In-process locks do not coordinate those independent Python
processes, so local model endpoints can receive more concurrent requests than
they can handle.  This module provides a small file-lock backed semaphore keyed
by model route.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import os
import socket
import time
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import urlsplit

from hermes_constants import get_hermes_home

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None

_QUEUE_DEPTH: contextvars.ContextVar[int] = contextvars.ContextVar(
    "hermes_llm_call_queue_depth", default=0
)


def _load_cfg() -> dict:
    try:
        import yaml

        path = get_hermes_home() / "config.yaml"
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _is_local_base_url(base_url: str) -> bool:
    try:
        host = urlsplit(str(base_url or "")).hostname or ""
    except Exception:
        host = ""
    if not host:
        return False
    lowered = host.lower()
    if lowered in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = socket.gethostbyname(lowered)
    except Exception:
        ip = lowered
    if ip.startswith(("127.", "10.", "192.168.")):
        return True
    if ip.startswith("172."):
        try:
            second = int(ip.split(".", 2)[1])
            return 16 <= second <= 31
        except Exception:
            return False
    return False


def _route_key(model: str, provider: str, base_url: str, api_mode: str) -> str:
    material = json.dumps(
        {
            "api_mode": str(api_mode or ""),
            "base_url": str(base_url or "").rstrip("/"),
            "model": str(model or ""),
            "provider": str(provider or "").lower(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _configured_concurrency(
    cfg: dict,
    *,
    model: str,
    provider: str,
    base_url: str,
    api_mode: str,
) -> int:
    queue_cfg = cfg.get("llm_call_queue") if isinstance(cfg.get("llm_call_queue"), dict) else {}
    enabled = queue_cfg.get("enabled", True)
    if str(enabled).strip().lower() in {"0", "false", "no", "off"}:
        return 0

    normalized_base = str(base_url or "").rstrip("/")
    normalized_provider = str(provider or "").strip().lower()
    normalized_model = str(model or "").strip()
    normalized_mode = str(api_mode or "").strip()

    route_blocks = []
    if isinstance(queue_cfg.get("routes"), list):
        route_blocks.extend(queue_cfg.get("routes") or [])
    qar = cfg.get("queue_aware_routing")
    if isinstance(qar, dict) and isinstance(qar.get("routes"), list):
        route_blocks.extend(qar.get("routes") or [])

    for raw in route_blocks:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("model") or "").strip() != normalized_model:
            continue
        if str(raw.get("provider") or "").strip().lower() != normalized_provider:
            continue
        if str(raw.get("base_url") or "").strip().rstrip("/") != normalized_base:
            continue
        raw_mode = str(raw.get("api_mode") or "").strip()
        if raw_mode and raw_mode != normalized_mode:
            continue
        try:
            return max(0, int(raw.get("max_concurrency")))
        except Exception:
            return 1

    if _is_local_base_url(normalized_base):
        try:
            return max(0, int(queue_cfg.get("local_max_concurrency", 1)))
        except Exception:
            return 1
    try:
        return max(0, int(queue_cfg.get("cloud_max_concurrency", 0)))
    except Exception:
        return 0


def _status_interval(cfg: dict) -> float:
    queue_cfg = cfg.get("llm_call_queue") if isinstance(cfg.get("llm_call_queue"), dict) else {}
    try:
        return max(1.0, float(queue_cfg.get("status_interval_seconds", 5)))
    except Exception:
        return 5.0


@contextlib.contextmanager
def acquire_llm_slot(
    *,
    model: str,
    provider: str,
    base_url: str,
    api_mode: str = "",
    operation: str = "llm_call",
    status_callback: Callable[[str], None] | None = None,
) -> Iterator[None]:
    """Acquire a route slot for the duration of a provider request.

    ``max_concurrency <= 0`` disables queueing for the route.  Nested calls in
    the same thread are treated as already admitted so helper fallbacks do not
    deadlock against their parent stream.
    """

    depth = _QUEUE_DEPTH.get()
    if depth > 0:
        token = _QUEUE_DEPTH.set(depth + 1)
        try:
            yield
        finally:
            _QUEUE_DEPTH.reset(token)
        return

    cfg = _load_cfg()
    max_concurrency = _configured_concurrency(
        cfg,
        model=model,
        provider=provider,
        base_url=base_url,
        api_mode=api_mode,
    )
    if max_concurrency <= 0:
        yield
        return
    if fcntl is None:
        yield
        return

    queue_dir = get_hermes_home() / "runtime" / "llm-call-queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    key = _route_key(model, provider, base_url, api_mode)
    interval = _status_interval(cfg)
    label = f"{provider or 'provider'}:{model or 'model'}"
    start = time.monotonic()
    last_status = 0.0
    handle = None
    slot_path: Path | None = None

    token = _QUEUE_DEPTH.set(1)
    try:
        while True:
            for idx in range(max_concurrency):
                candidate = queue_dir / f"{key}.{idx}.lock"
                candidate.parent.mkdir(parents=True, exist_ok=True)
                fh = open(candidate, "a+", encoding="utf-8")
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    fh.close()
                    continue
                handle = fh
                slot_path = candidate
                try:
                    fh.seek(0)
                    fh.truncate()
                    fh.write(
                        json.dumps(
                            {
                                "api_mode": api_mode,
                                "base_url": base_url,
                                "model": model,
                                "operation": operation,
                                "pid": os.getpid(),
                                "provider": provider,
                                "started_at": time.time(),
                            },
                            sort_keys=True,
                        )
                    )
                    fh.write("\n")
                    fh.flush()
                except Exception:
                    pass
                waited = time.monotonic() - start
                if waited >= 1.0 and status_callback:
                    status_callback(f"model slot acquired after {int(waited)}s: {label}")
                yield
                return

            now = time.monotonic()
            if status_callback and (now - last_status >= interval):
                waited = int(now - start)
                status_callback(f"waiting for model slot ({waited}s): {label}")
                last_status = now
            time.sleep(0.25)
    finally:
        _QUEUE_DEPTH.reset(token)
        if handle is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                handle.close()
            except Exception:
                pass
        if slot_path is not None:
            try:
                slot_path.unlink(missing_ok=True)
            except Exception:
                pass
