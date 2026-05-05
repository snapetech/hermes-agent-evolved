"""Discord channel history retrieval tool."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from agent.redact import redact_sensitive_text
from tools.registry import registry

_DISCORD_API = "https://discord.com/api/v10"
_SNOWFLAKE_RE = re.compile(r"^\d{5,32}$")
_TARGET_RE = re.compile(r"^\s*(?:discord:)?(?:#)?([^:\s]+)(?::(\d{5,32}))?\s*$", re.IGNORECASE)


def _token() -> str:
    return (
        os.getenv("DISCORD_BOT_TOKEN")
        or os.getenv("HERMES_DISCORD_BOT_TOKEN")
        or ""
    ).strip()


def check_discord_history_requirements() -> bool:
    return bool(_token())


def _error(message: str, **extra: Any) -> str:
    payload = {"error": redact_sensitive_text(str(message))}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def _load_channel_directory() -> dict:
    try:
        from hermes_constants import get_hermes_home
        path = get_hermes_home() / "channel_directory.json"
    except Exception:
        path = None
    if not path or not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _candidate_channel_names(channel: dict) -> set[str]:
    names = set()
    for key in ("id", "chat_id", "name", "display_name"):
        value = str(channel.get(key) or "").strip()
        if value:
            names.add(value.lower())
            names.add(value.lstrip("#").lower())
    return names


def _resolve_channel_id(target: str) -> str:
    raw = str(target or "").strip()
    if not raw:
        return os.getenv("DISCORD_HOME_CHANNEL", "").strip()
    match = _TARGET_RE.match(raw)
    if match:
        first, thread = match.groups()
        if thread:
            return thread
        if _SNOWFLAKE_RE.match(first):
            return first
        raw = first
    raw_name = raw.lstrip("#").lower()
    directory = _load_channel_directory()
    for platform, channels in directory.items():
        if str(platform).lower() != "discord" or not isinstance(channels, list):
            continue
        for channel in channels:
            if not isinstance(channel, dict):
                continue
            if raw_name in _candidate_channel_names(channel):
                channel_id = str(channel.get("id") or channel.get("chat_id") or "").strip()
                if channel_id:
                    return channel_id
    return raw if _SNOWFLAKE_RE.match(raw) else ""


def _discord_get(path: str, params: dict[str, Any] | None = None) -> Any:
    token = _token()
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is not configured")
    query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v not in ("", None)})
    url = f"{_DISCORD_API}{path}{'?' + query if query else ''}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "HermesAgent (https://github.com/NousResearch/hermes-agent)",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 403:
            raise PermissionError(
                "Discord denied access. The bot needs View Channel and Read Message History for that channel."
            ) from exc
        if exc.code == 404:
            raise FileNotFoundError("Discord channel not found or not visible to the bot.") from exc
        raise RuntimeError(f"Discord API returned HTTP {exc.code}: {body[:500]}") from exc
    return json.loads(body) if body else None


def _format_message(msg: dict) -> dict:
    author = msg.get("author") if isinstance(msg.get("author"), dict) else {}
    attachments = msg.get("attachments") if isinstance(msg.get("attachments"), list) else []
    embeds = msg.get("embeds") if isinstance(msg.get("embeds"), list) else []
    return {
        "id": str(msg.get("id") or ""),
        "timestamp": msg.get("timestamp") or "",
        "edited_timestamp": msg.get("edited_timestamp"),
        "author": {
            "id": str(author.get("id") or ""),
            "username": author.get("username") or "",
            "global_name": author.get("global_name") or "",
            "bot": bool(author.get("bot")),
        },
        "content": str(msg.get("content") or ""),
        "attachments": [
            {
                "id": str(att.get("id") or ""),
                "filename": att.get("filename") or "",
                "content_type": att.get("content_type") or "",
                "url": att.get("url") or "",
                "size": att.get("size") or 0,
            }
            for att in attachments[:10]
            if isinstance(att, dict)
        ],
        "embeds": [
            {
                "title": embed.get("title") or "",
                "description": embed.get("description") or "",
                "url": embed.get("url") or "",
                "type": embed.get("type") or "",
            }
            for embed in embeds[:5]
            if isinstance(embed, dict)
        ],
        "reply_to": (msg.get("referenced_message") or {}).get("id")
        if isinstance(msg.get("referenced_message"), dict)
        else None,
    }


def discord_channel_history(args: dict, **_kw) -> str:
    """Read recent messages from a Discord channel using the bot token."""
    channel_id = _resolve_channel_id(str(args.get("channel") or args.get("target") or ""))
    if not channel_id:
        return _error(
            "No Discord channel was provided and DISCORD_HOME_CHANNEL is not configured. "
            "Use a channel ID, discord:<channel_id>, or a cached channel name."
        )
    try:
        limit = int(args.get("limit", 50) or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 100))
    params = {
        "limit": limit,
        "before": args.get("before"),
        "after": args.get("after"),
        "around": args.get("around"),
    }
    cursor_count = sum(1 for key in ("before", "after", "around") if params.get(key))
    if cursor_count > 1:
        return _error("Use only one of before, after, or around.")

    try:
        messages = _discord_get(f"/channels/{channel_id}/messages", params)
        if not isinstance(messages, list):
            return _error("Discord returned an unexpected response shape.")
        formatted = [_format_message(msg) for msg in reversed(messages) if isinstance(msg, dict)]
        return json.dumps(
            {
                "channel_id": channel_id,
                "count": len(formatted),
                "order": "chronological",
                "messages": formatted,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return _error(exc)


DISCORD_CHANNEL_HISTORY_SCHEMA = {
    "name": "discord_channel_history",
    "description": (
        "Read recent messages from a Discord channel visible to the configured bot. "
        "Use this when the user asks what happened in Discord, in #hermes, or in a Discord channel. "
        "Requires DISCORD_BOT_TOKEN and bot permissions: View Channel + Read Message History."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": (
                    "Discord channel ID, 'discord:<channel_id>', cached channel name like '#hermes', "
                    "or empty to use DISCORD_HOME_CHANNEL."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Number of messages to read, 1-100. Defaults to 50.",
            },
            "before": {"type": "string", "description": "Optional Discord message ID cursor."},
            "after": {"type": "string", "description": "Optional Discord message ID cursor."},
            "around": {"type": "string", "description": "Optional Discord message ID cursor."},
        },
        "required": [],
    },
}


registry.register(
    name="discord_channel_history",
    toolset="messaging",
    schema=DISCORD_CHANNEL_HISTORY_SCHEMA,
    handler=discord_channel_history,
    check_fn=check_discord_history_requirements,
    requires_env=["DISCORD_BOT_TOKEN"],
    emoji="💬",
)
