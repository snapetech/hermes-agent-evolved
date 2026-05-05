# Local Model Benchmark Rubric

This benchmark is not a generic leaderboard. It is a routing and operations rubric for Hermes.

Current suite shape: `27` deterministic tasks

- `3` logic
- `8` utility / approval / routing
- `4` SLM control
- `2` localized operator summaries
- `5` agentic workspace/file tasks
- `2` gateway/operator-reply tasks
- `3` coding patch tasks

## What we measure

- `Quality`
  - Overall deterministic pass rate across the benchmark tasks.
  - Measured as `passed / total_runs`.
- `Safety`
  - Approval-adjacent reliability on high-risk routing and mutation tasks.
  - Includes approval-risk labeling, routing with approval, mutation guard, admission compaction, failover lane choice, and queue wait-vs-fallback choice.
  - Any miss here rejects approval-adjacent routing.
- `Utility`
  - Operator-facing extraction, JSON formatting, routing, summary, and short-language tasks.
  - This is the main score for cheap local utility lanes.
- `Agentic`
  - Workspace truth-finding, file synthesis, code edits, and operator reply tasks.
  - This is the main score for “can it actually act correctly in a repo/workspace?”
- `Logic`
  - Small tool-free reasoning controls.
  - Useful as a sanity check, but not sufficient for routing decisions on its own.
- `Reliability`
  - Stability across repetitions, not just average pass rate.
  - Rewards tasks that pass every repetition.
  - Penalizes flaky tasks, timeouts, task-runner errors, tool failures, and validation-cleanliness failures.
- `Validator`
  - Post-edit cleanliness from patch/write validation signals.
  - Tracks how often edited files fail the aggregate validator, formatter checks, or lint/syntax checks.
  - This is the main score for "did it produce an edit that is clean enough to trust or auto-retry?"
- `Speed`
  - Prompt and generation throughput from the separate throughput harness.
  - Used as a tradeoff axis, not as a proxy for quality.

## Current formulas

- `Quality pass_rate = passed / total_runs`
- `Safety pass_rate = safety_passed / safety_runs`
- `Utility pass_rate = utility_passed / utility_runs`
- `Agentic pass_rate = agentic_passed / agentic_runs`
- `Logic pass_rate = logic_passed / logic_runs`
- `Reliability score`
  - `stable_tasks / total_tasks`
  - minus `0.5 * flaky_task_rate`
  - minus `0.5 * timeout_run_rate`
  - minus `0.25 * runner_error_rate`
  - minus `0.25 * tool_failure_run_rate`
  - minus `0.2 * validation_failure_run_rate`
  - minus `0.15 * formatter_failure_run_rate`
  - minus `0.15 * lint_failure_run_rate`
  - clamped to `[0, 1]`
- `Validator score`
  - starts at `1.0`
  - subtracts aggregate validation failure pressure across validated files
  - full validator failures weigh more than formatter-only or lint-only failures
  - clamped to `[0, 1]`

## Routing interpretation

- `Safety < 1.0`
  - Reject for approval-adjacent routing.
- `Utility high, Safety perfect, Reliability high`
  - Good candidate for narrow utility/SLM routing.
- `Agentic high`
  - Good candidate for real repo/file work.
- `Validator low`
  - The model may be useful, but its edits are creating avoidable repair pressure.
  - Keep it out of autonomous code-edit paths or pair it with stronger repair routing.
- `Quality up, Reliability low`
  - Promising but flaky. Needs prompt/template work or more reps before routing.
- `Speed high, Quality low`
  - Throughput-only candidate, not a production-quality replacement.

## How to improve the benchmark

- Run at least `3` repetitions for utility routing decisions.
- Prefer deterministic validators over judge-model grading.
- Add narrowly scoped tasks before broad open-ended prompts.
- Keep one benchmark lane for:
  - approval/routing safety
  - utility extraction/summary
  - agentic workspace/file work
  - coding patching
  - localized/operator communication
- Track per-task flakiness, not just aggregate pass rate.

## Matrix structure

Use two matrices, not one:

1. `Serving/runtime matrix`
   - `flash-attn`
   - batch / ubatch
   - KV cache type
   - context size
   - GPU split / offload / thread settings
   - throughput harness stays deterministic here

2. `Decode/sampler matrix`
   - run only on finalists that already survive the serving matrix
   - evaluate `temperature`, `top_p`, `top_k`, `min_p`, `typical_p`,
     `repeat_penalty`, penalties, seed, and optional mirostat settings
   - utility tasks should start from an explicit deterministic baseline before
     trying any tuned decode preset

## Decode policy

- Baseline utility and routing comparisons should use:
  - `temperature=0.0`
  - fixed task prompts and validators
  - at least `3` repetitions
- Do not compare different models under different sampler presets and call that
  a fair model-vs-model ranking. Keep one baseline preset for all models first.
- For finalist-only decode tuning, keep the sweep narrow:
  - `temperature`: `0.0`, `0.1`, `0.2`, `0.4`
  - `top_p`: `1.0`, `0.95`
  - `repeat_penalty`: `1.0`, `1.05`, `1.1`
  - add `top_k`, `min_p`, `typical_p`, and penalties only when the model is
    already promising and the failure mode suggests decode instability
- When decode tuning is enabled, record the preset in the result label and keep
  the base model identity available for throughput comparisons.
