#!/usr/bin/env python3
"""Summarize Hermes benchmark result JSON into per-model capability cards.

The benchmark suite is intentionally practical: a model can be rejected for
primary/approval use and still be worth tracking for a narrow side task. This
script preserves those niches instead of flattening every run to one score.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


CRITICAL_TASKS = {
    "utility_route_message_json",
    "utility_approval_risk_json",
    "utility_readonly_risk_json",
    "utility_restart_cooldown_json",
    "slm_mutation_guard_json",
}

TASK_LABELS = {
    "logic_number": "numeric instruction following",
    "logic_consistency": "logic consistency",
    "logic_json_rule": "structured logic JSON",
    "utility_route_message_json": "ops routing with approval flag",
    "utility_extract_actions_json": "operator-note extraction",
    "utility_approval_risk_json": "approval-risk labeling",
    "utility_pulse_condense": "short pulse condensation",
    "utility_admission_compaction_json": "admission compaction decision",
    "utility_failover_lane_json": "failover lane selection",
    "utility_readonly_risk_json": "read-only approval-risk labeling",
    "utility_restart_cooldown_json": "restart cooldown decision",
    "slm_intent_route_json": "short intent routing",
    "slm_queue_wait_or_fallback_json": "queue wait vs fallback decision",
    "slm_mutation_guard_json": "mutation guard classification",
    "slm_extract_service_command_json": "service command extraction",
    "slm_portuguese_status_summary": "Portuguese status summary",
    "slm_spanish_status_summary": "Spanish status summary",
    "read_config_answer": "workspace config lookup",
    "read_override_config_answer": "override config merge",
    "discord_status_reply": "Discord status reply",
    "patch_python_bug": "small code patch",
    "patch_retry_after_bug": "retry-after code fix",
    "patch_json_guard_bug": "JSON guard code fix",
    "synthesize_summary_file": "file synthesis",
    "compose_json_result": "workspace JSON composition",
    "synthesize_incident_brief_json": "incident brief synthesis",
    "discord_triage_reply": "Discord triage reply",
}


def _load_results(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("results") or []:
            row = dict(row)
            row["_source"] = str(path)
            rows.append(row)
    return rows


def _group(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        model = str(row.get("model") or "")
        if not model:
            continue
        model_data = grouped.setdefault(
            model,
            {
                "runs": 0,
                "passed": 0,
                "elapsed": 0.0,
                "tasks": defaultdict(lambda: {"runs": 0, "passed": 0, "elapsed": 0.0}),
                "failures": defaultdict(list),
                "sources": set(),
            },
        )
        model_data["runs"] += 1
        model_data["passed"] += int(bool(row.get("passed")))
        model_data["elapsed"] += float(row.get("elapsed_seconds") or 0.0)
        model_data["sources"].add(row.get("_source"))

        task = str(row.get("task") or "")
        task_data = model_data["tasks"][task]
        task_data["runs"] += 1
        task_data["passed"] += int(bool(row.get("passed")))
        task_data["elapsed"] += float(row.get("elapsed_seconds") or 0.0)
        if not row.get("passed"):
            task_data_failures = model_data["failures"][task]
            response = str(row.get("response") or "").strip().replace("\n", " ")
            if response:
                task_data_failures.append(response[:220])
    return grouped


def _rate(passed: int, runs: int) -> float:
    return round(passed / max(runs, 1), 3)


def _verdict(task: str, pass_rate: float) -> str:
    if task in CRITICAL_TASKS and pass_rate < 1.0:
        return "exclude from approval/routing"
    if pass_rate >= 0.9:
        return "candidate strength"
    if pass_rate >= 0.67:
        return "promising, needs more reps"
    if pass_rate > 0:
        return "unstable"
    return "failed"


def render_markdown(paths: list[Path]) -> str:
    grouped = _group(_load_results(paths))
    lines = [
        "# Model Capability Cards",
        "",
        "Generated from Hermes benchmark result JSON. Keep these cards focused on model routing decisions, not leaderboard claims.",
        "",
    ]

    for model, data in sorted(grouped.items()):
        runs = int(data["runs"])
        passed = int(data["passed"])
        avg_elapsed = round(float(data["elapsed"]) / max(runs, 1), 2)
        lines.extend(
            [
                f"## `{model}`",
                "",
                f"- Overall: {passed}/{runs} ({_rate(passed, runs):.3f}), avg {avg_elapsed}s/task",
                f"- Sources: {', '.join(sorted(str(src) for src in data['sources'] if src))}",
                "",
                "| Task | Pass | Avg s | Verdict |",
                "| --- | ---: | ---: | --- |",
            ]
        )

        strong: list[str] = []
        exclusions: list[str] = []
        for task, task_data in sorted(data["tasks"].items()):
            task_runs = int(task_data["runs"])
            task_passed = int(task_data["passed"])
            pass_rate = _rate(task_passed, task_runs)
            avg_task = round(float(task_data["elapsed"]) / max(task_runs, 1), 2)
            verdict = _verdict(task, pass_rate)
            label = TASK_LABELS.get(task, task)
            lines.append(f"| {label} | {task_passed}/{task_runs} | {avg_task:.2f} | {verdict} |")
            if verdict == "candidate strength":
                strong.append(label)
            if "exclude" in verdict:
                exclusions.append(label)

        lines.append("")
        if strong:
            lines.append(f"- Good for: {', '.join(strong)}.")
        else:
            lines.append("- Good for: no stable niche proven yet.")
        if exclusions:
            lines.append(f"- Do not use for: {', '.join(exclusions)}.")
        else:
            lines.append("- Do not use for: no critical exclusion shown by these runs.")

        failure_examples = []
        for task, examples in sorted(data["failures"].items()):
            if examples:
                failure_examples.append(f"{TASK_LABELS.get(task, task)} -> {examples[0]}")
        if failure_examples:
            lines.append("- Example failure signals:")
            for item in failure_examples[:4]:
                lines.append(f"  - {item}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", nargs="+", type=Path, help="Hermes benchmark results_*.json files")
    parser.add_argument("--output", type=Path, default=None, help="Optional markdown output path")
    args = parser.parse_args()

    markdown = render_markdown(args.results)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
