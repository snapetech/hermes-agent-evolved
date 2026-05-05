"""Tool for reviewing and promoting runtime package installs."""

from __future__ import annotations

import json

from tools.registry import registry
from tools.runtime_installs import (
    promote_runtime_packages,
    read_promoted_packages,
    read_runtime_installs,
)


def _all_ecosystems() -> list[str]:
    return ["apt", "pip", "npm"]


def runtime_installs(
    action: str = "list",
    ecosystem: str = "all",
    packages: list[str] | None = None,
    repo_root: str = "",
) -> str:
    action = (action or "list").strip().lower()
    ecosystem = (ecosystem or "all").strip().lower()
    try:
        if action == "list":
            ecosystems = _all_ecosystems() if ecosystem == "all" else [ecosystem]
            return json.dumps(
                {
                    "success": True,
                    "runtime_installs": {
                        name: read_runtime_installs(name, limit=50)
                        for name in ecosystems
                    },
                    "promoted_packages": {
                        name: read_promoted_packages(name, repo_root or None)
                        for name in ecosystems
                    },
                },
                ensure_ascii=False,
            )
        if action == "promote":
            if ecosystem == "all":
                if packages:
                    return json.dumps(
                        {
                            "success": False,
                            "error": "Specify ecosystem when promoting explicit packages.",
                        },
                        ensure_ascii=False,
                    )
                results = {
                    name: promote_runtime_packages(name, None, repo_root=repo_root or None)
                    for name in _all_ecosystems()
                }
                return json.dumps({"success": True, "results": results}, ensure_ascii=False)
            return json.dumps(
                {
                    "success": True,
                    **promote_runtime_packages(ecosystem, packages or None, repo_root=repo_root or None),
                },
                ensure_ascii=False,
            )
        return json.dumps({"success": False, "error": f"Unknown action: {action}"}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)


registry.register(
    name="runtime_installs",
    toolset="terminal",
    schema={
        "name": "runtime_installs",
        "description": (
            "Review runtime apt, pip, and npm installs captured from successful terminal commands, "
            "or promote useful packages into the deploy/k8s declarative package lists so future pods reproduce them."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "promote"],
                    "description": "list captured installs and baked packages, or promote packages into the image package list.",
                },
                "ecosystem": {
                    "type": "string",
                    "enum": ["all", "apt", "pip", "npm"],
                    "description": "Package ecosystem to inspect or promote. Use apt for image packages, pip for requirements-persistent.txt, npm for npm-global-packages.txt.",
                },
                "packages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific package names/specifiers to promote. Omit to promote all captured runtime packages for the selected ecosystem.",
                },
                "repo_root": {
                    "type": "string",
                    "description": (
                        "Repository root containing deploy/k8s package list files. "
                        "Defaults to the current git checkout, then HERMES_HOME/hermes-agent, "
                        "then /opt/data/hermes-agent before falling back to the current directory."
                    ),
                },
            },
            "required": ["action"],
        },
    },
    handler=lambda args, **_kw: runtime_installs(
        action=args.get("action", "list"),
        ecosystem=args.get("ecosystem", "all"),
        packages=args.get("packages"),
        repo_root=args.get("repo_root", ""),
    ),
)
