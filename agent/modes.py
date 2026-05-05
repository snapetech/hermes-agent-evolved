from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from toolsets import resolve_multiple_toolsets


@dataclass(frozen=True)
class AgentMode:
    name: str
    description: str
    persona: str = ""
    allowed_tools: frozenset[str] | None = None
    denied_tools: frozenset[str] = frozenset()
    ask_tools: frozenset[str] = frozenset()


_ASK_READONLY_TOOLSETS = [
    "web",
    "vision",
    "file",
    "session_search",
    "skills",
    "todo",
]

_ASK_ALLOWED = frozenset(resolve_multiple_toolsets(_ASK_READONLY_TOOLSETS)) - {
    "write_file",
    "patch",
    "terminal",
    "process",
    "execute_code",
    "delegate_task",
    "send_message",
    "skill_manage",
}

_ARCHITECT_ALLOWED = frozenset(
    set(_ASK_ALLOWED)
    | set(resolve_multiple_toolsets(["browser"]))
) - {
    "browser_click",
    "browser_type",
    "browser_press",
}

_DEBUG_ALLOWED = frozenset(
    set(resolve_multiple_toolsets(["web", "vision", "file", "terminal", "session_search", "skills", "todo"]))
    | {"clarify"}
)

_REVIEW_ALLOWED = frozenset(
    set(resolve_multiple_toolsets(["web", "vision", "file", "session_search", "skills", "todo"]))
    | {"clarify"}
) - {
    "write_file",
    "patch",
    "skill_manage",
}

_ORCHESTRATOR_ALLOWED = frozenset(
    set(resolve_multiple_toolsets(["web", "file", "terminal", "session_search", "skills", "todo", "delegation"]))
    | {"clarify"}
) - {
    "write_file",
    "patch",
    "execute_code",
    "skill_manage",
}


BUILT_IN_MODES: dict[str, AgentMode] = {
    "code": AgentMode(
        name="code",
        description="Full-access coding mode.",
        persona="You are in code mode. Default to implementation work, use tools directly, and make concrete changes when appropriate.",
        allowed_tools=None,
    ),
    "ask": AgentMode(
        name="ask",
        description="Read-only exploration mode with no edits or execution.",
        persona="You are in ask mode. Focus on explanation, inspection, and analysis. Do not modify files or execute commands.",
        allowed_tools=_ASK_ALLOWED,
    ),
    "architect": AgentMode(
        name="architect",
        description="Planning mode with read-heavy access and confirmation-gated edits.",
        persona="You are in architect mode. Prioritize plans, tradeoffs, structure, and design rationale over direct implementation.",
        allowed_tools=_ARCHITECT_ALLOWED,
        denied_tools=frozenset({"terminal", "process", "execute_code", "delegate_task", "send_message"}),
        ask_tools=frozenset({"write_file", "patch"}),
    ),
    "debug": AgentMode(
        name="debug",
        description="Diagnostic mode with execution access but confirmation-gated edits.",
        persona="You are in debug mode. Be systematic, form concrete hypotheses, gather evidence, and isolate faults before editing.",
        allowed_tools=_DEBUG_ALLOWED,
        ask_tools=frozenset({"write_file", "patch"}),
    ),
    "review": AgentMode(
        name="review",
        description="Code review mode focused on reading and evaluating changes.",
        persona="You are in review mode. Prioritize bugs, regressions, risk, and missing tests. Avoid making changes unless explicitly needed.",
        allowed_tools=_REVIEW_ALLOWED,
    ),
    "orchestrator": AgentMode(
        name="orchestrator",
        description="Coordination mode for breaking work into steps and delegating.",
        persona="You are in orchestrator mode. Break problems down, route work intentionally, and avoid direct edits unless necessary.",
        allowed_tools=_ORCHESTRATOR_ALLOWED,
        denied_tools=frozenset({"write_file", "patch", "execute_code"}),
    ),
}


def get_agent_mode(name: Optional[str]) -> AgentMode:
    key = (name or "code").strip().lower() or "code"
    return BUILT_IN_MODES.get(key, BUILT_IN_MODES["code"])


def list_agent_modes() -> list[AgentMode]:
    return [BUILT_IN_MODES[name] for name in ("code", "ask", "architect", "debug", "review", "orchestrator")]


def compose_mode_prompt(base_prompt: str, mode_name: Optional[str]) -> str:
    mode = get_agent_mode(mode_name)
    persona = "" if mode.name == "code" else mode.persona
    parts = [part.strip() for part in (base_prompt or "", persona or "") if str(part or "").strip()]
    return "\n\n".join(parts)


def build_mode_policy(mode_name: Optional[str]) -> dict[str, object]:
    mode = get_agent_mode(mode_name)
    allowed = None if mode.allowed_tools is None else sorted(mode.allowed_tools)
    return {
        "name": mode.name,
        "description": mode.description,
        "allowed_tools": allowed,
        "denied_tools": sorted(mode.denied_tools),
        "ask_tools": sorted(mode.ask_tools),
    }


def describe_mode(mode_name: Optional[str]) -> str:
    mode = get_agent_mode(mode_name)
    details = [f"`{mode.name}` — {mode.description}"]
    if mode.allowed_tools is not None:
        details.append(f"allowed: {len(mode.allowed_tools)} tool(s)")
    if mode.ask_tools:
        details.append(f"ask: {', '.join(sorted(mode.ask_tools))}")
    if mode.denied_tools:
        details.append(f"deny: {', '.join(sorted(mode.denied_tools))}")
    return " | ".join(details)
