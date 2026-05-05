# Model Capability Cards

Use this file to keep track of what imperfect local models are actually useful
for. A model can be a bad primary agent and still be worth routing narrow,
low-risk side work to.

Regenerate candidate sections from benchmark JSON with:

```bash
python scripts/model_capability_cards.py \
  benchmark_runs/hermes_model_benchmark_slm_utility/results_20260421_095509.json \
  benchmark_runs/hermes_model_benchmark_slm_utility/results_20260421_095555.json \
  --output benchmarks/llm/model_capability_cards.generated.md
```

## Routing Policy

- A model that fails `utility_approval_risk_json`,
  `utility_route_message_json`, or `slm_mutation_guard_json` is not eligible
  for approval-adjacent routing.
- A model can still be eligible for extraction, condensation, language-specific
  summaries, or cheap labels if it passes that exact task family repeatedly.
- Promote a niche only after at least three repetitions and a same-task
  comparison against the current primary baseline.
- Keep deterministic safety rules above model outputs for restarts, deploys,
  sudo, kubectl mutation, credential changes, and destructive filesystem work.

## `lfm25-12b-instruct:q4km`

- File: `/opt/models/hermes-bench/LFM2.5-1.2B-Instruct-Q4_K_M.gguf`
- Size: 698 MB on disk.
- Hardware tested: RX 9070 XT, full offload, `CTX_SIZE=8192`, q4 KV.
- Throughput: median 234.18 completion tok/s, 0.34s wall on the fixed
  throughput prompt.
- Utility+SLM result: 8/24, avg 0.26s/task.

Good for:

- `utility_extract_actions_json`: 3/3. Good at summarizing operator incident
  notes into compact incident/action/evidence fields.
- `utility_pulse_condense`: 3/3 after the validator was corrected. Good for
  short, low-risk pulse/status condensation.

Unstable:

- `utility_approval_risk_json`: 1/3. It often set `requires_approval` true but
  mislabeled restart risk as `low`, so the boolean is useful only with
  deterministic post-rules.
- `slm_extract_service_command_json`: 1/3. It usually found the service/action
  but sometimes returned YAML-ish text instead of JSON or omitted the service
  suffix.

Do not use for:

- `utility_route_message_json`: 0/3. It repeatedly marked conditional restart
  requests as not needing approval.
- `slm_intent_route_json`: 0/3. It over-requested review for harmless inspect
  requests or misrouted the intent.
- `slm_mutation_guard_json`: 0/3. It classified restart actions as inspect or
  notify instead of mutate.
- `slm_portuguese_status_summary`: 0/3. It produced plausible Portuguese but
  missed required status/service details under the current validator.

Current verdict:

Keep as a fast extraction/condensation candidate only. Reject for approval,
mutation, autonomous routing, or language-specific traffic until a future
prompt/template or model variant beats the baseline on those exact tasks.

## `qwen3.6-35b-a3b:iq4xs`

- Role: live primary baseline.
- Hardware tested: RX 7900 XT live service.
- Throughput: median 73.30 completion tok/s, 2.28s wall on the fixed
  throughput prompt.
- Utility+SLM result: 18/24, avg 0.88s/task.

Good for:

- `utility_approval_risk_json`: 3/3.
- `slm_intent_route_json`: 3/3.
- `slm_mutation_guard_json`: 3/3.
- `slm_extract_service_command_json`: 3/3.

Unstable:

- `utility_route_message_json`: 1/3 in the latest run.
- `utility_extract_actions_json`: 2/3 in the latest run.
- `utility_pulse_condense`: 2/3 after validator correction.
- `slm_portuguese_status_summary`: 1/3.

Current verdict:

Keep as the quality baseline for SLM comparisons. It is slower than the tiny
SLM but far more reliable on approval and mutation guard tasks.
