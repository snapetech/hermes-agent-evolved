# Workflow Map

Use this file with `hermes-local-llm-nightly`.

## Purpose

The nightly local-LLM cycle should continuously answer:

1. Did any already-retained local model family get a better release, quant,
   variant, or runtime path?
2. Are there new local candidates worth testing that were not in the last pass?
3. Which new downloads deserve retention, and which should be deleted after
   documentation?

## Current Repo Sources

Start from these local references:

- `docs/research-update-cycles.md`
- `benchmarks/llm/local_llm_benchmark_report_20260421.md`
- `benchmarks/llm/model_benchmark_scorecard.md`
- `benchmarks/llm/nous_edge_watch_local_results_20260422.md`
- `benchmarks/llm/split_card_test_plan_20260422.md`
- `benchmarks/llm/qwen36_27b_tuning_research_20260423.md`
- `benchmarks/llm/slm_candidates.tsv`
- `benchmarks/llm/model_capability_cards.md`
- `benchmarks/llm/model_capability_cards.generated.md`

Check installed weights:

```bash
find /opt/models/hermes-bench -maxdepth 1 -type f -name '*.gguf' -printf '%f\n' | sort
```

## Report Convention

Every nightly run should leave a predictable report artifact under:

- `$HERMES_HOME/self-improvement/local-llm-nightly/reports/YYYY-MM-DD.md`
- `$HERMES_HOME/self-improvement/local-llm-nightly/reports/latest.md`
- `$HERMES_HOME/self-improvement/local-llm-nightly/state.json`

Use the dated file for the immutable nightly record and refresh `latest.md`
after each pass. Use `state.json` as the in-progress ledger and recovery
checkpoint.

Minimum report sections:

- `Retained`
- `Rejected`
- `Deleted downloads`
- `Needs follow-up`
- `Next-best downloads`

Rejected candidates should include enough detail to avoid blind re-downloads in
the next cycle.

## Resume Protocol

Start each nightly run with:

```bash
python scripts/local_llm_nightly_state.py reconcile
python scripts/local_llm_nightly_state.py begin --phase startup
```

During the run, checkpoint phase progress and candidate decisions:

```bash
python scripts/local_llm_nightly_state.py checkpoint --phase research --note "candidate triage complete"
python scripts/local_llm_nightly_state.py candidate --name model.gguf --status downloaded --local-path /opt/models/hermes-bench/model.gguf
python scripts/local_llm_nightly_state.py checkpoint --phase cleanup --note "deleted rejected leftovers"
```

Finalize after the report is written:

```bash
python scripts/local_llm_nightly_state.py finalize --status completed --report-path "$HERMES_HOME/self-improvement/local-llm-nightly/reports/$(date +%F).md"
```

If `reconcile` reports:

- `stale_running_state`: continue the interrupted run instead of pretending it
  never happened
- `leftover_rejected_download`: delete the file after confirming the rejection
  note still stands
- `missing_candidate_file`: mark the candidate as interrupted or abandoned in
  the report instead of reusing stale assumptions
- missing report files: regenerate or refresh the nightly report pointers before
  moving on

## Existing Scripts

Use these before inventing new commands:

- `benchmarks/llm/qwen36_knob_bench.sh`
- `benchmarks/llm/run_slm_utility_bench.sh`
- `scripts/llama_throughput_compare.py`
- `scripts/hermes_model_benchmark.py`
- `scripts/model_benchmark_scorecard.py`
- `deploy/k8s/hermes-llama-qwen36-service.sh`

Useful related skill:

- `skills/mlops/evaluation/hermes-model-benchmark/SKILL.md`
- `skills/mlops/inference/llama-cpp/SKILL.md`

## Nightly Sequence

### 1. Research retained families

For each retained family or currently prioritized family:

- check official upstream repo/model cards
- check the most trusted GGUF distribution pages
- check whether llama.cpp/runtime guidance changed
- note any new recommended quant, bug fix, or runtime warning

Examples:

- current Qwen/Qwen3.6 lanes
- GLM validator lane
- Kimi/Moonshot candidates
- Gemma/Mistral/Seed/Nemotron or other retained watchlist families

### 2. Research genuinely new candidates

Look for:

- new upstream open-weight model families
- renamed or newly published model lines
- new GGUF releases for previously inaccessible families
- runtime changes that make an old non-viable candidate newly viable
- new inference techniques that matter on this hardware

Prefer primary sources first:

- upstream model repos/cards
- official vendor docs
- llama.cpp docs/issues/PRs

Use community sources only as secondary evidence for what is getting real usage.

### 3. Candidate preflight

Before downloading, answer:

- does it fit the machine or known split budget?
- does it target an actual Hermes lane?
- is there a plausible win over a retained candidate?
- is there a clear first quant to test?

Reject early if the answer is no.

### 4. Download bounded candidates

Prefer:

- one first-pass speed quant
- one first quality-control quant

Do not bulk-download an entire family without a reason.

### 5. Benchmark in stages

1. Direct throughput / tuning probe
2. Served-path throughput
3. Hermes task quality
4. Repetition for finalists

For dense model families, start with:

- `flash-attn`
- KV cache type
- `batch`
- `ubatch`

For MoE families, include fit/offload questions only when relevant.

### 6. Decide retain vs reject

Retention requires a durable reason:

- better default
- better narrow lane
- fills a missing lane

Rejection requires documentation before deletion:

- what was tested
- what failed or regressed
- why it is not worth keeping
- whether a later retry is justified

### 7. Clean up

Delete rejected downloads after the rejection note is written.

If the run was interrupted mid-cleanup, use the state file to finish deleting
rejected leftovers before starting fresh downloads.

Keep the matrix current:

- add retained candidates to the scorecard/plan/docs
- add rejects to the notes with enough evidence to avoid re-testing blindly

## Suggested Output Pattern

A nightly pass should leave a short written result with:

- `Retained`
- `Rejected`
- `Needs follow-up`
- `Next-best downloads`

For rejected candidates, include a one-line deletion note such as:

`Deleted <model-file> after <benchmarks>; slower than <retained candidate> and failed <critical task>.`

## Hard Guardrails

- do not switch the live primary model without explicit approval
- do not restart the live primary service for speculative testing
- do not keep large failed downloads around without a written reason
- do not call a candidate "better" from throughput alone
- do not add a new retained lane without naming the Hermes use-case it serves
