import json


def test_scorecard_renders_rubric_axes(tmp_path):
    from scripts import model_benchmark_scorecard

    quality_path = tmp_path / "quality.json"
    throughput_path = tmp_path / "throughput.json"

    quality_payload = {
        "summary": {
            "baseline:model": {
                "tasks": 6,
                "passed": 5,
                "elapsed_seconds": 6.0,
                "tool_failures": 0,
                "tasks_by_name": {
                    "utility_route_message_json": {"runs": 1, "passed": 1},
                    "utility_approval_risk_json": {"runs": 1, "passed": 1},
                    "slm_mutation_guard_json": {"runs": 1, "passed": 1},
                    "utility_extract_actions_json": {"runs": 1, "passed": 1},
                    "read_config_answer": {"runs": 1, "passed": 0},
                    "logic_number": {"runs": 1, "passed": 1},
                },
            },
            "candidate:model": {
                "tasks": 6,
                "passed": 6,
                "elapsed_seconds": 7.5,
                "tool_failures": 0,
                "tasks_by_name": {
                    "utility_route_message_json": {"runs": 1, "passed": 1},
                    "utility_approval_risk_json": {"runs": 1, "passed": 1},
                    "slm_mutation_guard_json": {"runs": 1, "passed": 1},
                    "utility_extract_actions_json": {"runs": 1, "passed": 1},
                    "read_config_answer": {"runs": 1, "passed": 1},
                    "logic_number": {"runs": 1, "passed": 1},
                },
            },
        },
        "results": [
            {"model": "baseline:model", "task": "read_config_answer", "reasons": ["python validator assertion failed"]},
            {"model": "candidate:model", "task": "read_config_answer", "reasons": []},
        ],
    }
    throughput_payload = {
        "model": "candidate:model",
        "median_completion_tokens_per_second": 42.0,
    }

    quality_path.write_text(json.dumps(quality_payload), encoding="utf-8")
    throughput_path.write_text(json.dumps(throughput_payload), encoding="utf-8")

    rendered = model_benchmark_scorecard.render_scorecard(
        model_benchmark_scorecard._load_quality([quality_path]),
        model_benchmark_scorecard._load_throughput([throughput_path]),
        baseline="baseline:model",
        min_generation_tps=30.0,
        quality_multiplier_target=1.1,
    )

    assert "| Model | Pass | Safety | Utility | Agentic | Reliability | Validator | Gen tok/s | Quality x | Speed x | Gate |" in rendered
    assert "`candidate:model`" in rendered
    assert "quality candidate" in rendered or "2x-quality candidate" in rendered
    assert "reject approval/routing" not in rendered.split("`candidate:model`", 1)[1].splitlines()[0]
    assert "Reliability" in rendered
    assert "Validator" in rendered


def test_scorecard_uses_base_model_throughput_for_labeled_variant(tmp_path):
    from scripts import model_benchmark_scorecard

    quality_path = tmp_path / "quality.json"
    throughput_path = tmp_path / "throughput.json"

    quality_payload = {
        "summary": {
            "candidate:model [t=0,tp=1]": {
                "base_model": "candidate:model",
                "tasks": 2,
                "passed": 2,
                "elapsed_seconds": 3.0,
                "tool_failures": 0,
                "tasks_by_name": {
                    "utility_route_message_json": {"runs": 1, "passed": 1},
                    "utility_extract_actions_json": {"runs": 1, "passed": 1},
                },
            }
        },
        "results": [
            {
                "model": "candidate:model",
                "display_model": "candidate:model [t=0,tp=1]",
                "task": "utility_route_message_json",
                "reasons": [],
            }
        ],
    }
    throughput_payload = {
        "model": "candidate:model",
        "median_completion_tokens_per_second": 37.5,
    }

    quality_path.write_text(json.dumps(quality_payload), encoding="utf-8")
    throughput_path.write_text(json.dumps(throughput_payload), encoding="utf-8")

    rendered = model_benchmark_scorecard.render_scorecard(
        model_benchmark_scorecard._load_quality([quality_path]),
        model_benchmark_scorecard._load_throughput([throughput_path]),
        baseline="candidate:model [t=0,tp=1]",
        min_generation_tps=30.0,
        quality_multiplier_target=1.1,
    )

    row = next(
        line
        for line in rendered.splitlines()
        if line.startswith("| `candidate:model [t=0,tp=1]` |")
    )
    assert "37.5" in row


def test_scorecard_uses_base_model_throughput_for_decode_variants(tmp_path):
    from scripts import model_benchmark_scorecard

    quality_path = tmp_path / "quality.json"
    throughput_path = tmp_path / "throughput.json"

    quality_payload = {
        "summary": {
            "candidate:model [t=0.1,tp=0.95]": {
                "base_model": "candidate:model",
                "tasks": 3,
                "passed": 3,
                "elapsed_seconds": 3.0,
                "tool_failures": 0,
                "tasks_by_name": {
                    "utility_route_message_json": {"runs": 1, "passed": 1},
                    "utility_approval_risk_json": {"runs": 1, "passed": 1},
                    "slm_mutation_guard_json": {"runs": 1, "passed": 1},
                },
            },
            "baseline:model": {
                "tasks": 3,
                "passed": 2,
                "elapsed_seconds": 3.0,
                "tool_failures": 0,
                "tasks_by_name": {
                    "utility_route_message_json": {"runs": 1, "passed": 1},
                    "utility_approval_risk_json": {"runs": 1, "passed": 1},
                    "slm_mutation_guard_json": {"runs": 1, "passed": 0},
                },
            },
        },
        "results": [
            {"model": "candidate:model", "display_model": "candidate:model [t=0.1,tp=0.95]", "task": "utility_route_message_json", "reasons": []},
            {"model": "baseline:model", "task": "slm_mutation_guard_json", "reasons": ["python validator assertion failed"]},
        ],
    }
    throughput_payload = {
        "model": "candidate:model",
        "median_completion_tokens_per_second": 42.0,
    }

    quality_path.write_text(json.dumps(quality_payload), encoding="utf-8")
    throughput_path.write_text(json.dumps(throughput_payload), encoding="utf-8")

    rendered = model_benchmark_scorecard.render_scorecard(
        model_benchmark_scorecard._load_quality([quality_path]),
        model_benchmark_scorecard._load_throughput([throughput_path]),
        baseline="baseline:model",
        min_generation_tps=30.0,
        quality_multiplier_target=1.1,
    )

    row = next(line for line in rendered.splitlines() if "`candidate:model [t=0.1,tp=0.95]`" in line)
    assert "42.00" in row


def test_scorecard_includes_validator_cleanliness_from_summary(tmp_path):
    from scripts import model_benchmark_scorecard

    quality_path = tmp_path / "quality.json"
    throughput_path = tmp_path / "throughput.json"

    quality_payload = {
        "summary": {
            "baseline:model": {
                "tasks": 2,
                "passed": 2,
                "elapsed_seconds": 2.0,
                "tool_failures": 0,
                "validated_files": 2,
                "validation_failure_count": 0,
                "formatter_failure_count": 0,
                "lint_failure_count": 0,
                "validation_failure_runs": 0,
                "formatter_failure_runs": 0,
                "lint_failure_runs": 0,
                "tasks_by_name": {
                    "utility_route_message_json": {"runs": 1, "passed": 1},
                    "patch_python_bug": {"runs": 1, "passed": 1},
                },
            },
            "candidate:model": {
                "tasks": 2,
                "passed": 2,
                "elapsed_seconds": 2.0,
                "tool_failures": 0,
                "validated_files": 2,
                "validation_failure_count": 1,
                "formatter_failure_count": 1,
                "lint_failure_count": 0,
                "validation_failure_runs": 1,
                "formatter_failure_runs": 1,
                "lint_failure_runs": 0,
                "tasks_by_name": {
                    "utility_route_message_json": {"runs": 1, "passed": 1},
                    "patch_python_bug": {"runs": 1, "passed": 1},
                },
            },
        },
        "results": [],
    }
    throughput_payload = {
        "model": "candidate:model",
        "median_completion_tokens_per_second": 31.0,
    }

    quality_path.write_text(json.dumps(quality_payload), encoding="utf-8")
    throughput_path.write_text(json.dumps(throughput_payload), encoding="utf-8")

    rendered = model_benchmark_scorecard.render_scorecard(
        model_benchmark_scorecard._load_quality([quality_path]),
        model_benchmark_scorecard._load_throughput([throughput_path]),
        baseline="baseline:model",
        min_generation_tps=30.0,
        quality_multiplier_target=1.0,
    )

    row = next(line for line in rendered.splitlines() if line.startswith("| `candidate:model` |"))
    assert "| 0.25 | 31.00 |" in row
