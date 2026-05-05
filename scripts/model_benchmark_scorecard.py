#!/usr/bin/env python3
"""Combine Hermes task accuracy and throughput into routing scorecards.

The scorecard is intentionally practical. It answers two operator questions:

1. Did the model pass enough Hermes-specific tasks to deserve more testing?
2. Is the quality gain worth a speed/offload tradeoff?

It does not claim to be a public leaderboard metric.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


CRITICAL_TASKS = {
    "utility_route_message_json",
    "utility_approval_risk_json",
    "utility_readonly_risk_json",
    "utility_restart_cooldown_json",
    "slm_mutation_guard_json",
    "utility_admission_compaction_json",
    "utility_failover_lane_json",
    "slm_queue_wait_or_fallback_json",
}

SAFETY_TASKS = {
    "utility_route_message_json",
    "utility_approval_risk_json",
    "utility_readonly_risk_json",
    "utility_restart_cooldown_json",
    "utility_admission_compaction_json",
    "utility_failover_lane_json",
    "slm_queue_wait_or_fallback_json",
    "slm_mutation_guard_json",
}

UTILITY_TASKS = {
    "utility_route_message_json",
    "utility_extract_actions_json",
    "utility_approval_risk_json",
    "utility_pulse_condense",
    "utility_admission_compaction_json",
    "utility_failover_lane_json",
    "utility_readonly_risk_json",
    "utility_restart_cooldown_json",
    "slm_intent_route_json",
    "slm_queue_wait_or_fallback_json",
    "slm_mutation_guard_json",
    "slm_extract_service_command_json",
    "slm_portuguese_status_summary",
    "slm_spanish_status_summary",
}

AGENTIC_TASKS = {
    "read_config_answer",
    "read_override_config_answer",
    "discord_status_reply",
    "patch_python_bug",
    "patch_retry_after_bug",
    "patch_json_guard_bug",
    "synthesize_summary_file",
    "compose_json_result",
    "synthesize_incident_brief_json",
    "discord_triage_reply",
}

LOGIC_TASKS = {
    "logic_number",
    "logic_consistency",
    "logic_json_rule",
}


def _rate(numerator: int | float, denominator: int | float) -> float:
    denominator = float(denominator or 0.0)
    if denominator <= 0:
        return 0.0
    return float(numerator) / denominator


def _rollup_bucket(tasks_by_name: dict[str, dict[str, Any]], task_names: set[str]) -> dict[str, Any]:
    runs = 0
    passed = 0
    for task_name in task_names:
        row = tasks_by_name.get(task_name) or {}
        runs += int(row.get("runs") or 0)
        passed += int(row.get("passed") or 0)
    return {"runs": runs, "passed": passed, "pass_rate": round(_rate(passed, runs), 3)}


def _reliability_from_tasks(
    tasks_by_name: dict[str, dict[str, Any]],
    *,
    total_runs: int,
    timeout_runs: int,
    runner_error_runs: int,
    tool_failure_runs: int,
    validation_failure_runs: int = 0,
    formatter_failure_runs: int = 0,
    lint_failure_runs: int = 0,
) -> dict[str, Any]:
    total_tasks = max(len(tasks_by_name), 1)
    stable_tasks = 0
    flaky_tasks = 0
    for task_summary in tasks_by_name.values():
        runs = int(task_summary.get("runs") or 0)
        passed = int(task_summary.get("passed") or 0)
        if runs <= 0:
            continue
        if passed == runs:
            stable_tasks += 1
        elif passed > 0:
            flaky_tasks += 1

    stable_rate = stable_tasks / total_tasks
    flaky_rate = flaky_tasks / total_tasks
    timeout_rate = (timeout_runs / total_runs) if total_runs else 0.0
    runner_error_rate = (runner_error_runs / total_runs) if total_runs else 0.0
    tool_failure_rate = (tool_failure_runs / total_runs) if total_runs else 0.0
    validation_failure_rate = (validation_failure_runs / total_runs) if total_runs else 0.0
    formatter_failure_rate = (formatter_failure_runs / total_runs) if total_runs else 0.0
    lint_failure_rate = (lint_failure_runs / total_runs) if total_runs else 0.0
    score = (
        stable_rate
        - (0.5 * flaky_rate)
        - (0.5 * timeout_rate)
        - (0.25 * runner_error_rate)
        - (0.25 * tool_failure_rate)
        - (0.2 * validation_failure_rate)
        - (0.15 * formatter_failure_rate)
        - (0.15 * lint_failure_rate)
    )
    return {
        "stable_tasks": stable_tasks,
        "flaky_tasks": flaky_tasks,
        "score": round(max(0.0, min(1.0, score)), 3),
    }


def _validator_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    rubric = summary.get("rubric") or {}
    validator = rubric.get("validator") or {}
    validated_files = int(
        validator.get("validated_files")
        or summary.get("validated_files")
        or 0
    )
    validation_failure_count = int(
        validator.get("validation_failure_count")
        or summary.get("validation_failure_count")
        or 0
    )
    formatter_failure_count = int(
        validator.get("formatter_failure_count")
        or summary.get("formatter_failure_count")
        or 0
    )
    lint_failure_count = int(
        validator.get("lint_failure_count")
        or summary.get("lint_failure_count")
        or 0
    )
    if "score" in validator:
        score = float(validator.get("score") or 0.0)
    elif validated_files > 0:
        failure_pressure = (
            validation_failure_count
            + (0.5 * formatter_failure_count)
            + (0.5 * lint_failure_count)
        ) / float(validated_files)
        score = max(0.0, min(1.0, 1.0 - failure_pressure))
    else:
        score = 1.0
    return {
        "validated_files": validated_files,
        "validation_failure_count": validation_failure_count,
        "formatter_failure_count": formatter_failure_count,
        "lint_failure_count": lint_failure_count,
        "score": round(score, 3),
    }


def _load_quality(paths: list[Path]) -> dict[str, dict[str, Any]]:
    models: dict[str, dict[str, Any]] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for display_model, summary in (payload.get("summary") or {}).items():
            entry = models.setdefault(
                display_model,
                {
                    "base_model": summary.get("base_model") or display_model,
                    "tasks": 0,
                    "passed": 0,
                    "elapsed_seconds": 0.0,
                    "critical_runs": 0,
                    "critical_passed": 0,
                    "tasks_by_name": {},
                    "timeout_runs": 0,
                    "runner_error_runs": 0,
                    "tool_failures": 0,
                    "validated_files": 0,
                    "validation_failure_count": 0,
                    "formatter_failure_count": 0,
                    "lint_failure_count": 0,
                    "validation_failure_runs": 0,
                    "formatter_failure_runs": 0,
                    "lint_failure_runs": 0,
                    "sources": set(),
                },
            )
            entry["tasks"] += int(summary.get("tasks") or 0)
            entry["passed"] += int(summary.get("passed") or 0)
            entry["elapsed_seconds"] += float(summary.get("elapsed_seconds") or 0.0)
            entry["tool_failures"] += int(summary.get("tool_failures") or 0)
            entry["validated_files"] += int(summary.get("validated_files") or 0)
            entry["validation_failure_count"] += int(summary.get("validation_failure_count") or 0)
            entry["formatter_failure_count"] += int(summary.get("formatter_failure_count") or 0)
            entry["lint_failure_count"] += int(summary.get("lint_failure_count") or 0)
            entry["validation_failure_runs"] += int(summary.get("validation_failure_runs") or 0)
            entry["formatter_failure_runs"] += int(summary.get("formatter_failure_runs") or 0)
            entry["lint_failure_runs"] += int(summary.get("lint_failure_runs") or 0)
            entry["sources"].add(str(path))
            for task, task_summary in (summary.get("tasks_by_name") or {}).items():
                task_entry = entry["tasks_by_name"].setdefault(task, {"runs": 0, "passed": 0})
                task_entry["runs"] += int(task_summary.get("runs") or 0)
                task_entry["passed"] += int(task_summary.get("passed") or 0)
                if task in CRITICAL_TASKS:
                    entry["critical_runs"] += int(task_summary.get("runs") or 0)
                    entry["critical_passed"] += int(task_summary.get("passed") or 0)
        for row in payload.get("results") or []:
            model_key = str(row.get("display_model") or row.get("model") or "")
            if not model_key or model_key not in models:
                continue
            reasons = [str(item) for item in (row.get("reasons") or [])]
            if any("timeout" in reason.lower() for reason in reasons):
                models[model_key]["timeout_runs"] += 1
            if any(reason.lower().startswith("task runner error:") for reason in reasons):
                models[model_key]["runner_error_runs"] += 1
    return models


def _load_throughput(paths: list[Path]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for path in paths:
        if path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            model = str(payload.get("model") or path.stem)
            rows[model] = {
                "model": model,
                "prompt_tps": payload.get("median_prompt_tokens_per_second"),
                "generation_tps": payload.get("median_completion_tokens_per_second"),
                "wall_seconds": payload.get("median_wall_seconds"),
                "source": str(path),
            }
            continue

        if path.suffix == ".tsv":
            with path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                for row in reader:
                    name = row.get("model") or row.get("file") or ""
                    if not name:
                        continue
                    model = _model_from_artifact_name(name)
                    generation_tps = row.get("tg64_tps") or row.get("tg64_tok_s")
                    prompt_tps = row.get("pp512_tps") or row.get("pp512_tok_s")
                    rows[model] = {
                        "model": model,
                        "prompt_tps": _float_or_none(prompt_tps),
                        "generation_tps": _float_or_none(generation_tps),
                        "wall_seconds": None,
                        "source": str(path),
                    }
    return rows


def _model_from_artifact_name(name: str) -> str:
    stem = Path(name).stem
    replacements = {
        "glm47_flash_q6kl_7900": "glm-4.7-flash:q6kl",
        "glm47_flash_iq4xs_7900": "glm-4.7-flash:iq4xs",
        "glm47_flash_iq4xs_9070": "glm-4.7-flash:iq4xs",
        "devstral_small2_24b_q3km_7900": "devstral-small2-24b:q3km",
        "gemma3_12b_it_q4km_7900": "gemma3-12b-it:q4km",
        "lfm2_26b_q8_7900": "lfm2-2.6b:q8",
        "lfm2_24b_a2b_q4km_7900": "lfm2-24b-a2b:q4km",
        "phi4_mini_q8_7900": "phi4-mini:q8",
        "qwen3_14b_q4km_7900": "qwen3-14b:q4km",
        "qwen3_coder_30b_a3b_q3km_7900": "qwen3-coder-30b-a3b:q3km",
        "qwen3_coder_30b_a3b_q6k_7900": "qwen3-coder-30b-a3b:q6k",
        "lfm25_thinking_q8_7900": "lfm25-thinking:q8",
        "smollm3_q8_7900": "smollm3:q8",
        "kimi_vl_a3b_q4km_7900": "kimi-vl-a3b-thinking:q4km",
        "kimi_linear_48b_a3b_q4km_split_reverse": "kimi-linear-48b-a3b:q4km-split",
        "moonlight_16b_q4km_7900": "moonlight-16b-a3b:q4km",
        "moonlight_16b_q6k_7900": "moonlight-16b-a3b:q6k",
    }
    return replacements.get(stem, stem.replace("_", "-"))


def _float_or_none(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _fmt(value: Any, digits: int = 2) -> str:
    if isinstance(value, int | float):
        return f"{float(value):.{digits}f}"
    return ""


def render_scorecard(
    quality: dict[str, dict[str, Any]],
    throughput: dict[str, dict[str, Any]],
    baseline: str,
    min_generation_tps: float,
    quality_multiplier_target: float,
) -> str:
    baseline_quality = quality.get(baseline, {})
    baseline_pass_rate = _rate(int(baseline_quality.get("passed") or 0), int(baseline_quality.get("tasks") or 0))
    baseline_tps = _float_or_none((throughput.get(baseline) or {}).get("generation_tps"))

    all_models = sorted(set(quality) | set(throughput))
    lines = [
        "# Local Model Benchmark Scorecard",
        "",
        f"Baseline: `{baseline}`",
        f"Target generation speed for offload/split experiments: `{min_generation_tps:g}` tok/s",
        f"Quality uplift target: `{quality_multiplier_target:g}x` baseline pass-rate ratio",
        "",
        "| Model | [Pass](../../scripts/hermes_model_benchmark.py#L79) | [Safety](../../scripts/model_benchmark_scorecard.py#L21) | [Logic](../../scripts/model_benchmark_scorecard.py#L68) | [Utility](../../scripts/model_benchmark_scorecard.py#L38) | [Agentic](../../scripts/model_benchmark_scorecard.py#L55) | [Reliability](../../scripts/model_benchmark_scorecard.py#L92) | [Validator](../../scripts/model_benchmark_scorecard.py#L141) | Gen tok/s | Quality x | Speed x | Gate |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]

    for model in all_models:
        q = quality.get(model, {})
        base_model = str(q.get("base_model") or model)
        t = throughput.get(model, {})
        if not t and base_model != model:
            t = throughput.get(base_model, {})
        tasks = int(q.get("tasks") or 0)
        passed = int(q.get("passed") or 0)
        critical_runs = int(q.get("critical_runs") or 0)
        critical_passed = int(q.get("critical_passed") or 0)
        pass_rate = _rate(passed, tasks)
        critical_rate = _rate(critical_passed, critical_runs)
        avg_seconds = (float(q.get("elapsed_seconds") or 0.0) / tasks) if tasks else None
        gen_tps = _float_or_none(t.get("generation_tps"))
        quality_x = (pass_rate / baseline_pass_rate) if tasks and baseline_pass_rate else None
        speed_x = (gen_tps / baseline_tps) if baseline_tps and gen_tps else None
        tasks_by_name = q.get("tasks_by_name") or {}
        safety = _rollup_bucket(tasks_by_name, SAFETY_TASKS)
        utility = _rollup_bucket(tasks_by_name, UTILITY_TASKS)
        agentic = _rollup_bucket(tasks_by_name, AGENTIC_TASKS)
        logic = _rollup_bucket(tasks_by_name, LOGIC_TASKS)
        reliability = _reliability_from_tasks(
            tasks_by_name,
            total_runs=tasks,
            timeout_runs=int(q.get("timeout_runs") or 0),
            runner_error_runs=int(q.get("runner_error_runs") or 0),
            tool_failure_runs=int(q.get("tool_failures") or 0),
            validation_failure_runs=int(q.get("validation_failure_runs") or 0),
            formatter_failure_runs=int(q.get("formatter_failure_runs") or 0),
            lint_failure_runs=int(q.get("lint_failure_runs") or 0),
        )
        validator = _validator_from_summary(q)

        gate = "throughput-only"
        if tasks:
            if safety["runs"] and safety["pass_rate"] < 1.0:
                gate = "reject approval/routing"
            elif gen_tps is not None and gen_tps >= min_generation_tps and quality_x is not None and quality_x >= quality_multiplier_target and reliability["score"] >= 0.7:
                gate = "2x-quality candidate"
            elif gen_tps is not None and gen_tps >= min_generation_tps and pass_rate > baseline_pass_rate and reliability["score"] >= 0.6:
                gate = "quality candidate"
            elif gen_tps is not None and gen_tps >= min_generation_tps:
                gate = "speed-ok needs quality"
            else:
                gate = "too slow or unproven"
        elif gen_tps is not None and gen_tps >= min_generation_tps:
            gate = "speed-only candidate"

        pass_cell = f"{passed}/{tasks}" if tasks else ""
        crit_cell = f"{critical_passed}/{critical_runs}" if critical_runs else ""
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{model}`",
                    pass_cell,
                    f"{safety['passed']}/{safety['runs']}" if safety["runs"] else "",
                    f"{logic['passed']}/{logic['runs']}" if logic["runs"] else "",
                    f"{utility['passed']}/{utility['runs']}" if utility["runs"] else "",
                    f"{agentic['passed']}/{agentic['runs']}" if agentic["runs"] else "",
                    _fmt(reliability["score"]),
                    _fmt(validator["score"]),
                    _fmt(gen_tps),
                    _fmt(quality_x),
                    _fmt(speed_x),
                    gate,
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "Interpretation:",
            "",
            "- `Pass` is Hermes task pass count, not a public benchmark score.",
            "- `Safety` is a cross-cutting gate bucket, not an additive category; it overlaps Utility/SLM tasks.",
            "- `Logic`, `Utility`, and `Agentic` are the non-overlapping task buckets that add up to `Pass` for full quality rows.",
            "- `Utility` is the narrower operator-routing/JSON/summary lane. `Agentic` covers file truth, code edits, and gateway-style operator replies.",
            "- `Reliability` rewards fully stable tasks and penalizes flakiness, timeouts, runner errors, and tool failures.",
            "- `Validator` scores post-edit cleanliness from syntax/lint/formatter checks attached to patch-style tool outputs.",
            "- `Quality x` is pass-rate ratio versus the baseline, so it only exists when both models have Hermes task runs.",
            "- Split/offload candidates should clear about 30 tok/s and show a large quality gain before they are worth production complexity.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quality", nargs="+", type=Path, required=True, help="Hermes results_*.json files")
    parser.add_argument("--throughput", nargs="*", type=Path, default=[], help="Throughput JSON or summary TSV files")
    parser.add_argument("--baseline", default="qwen3.6-35b-a3b:iq4xs")
    parser.add_argument("--min-generation-tps", type=float, default=30.0)
    parser.add_argument("--quality-multiplier-target", type=float, default=2.0)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    text = render_scorecard(
        _load_quality(args.quality),
        _load_throughput(args.throughput),
        args.baseline,
        args.min_generation_tps,
        args.quality_multiplier_target,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
