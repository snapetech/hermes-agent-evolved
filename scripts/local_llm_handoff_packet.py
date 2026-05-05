#!/usr/bin/env python3
"""Create deterministic approval handoff packets for local-LLM promotions."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "unnamed"


def handoff_root() -> Path:
    return get_hermes_home() / "self-improvement" / "local-llm-nightly" / "handoffs"


def build_packet(
    *,
    kind: str,
    title: str,
    summary: str,
    reasoning: str,
    report_path: str = "",
    evidence: list[str] | None = None,
    recipient: str = "keith@snape.tech",
    base_branch: str = "main",
) -> dict[str, Any]:
    date = _today()
    slug = _slugify(title)
    branch_name = f"llm-handoff/{date}-{slug}"
    pr_title = f"{kind}: {title}"
    evidence = [item.strip() for item in (evidence or []) if item.strip()]
    handoff_dir = handoff_root() / f"{date}-{slug}"
    return {
        "schema_version": 1,
        "kind": kind,
        "title": title.strip(),
        "slug": slug,
        "date": date,
        "summary": summary.strip(),
        "reasoning": reasoning.strip(),
        "report_path": report_path.strip(),
        "recipient": recipient,
        "branch_name": branch_name,
        "base_branch": base_branch,
        "pr_title": pr_title,
        "handoff_dir": str(handoff_dir),
        "evidence": evidence,
        "paths": {
            "packet_json": str(handoff_dir / "packet.json"),
            "pr_body_md": str(handoff_dir / "pr_body.md"),
            "email_txt": str(handoff_dir / "email.txt"),
        },
    }


def render_pr_body(packet: dict[str, Any]) -> str:
    evidence = packet.get("evidence") or []
    evidence_lines = "\n".join(f"- {item}" for item in evidence) if evidence else "- See latest nightly report and benchmark docs."
    report_line = f"- Nightly report: `{packet['report_path']}`" if packet.get("report_path") else "- Nightly report path was not provided."
    return (
        f"## Summary\n"
        f"- {packet['summary']}\n\n"
        f"## Reasoning\n"
        f"{packet['reasoning']}\n\n"
        f"## Evidence\n"
        f"{report_line}\n"
        f"{evidence_lines}\n\n"
        f"## Human Approval Required\n"
        f"- This change was escalated from the Hermes local-LLM nightly review.\n"
        f"- Approval is required before any live promotion or remediation is applied.\n"
        f"- Review routing, rollback, and operational fit before merge.\n"
    )


def render_email(packet: dict[str, Any]) -> str:
    return (
        f"Subject: Hermes local LLM {packet['kind']} needs approval: {packet['title']}\n"
        f"To: {packet['recipient']}\n\n"
        f"Hermes identified a local-LLM {packet['kind']} that needs human approval.\n\n"
        f"Summary:\n{packet['summary']}\n\n"
        f"Reasoning:\n{packet['reasoning']}\n\n"
        f"Branch:\n{packet['branch_name']}\n\n"
        f"PR title:\n{packet['pr_title']}\n\n"
        f"Report:\n{packet['report_path'] or 'not provided'}\n"
    )


def write_packet(packet: dict[str, Any]) -> dict[str, Any]:
    handoff_dir = Path(packet["handoff_dir"])
    handoff_dir.mkdir(parents=True, exist_ok=True)
    Path(packet["paths"]["packet_json"]).write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    Path(packet["paths"]["pr_body_md"]).write_text(render_pr_body(packet), encoding="utf-8")
    Path(packet["paths"]["email_txt"]).write_text(render_email(packet), encoding="utf-8")
    return packet


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["promotion", "remediation"], required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--reasoning", required=True)
    parser.add_argument("--report-path", default="")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--recipient", default="keith@snape.tech")
    parser.add_argument("--base-branch", default="main")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    packet = build_packet(
        kind=args.kind,
        title=args.title,
        summary=args.summary,
        reasoning=args.reasoning,
        report_path=args.report_path,
        evidence=args.evidence,
        recipient=args.recipient,
        base_branch=args.base_branch,
    )
    write_packet(packet)
    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
