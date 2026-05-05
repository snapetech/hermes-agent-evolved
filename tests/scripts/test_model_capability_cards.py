import json


def test_capability_cards_cover_all_benchmark_tasks():
    from scripts import hermes_model_benchmark, model_capability_cards

    benchmark_tasks = {task.name for task in hermes_model_benchmark.TASKS}

    assert benchmark_tasks <= set(model_capability_cards.TASK_LABELS)
    assert model_capability_cards.CRITICAL_TASKS <= benchmark_tasks


def test_capability_cards_render_strengths_and_exclusions(tmp_path):
    from scripts import model_capability_cards

    result_path = tmp_path / "results.json"
    rows = [
        {
            "task": "utility_extract_actions_json",
            "category": "utility",
            "model": "tiny:test",
            "passed": True,
            "response": '{"incident":"x","action":"restart","evidence":"healthy"}',
            "elapsed_seconds": 0.2,
        },
        {
            "task": "utility_route_message_json",
            "category": "utility",
            "model": "tiny:test",
            "passed": False,
            "response": '{"lane":"ops","urgency":"normal","needs_approval":false}',
            "elapsed_seconds": 0.1,
        },
    ]
    result_path.write_text(json.dumps({"results": rows}), encoding="utf-8")

    rendered = model_capability_cards.render_markdown([result_path])

    assert "## `tiny:test`" in rendered
    assert "operator-note extraction | 1/1" in rendered
    assert "Good for: operator-note extraction." in rendered
    assert "ops routing with approval flag | 0/1" in rendered
    assert "exclude from approval/routing" in rendered
    assert "Do not use for: ops routing with approval flag." in rendered
    assert "needs_approval" in rendered
