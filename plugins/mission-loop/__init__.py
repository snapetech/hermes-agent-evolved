"""Mission-loop plugin.

Provides a Hermes-native Ralph-style outer loop:

* mission state is persisted under ``$HERMES_HOME/missions/<id>/``
* each execution iteration starts from a fresh ``AIAgent`` context
* progress, verifier output, and agent responses are written to disk
* loops are bounded by explicit iteration limits and verifier success

The plugin is inert unless enabled in ``plugins.enabled`` and explicitly
invoked through ``/mission`` or the ``mission_loop`` tool.
"""

from __future__ import annotations

from . import mission_loop as ml


MISSION_LOOP_SCHEMA = {
    "name": "mission_loop",
    "description": (
        "Create and manage durable Ralph-style mission loops. Use this for "
        "long-running, verifier-gated work that should refresh context between "
        "iterations by persisting state to disk instead of carrying a huge chat "
        "history. Running iterations is explicit and bounded."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "create",
                    "list",
                    "status",
                    "record",
                    "verify",
                    "render_prompt",
                    "run",
                ],
                "description": "Operation to perform.",
            },
            "mission_id": {
                "type": "string",
                "description": "Mission ID for status, record, verify, render_prompt, or run.",
            },
            "title": {
                "type": "string",
                "description": "Short human-readable title for create.",
            },
            "spec": {
                "type": "string",
                "description": "Mission specification / acceptance criteria for create.",
            },
            "workdir": {
                "type": "string",
                "description": "Workspace directory. Defaults to current working directory.",
            },
            "verifier": {
                "type": "string",
                "description": "Shell verifier command run in workdir. Success is exit code 0.",
            },
            "max_iterations": {
                "type": "integer",
                "description": "Maximum total iterations for this mission.",
                "default": 10,
            },
            "iterations": {
                "type": "integer",
                "description": "Maximum iterations to execute for this run action.",
                "default": 1,
            },
            "note": {
                "type": "string",
                "description": "Progress note for record action.",
            },
            "status": {
                "type": "string",
                "description": "Optional status for record action.",
            },
            "success_marker": {
                "type": "string",
                "description": "Marker the agent may include when it believes done. Verification still decides completion.",
                "default": "VERIFIED_DONE",
            },
        },
        "required": ["action"],
    },
}


def _tool_handler(args: dict, **_: object) -> str:
    return ml.mission_loop_tool(args if isinstance(args, dict) else {})


def register(ctx) -> None:
    ctx.register_command(
        "mission",
        ml.handle_slash,
        description="Create, inspect, verify, and run durable verifier-gated mission loops",
        args_hint="<create|list|status|record|verify|prompt|run> ...",
    )
    ctx.register_tool(
        name="mission_loop",
        toolset="mission_loop",
        schema=MISSION_LOOP_SCHEMA,
        handler=_tool_handler,
        check_fn=lambda: True,
        description=MISSION_LOOP_SCHEMA["description"],
        emoji="",
    )
