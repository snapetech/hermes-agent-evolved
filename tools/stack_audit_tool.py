"""Hermes stack inventory and CVE audit tool."""

from __future__ import annotations

import json
from pathlib import Path

from tools.registry import registry, tool_error


def _run_stack_audit(action: str = "audit", schedule: str = "0 9 * * 1") -> str:
    try:
        from scripts.stack_cve_check import (
            DEFAULT_INVENTORY,
            DEFAULT_REPORT,
            audit_inventory,
            install_cron_job,
            write_inventory,
            write_report,
        )

        action = (action or "audit").strip().lower()
        result: dict = {"success": True, "action": action}

        if action in {"inventory", "audit"}:
            inventory = write_inventory()
            result["inventory_path"] = str(DEFAULT_INVENTORY)
            result["inventory_counts"] = {
                "python_installed": len(inventory.get("python", {}).get("installed", [])),
                "npm_locks": len(inventory.get("node", {}).get("locks", [])),
                "npm_globals": len(inventory.get("runtime", {}).get("npm_globals", {}).get("packages", [])),
                "system_packages": len(inventory.get("runtime", {}).get("system_packages", {}).get("packages", [])),
                "kubernetes_images": len(inventory.get("runtime", {}).get("kubernetes_images", {}).get("images", [])),
                "workspace_repos": len(inventory.get("runtime", {}).get("workspace_repos", [])),
                "skills": inventory.get("skills", {}).get("count", 0),
                "core_tools": len(inventory.get("tools", {}).get("core_tools", [])),
            }

        if action == "audit":
            audit = audit_inventory(inventory)
            report_json = Path(DEFAULT_REPORT).with_suffix(".json")
            report_json.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            write_report(audit)
            result.update({
                "report_path": str(DEFAULT_REPORT),
                "report_json_path": str(report_json),
                "osv_findings": audit.get("osv", {}).get("finding_count", 0),
                "npm_audit_totals": audit.get("npm_audit", {}).get("totals", {}),
                "recommendations": audit.get("recommendations", []),
            })

        elif action == "install_cron":
            result["cron"] = install_cron_job(schedule)

        elif action != "inventory":
            return tool_error("action must be one of: inventory, audit, install_cron", success=False)

        return json.dumps(result, indent=2, default=str)
    except Exception as exc:
        return tool_error(f"stack_audit failed: {type(exc).__name__}: {exc}", success=False)


STACK_AUDIT_SCHEMA = {
    "name": "stack_audit",
    "description": (
        "Maintain Hermes' stack inventory and run conservative CVE checks. "
        "Actions: inventory writes docs/stack-inventory.json; audit also writes "
        "docs/stack-cve-report.md; install_cron creates a recurring weekly check."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["inventory", "audit", "install_cron"],
                "description": "What to do. Default: audit.",
                "default": "audit",
            },
            "schedule": {
                "type": "string",
                "description": "Cron expression for install_cron. Default: Monday 09:00.",
                "default": "0 9 * * 1",
            },
        },
    },
}


registry.register(
    name="stack_audit",
    toolset="stack_audit",
    schema=STACK_AUDIT_SCHEMA,
    handler=lambda args, **kw: _run_stack_audit(
        action=args.get("action", "audit"),
        schedule=args.get("schedule", "0 9 * * 1"),
    ),
    check_fn=lambda: True,
    emoji="🛡️",
    max_result_size_chars=100_000,
)
