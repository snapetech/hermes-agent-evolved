from types import SimpleNamespace


def test_task_matrix_expands_to_27_tasks_with_expected_category_counts():
    from scripts import hermes_model_benchmark

    counts: dict[str, int] = {}
    for task in hermes_model_benchmark.TASKS:
        counts[task.category] = counts.get(task.category, 0) + 1

    assert len(hermes_model_benchmark.TASKS) == 27
    assert counts == {
        "logic": 3,
        "utility": 8,
        "slm": 4,
        "slm-localized": 2,
        "agentic": 5,
        "gateway": 2,
        "coding": 3,
    }


def test_summarize_preserves_display_variant_and_base_model():
    from scripts import hermes_model_benchmark

    results = [
        {
            "task": "utility_route_message_json",
            "category": "utility",
            "model": "candidate:model",
            "display_model": "candidate:model [t=0.1,tp=0.95]",
            "passed": True,
            "elapsed_seconds": 1.2,
            "api_calls": 1,
            "tool_calls": 0,
            "tool_failures": 0,
            "validated_files": 0,
            "validation_failure_count": 0,
            "formatter_failure_count": 0,
            "lint_failure_count": 0,
            "validation_failure_runs": 0,
            "formatter_failure_runs": 0,
            "lint_failure_runs": 0,
            "reasons": [],
        },
        {
            "task": "read_config_answer",
            "category": "agentic",
            "model": "candidate:model",
            "display_model": "candidate:model [t=0.1,tp=0.95]",
            "passed": False,
            "elapsed_seconds": 2.0,
            "api_calls": 2,
            "tool_calls": 1,
            "tool_failures": 1,
            "validated_files": 1,
            "validation_failure_count": 1,
            "formatter_failure_count": 1,
            "lint_failure_count": 0,
            "validation_failure_runs": 1,
            "formatter_failure_runs": 1,
            "lint_failure_runs": 0,
            "reasons": ["python validator assertion failed"],
        },
    ]

    summary = hermes_model_benchmark._summarize(results)

    assert set(summary) == {"candidate:model [t=0.1,tp=0.95]"}
    row = summary["candidate:model [t=0.1,tp=0.95]"]
    assert row["base_model"] == "candidate:model"
    assert row["tasks"] == 2
    assert row["passed"] == 1
    assert row["tool_failures"] == 1
    assert row["rubric"]["quality"]["pass_rate"] == 0.5
    assert row["rubric"]["validator"]["validated_files"] == 1
    assert row["rubric"]["validator"]["validation_failure_count"] == 1
    assert row["rubric"]["validator"]["formatter_failure_count"] == 1


def test_count_tool_usage_extracts_validation_failures():
    from scripts import hermes_model_benchmark

    messages = [
        {"role": "assistant", "tool_calls": [{"name": "patch_tool"}]},
        {
            "role": "tool",
            "content": '{"success": true, "validation": {"status": "error", "lint": {"status": "ok"}, "formatter": {"status": "error"}}}',
        },
        {
            "role": "tool",
            "content": '{"success": true, "validation": {"a.py": {"status": "ok", "lint": {"status": "error"}, "formatter": {"status": "ok"}}}}',
        },
    ]

    counts = hermes_model_benchmark._count_tool_usage(messages)

    assert counts["tool_calls"] == 1
    assert counts["validated_files"] == 2
    assert counts["validation_failure_count"] == 1
    assert counts["formatter_failure_count"] == 1
    assert counts["lint_failure_count"] == 1
    assert counts["validation_failure_runs"] == 1


def test_build_request_overrides_includes_llama_and_openai_sampler_fields():
    from scripts import hermes_model_benchmark

    namespace = SimpleNamespace(
        temperature=0.2,
        top_p=0.9,
        top_k=40,
        min_p=0.05,
        typical_p=0.8,
        repeat_penalty=1.05,
        presence_penalty=0.1,
        frequency_penalty=0.2,
        seed=7,
        mirostat=2,
        mirostat_tau=5.0,
        mirostat_eta=0.1,
    )

    overrides = hermes_model_benchmark._build_request_overrides(namespace)

    assert overrides["temperature"] == 0.2
    assert overrides["top_p"] == 0.9
    assert overrides["presence_penalty"] == 0.1
    assert overrides["frequency_penalty"] == 0.2
    assert overrides["seed"] == 7
    assert overrides["extra_body"] == {
        "top_k": 40,
        "min_p": 0.05,
        "typical_p": 0.8,
        "repeat_penalty": 1.05,
        "mirostat": 2,
        "mirostat_tau": 5.0,
        "mirostat_eta": 0.1,
    }
