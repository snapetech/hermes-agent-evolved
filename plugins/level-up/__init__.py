"""Level-up plugin: wire hooks, commands, and tools into Hermes.

Entry point for the level-up plugin. See the individual modules for
implementation details:

    - recovery.py         typed failure taxonomy + recipes
    - escalation.py       file/webhook/discord alert channels
    - harvest.py          memory extraction from recent sessions
    - correction_guard.py overlap-based pre_tool_call gate
    - task_packet.py      structured /task wrapper over delegate_task
    - promote.py          promote harvested entries into live memory
    - boot_check.py       executable BOOT.md checks
    - metrics.py          per-tool latency/result-size observer
    - skill_audit.py      stale SKILL.md/MEMORY/SOUL reference audit
    - decision_hygiene.py decisions.jsonl stale/overlap audit
    - lsp_tool.py         stdio LSP client exposed as the `lsp` tool
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import (
    boot_check,
    correction_guard,
    decision_hygiene,
    harvest,
    lsp_tool,
    metrics,
    promote,
    recovery,
    self_review,
    skill_audit,
    task_packet,
)

logger = logging.getLogger(__name__)


def register(ctx) -> None:
    # Hooks
    ctx.register_hook("post_tool_call", recovery.post_tool_call_hook)
    ctx.register_hook("post_tool_call", metrics.post_tool_call_hook)
    ctx.register_hook("pre_tool_call", correction_guard.pre_tool_call_hook)
    ctx.register_hook("on_session_end", harvest.on_session_end_hook)

    # Slash commands
    ctx.register_command(
        "recovery",
        recovery.recovery_command,
        description="Show recent tool-failure recovery events",
    )
    ctx.register_command(
        "harvest",
        harvest.harvest_command,
        description="Extract durable memories from recent sessions",
    )
    ctx.register_command(
        "self-review",
        self_review.self_review_command,
        description="Cluster recurring failures, auto-apply low-risk lessons, and write a review queue",
    )
    ctx.register_command(
        "promote",
        promote.promote_command,
        description="Promote a harvested entry into MEMORY.md, USER.md, SOUL.md, or Hindsight",
    )
    ctx.register_command(
        "boot-check",
        boot_check.boot_check_command,
        description="Run executable BOOT.md health checks",
    )
    ctx.register_command(
        "skill-audit",
        skill_audit.skill_audit_command,
        description="Scan skills and memory files for stale path and URL references",
    )
    ctx.register_command(
        "decision-hygiene",
        decision_hygiene.decision_hygiene_command,
        description="Audit decisions.jsonl for stale entries and probable contradictions",
    )
    ctx.register_command(
        "decisions-audit",
        decision_hygiene.decision_hygiene_command,
        description="Alias for /decision-hygiene",
    )

    def _task(raw_args: str = "") -> str:
        return task_packet.task_command(raw_args, ctx=ctx)

    ctx.register_command(
        "task",
        _task,
        description="Run a structured TaskPacket through delegate_task",
    )

    # Tools
    ctx.register_tool(
        name="lsp",
        toolset="code_intel",
        schema=lsp_tool.LSP_TOOL_SCHEMA,
        handler=lsp_tool.lsp_handler,
        check_fn=lsp_tool.lsp_check,
        description="Query a language server for definitions, references, hover, and symbols.",
        emoji="🔎",
    )

    # Skill — operator-facing reference for the six surfaces.
    skill = Path(__file__).parent / "skills" / "level-up-ops" / "SKILL.md"
    if skill.exists():
        ctx.register_skill(
            "level-up-ops",
            skill,
            description="How to use recovery, escalation, harvest, promotion, boot checks, audits, TaskPacket, LSP, and the shared-memory MCP bridge.",
        )

    logger.info("level-up plugin registered: hooks + slash commands + lsp tool + level-up-ops skill")
