"""Escalation channels for level-up plugin.

Delivers structured alerts to file, Discord home channel, or an arbitrary
webhook. Used by recovery recipes, the correction guard, and any plugin
module that wants to page the operator without blocking on stdin.

Configuration lives in `$HERMES_HOME/level_up/escalation.yaml`:

    default: file
    channels:
      file:
        type: file
        path: $HERMES_HOME/level_up/escalations.log
      discord:
        type: discord
        channel: home
      ntfy:
        type: webhook
        url: https://ntfy.sh/my-topic
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


@dataclass
class Escalation:
    reason: str
    category: str = "general"
    severity: str = "warn"
    details: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


def _config_path() -> Path:
    return get_hermes_home() / "level_up" / "escalation.yaml"


def _default_log_path() -> Path:
    return get_hermes_home() / "level_up" / "escalations.log"


def _load_config() -> dict[str, Any]:
    path = _config_path()
    if not path.exists():
        return {"default": "file", "channels": {"file": {"type": "file", "path": str(_default_log_path())}}}
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("level-up: failed to load escalation config: %s", exc)
        return {"default": "file", "channels": {"file": {"type": "file", "path": str(_default_log_path())}}}


def _expand(value: str) -> str:
    return os.path.expandvars(os.path.expanduser(value))


def _deliver_file(cfg: dict[str, Any], payload: dict[str, Any]) -> bool:
    raw = cfg.get("path") or str(_default_log_path())
    path = Path(_expand(raw))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return True


def _deliver_webhook(cfg: dict[str, Any], payload: dict[str, Any]) -> bool:
    url = cfg.get("url")
    if not url:
        return False
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    headers.update(cfg.get("headers") or {})
    req = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=5) as resp:
            return 200 <= resp.status < 300
    except (URLError, TimeoutError) as exc:
        logger.warning("level-up: webhook escalation failed: %s", exc)
        return False


def _deliver_discord(cfg: dict[str, Any], payload: dict[str, Any]) -> bool:
    target = cfg.get("channel") or "home"
    text = (
        f"🚨 **{payload['category']}** ({payload['severity']}): {payload['reason']}"
    )
    detail_preview = payload.get("details") or {}
    if detail_preview:
        text += "\n```\n" + json.dumps(detail_preview, indent=2)[:1500] + "\n```"
    try:
        from gateway.platforms.discord import send_to_home_channel
    except Exception:
        logger.warning("level-up: discord gateway not available; falling back to file")
        return _deliver_file({"path": str(_default_log_path())}, payload)
    try:
        return bool(send_to_home_channel(text, channel=target))
    except Exception as exc:
        logger.warning("level-up: discord delivery failed: %s", exc)
        return False


_DELIVERERS = {
    "file": _deliver_file,
    "webhook": _deliver_webhook,
    "discord": _deliver_discord,
}

_RATE_LIMIT_WINDOW_S = 300
_RATE_LIMIT_MAX = 5
_RATE_STATE: dict[str, dict[str, Any]] = {}


def _rate_limit(esc: Escalation) -> tuple[bool, Escalation | None]:
    now = time.time()
    state = _RATE_STATE.setdefault(
        esc.category,
        {"window_start": now, "sent": 0, "suppressed": 0, "last_summary": 0.0},
    )
    if now - float(state["window_start"]) > _RATE_LIMIT_WINDOW_S:
        suppressed = int(state.get("suppressed") or 0)
        state.update({"window_start": now, "sent": 1, "suppressed": 0, "last_summary": 0.0})
        if suppressed:
            summary = Escalation(
                reason=f"{suppressed} more `{esc.category}` escalation(s) suppressed in the previous 5 minutes",
                category=esc.category,
                severity=esc.severity,
                details={"suppressed": suppressed, "window_seconds": _RATE_LIMIT_WINDOW_S},
            )
            return False, summary
        return False, None

    if int(state["sent"]) < _RATE_LIMIT_MAX:
        state["sent"] = int(state["sent"]) + 1
        return False, None

    state["suppressed"] = int(state.get("suppressed") or 0) + 1
    suppressed = int(state["suppressed"])
    if suppressed == 1 or now - float(state.get("last_summary") or 0.0) >= 60:
        state["last_summary"] = now
        summary = Escalation(
            reason=f"{suppressed} more `{esc.category}` escalation(s) suppressed in the last 5 minutes",
            category=esc.category,
            severity=esc.severity,
            details={"suppressed": suppressed, "window_seconds": _RATE_LIMIT_WINDOW_S},
        )
        return True, summary
    return True, None


def escalate(esc: Escalation, channel: str | None = None) -> bool:
    """Deliver an escalation and always persist a file copy as audit trail."""
    cfg = _load_config()
    payload = asdict(esc)

    # Always file-log for audit, even when another channel is also selected.
    _deliver_file({"path": str(_default_log_path())}, payload)

    suppressed, summary = _rate_limit(esc)
    if suppressed:
        if summary is not None:
            summary_payload = asdict(summary)
            _deliver_file({"path": str(_default_log_path())}, summary_payload)
            name = channel or cfg.get("default") or "file"
            channel_cfg = (cfg.get("channels") or {}).get(name) or {}
            kind = channel_cfg.get("type") or name
            deliverer = _DELIVERERS.get(kind, _deliver_file)
            try:
                return deliverer(channel_cfg, summary_payload)
            except Exception as exc:
                logger.warning("level-up: escalation summary via %s failed: %s", name, exc)
                return False
        return False
    if summary is not None:
        summary_payload = asdict(summary)
        _deliver_file({"path": str(_default_log_path())}, summary_payload)

    name = channel or cfg.get("default") or "file"
    channel_cfg = (cfg.get("channels") or {}).get(name) or {}
    kind = channel_cfg.get("type") or name
    deliverer = _DELIVERERS.get(kind, _deliver_file)
    try:
        return deliverer(channel_cfg, payload)
    except Exception as exc:
        logger.warning("level-up: escalation via %s failed: %s", name, exc)
        return False
