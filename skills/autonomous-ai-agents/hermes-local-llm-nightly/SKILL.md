---
name: hermes-local-llm-nightly
description: Run the nightly Hermes local-LLM review cycle: research new versions and variants of current local llama.cpp/GGUF models, discover new replacement candidates worth testing, benchmark viable newcomers, retain only models that improve the matrix without regressions, and document then delete failed candidates.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, nightly, local-models, llama.cpp, gguf, benchmarking, research, self-improvement]
    category: autonomy
    related_skills: [putter, hermes-model-benchmark, llama-cpp, blogwatcher, llm-wiki]
---

# Hermes Local LLM Nightly

Use this skill when Hermes needs to run the recurring local-model review loop
for the Snapetech deployment.

This is the canonical workflow for:

- checking whether current retained local model families have new variants,
  better quants, bug-fixed runtimes, or stronger upstream recommendations
- finding genuinely new local model candidates that did not exist in the
  previous review cycle
- benchmarking, comparing, retaining, or deleting downloaded candidate models
  with durable documentation

Read [references/workflow-map.md](references/workflow-map.md) before acting.

## Contract

Treat this as a research-and-benchmark cycle, not permission to silently change
production.

Allowed by default:

- browse and research current model/runtime facts
- update benchmark plans, comparison docs, and result summaries
- download candidate GGUFs when they fit the documented machine budget and the
  candidate is worth real testing
- run local benchmark scripts and quality suites
- delete rejected downloaded candidates after writing down exactly what was
  tested and why they were rejected
- patch skills/docs/scripts/tests that make this nightly cycle more reliable

Do not by default:

- replace the live primary model
- switch production routing or fallback providers
- restart the live primary service
- merge PRs, deploy, or mutate cluster resources
- keep unpromising model files around "just in case" after a completed review
  unless they fill a clearly documented niche

## Nightly Goal

Each nightly pass should leave durable evidence for all three lanes:

1. **Current-family upgrades**
   - new versions, quants, runtime fixes, or stronger configs for already
     retained model families
2. **New replacement candidates**
   - new models, renamed releases, new families, new inference/runtime options,
     or other "new hotness" worth evaluating
3. **Retention decisions**
   - kept and added to the matrix, or rejected and deleted with written reasons

If nothing worth testing exists, say so and record that conclusion briefly.

## Workflow

1. Start from the latest local matrix and research notes.
2. Research current-family upgrades from primary sources first.
3. Research new candidates from primary sources first, community sources second.
4. Triage candidates before download:
   - reject obvious non-fits early
   - keep the download set bounded
5. Download only candidates that pass the preflight bar.
6. Run direct throughput/tuning probes first.
7. Run served-path throughput and Hermes quality checks for finalists.
8. Decide retain vs reject using the retention rules below.
9. For rejects, document what was tested, why it failed, and delete the local
   download.
10. Update the benchmark matrix and next-step plan so the following nightly pass
    starts from current truth.

## Retention Rules

A candidate is worth retaining only if at least one of these is true:

- it is the new best overall option for an existing Hermes lane
- it cleanly replaces an older retained candidate with no meaningful regression
- it opens a new lane that the current retained set does not cover
  (for example, a better validator, coding lane, split-only lane, or vision lane)

Do not retain a candidate that is merely interesting.

For promotion to a serious retained candidate, require:

- no regression on critical Hermes tasks for the intended lane
- throughput and latency that are operationally acceptable on this hardware
- documented fit/runtime behavior
- a clear reason to keep the weights on disk

For replacing an existing default, require a stricter bar:

- improves quality or reliability
- does not regress the required tasks
- does not create a worse fit/VRAM/runtime story
- is backed by repeatable measurements, not a single lucky run

## Rejection Rules

Reject and delete a downloaded candidate after documenting it when any of these
is true:

- it fails critical Hermes tasks for the lane it was meant to fill
- it is slower and no better than an already retained candidate
- it needs awkward runtime handling with no compensating quality gain
- it duplicates an existing retained lane without clearly improving it
- it only looks good on synthetic throughput and is not useful in Hermes tasks
- it is too large, unstable, or operationally messy to justify retention

Before deleting a rejected candidate, write down:

- exact model/quant/runtime tested
- benchmark commands or scripts used
- measured result summary
- rejection reason
- whether there is any follow-up worth retrying later

## Scope Rules For Downloads

Prefer one or two best-first quants per family, not broad hoarding.

Default order:

- first speed probe
- first quality-control quant
- only then stretch quants if the family still looks promising

Delete dead-end downloads after the decision is written down. Do not let
`/opt/models/hermes-bench` become a graveyard of unscored experiments.

## Validation

Use the smallest valid sequence:

- direct `llama-bench` or knob sweep first
- served-path throughput next
- Hermes quality suite for finalists
- repeat top candidates before any recommendation to change defaults

Prefer existing scripts and reports over ad hoc command invention. The reference
file lists the current canonical paths and outputs.

## Outputs

A good nightly pass updates one or more of:

- benchmark notes under `benchmarks/llm/`
- retained-vs-rejected rationale in the current matrix docs
- next-step candidate plan
- a skill/doc/script patch that improves future nightly passes

For scheduled/nightly runs, also write a deterministic artifact under
`$HERMES_HOME/self-improvement/local-llm-nightly/reports/`:

- dated report: `YYYY-MM-DD.md`
- rolling pointer copy: `latest.md`
- durable state ledger: `$HERMES_HOME/self-improvement/local-llm-nightly/state.json`

The report should include flat sections for:

- `Retained`
- `Rejected`
- `Deleted downloads`
- `Needs follow-up`
- `Next-best downloads`

If nothing changed, still update the dated report and `latest.md` with a short
`no actionable changes` result.

## Resilience And Resume

Nightly runs must be restart-safe. Before doing research or downloads:

1. Reconcile the previous state:
   - `python scripts/local_llm_nightly_state.py reconcile`
2. Start or resume the current run:
   - `python scripts/local_llm_nightly_state.py begin --phase startup`

Use the state file as the canonical in-progress ledger for:

- current phase
- current candidate under test
- candidate-level status such as `queued`, `downloaded`, `benchmarked`,
  `retained`, `rejected`, or `deleted`
- interrupted/stale previous-run recovery context

Update it during the pass:

- after research triage
- after each download decision
- after each benchmark stage
- after each retain/reject decision
- after cleanup

Example heartbeat:

```bash
python scripts/local_llm_nightly_state.py checkpoint \
  --phase benchmark \
  --candidate Qwen_Qwen3.6-27B-Q4_K_M.gguf \
  --note "served-path throughput probe started"
```

Example candidate decision:

```bash
python scripts/local_llm_nightly_state.py candidate \
  --name Qwen_Qwen3.6-27B-Q4_K_M.gguf \
  --status rejected \
  --local-path /opt/models/hermes-bench/Qwen_Qwen3.6-27B-Q4_K_M.gguf \
  --note "slower than retained lane and failed utility threshold"
```

At the end of the pass, finalize the run:

```bash
python scripts/local_llm_nightly_state.py finalize \
  --status completed \
  --report-path "$HERMES_HOME/self-improvement/local-llm-nightly/reports/$(date +%F).md"
```

If `reconcile` reports stale or inconsistent state, repair that first. The next
nightly pass should prefer finishing or cleaning partial work over blindly
restarting the same candidate downloads and probes.

## Self-Fixing Expectations

When the nightly run fails because of bounded local friction, fix the path if it
is safe and auditable. Examples:

- create missing report/state directories
- resume a partially documented candidate instead of re-downloading it
- delete a rejected leftover download that state already marks as rejected
- patch a small script/doc/test issue that prevents the nightly loop from
  running correctly

Do not do dangerous "self-fixing" under this skill:

- no silent production routing changes
- no live service restarts
- no speculative dependency churn unrelated to the nightly loop
- no keeping broken partial downloads without documenting why

## Approval Handoff

If a nightly pass finds a validated promotion or remediation that should change
live Hermes behavior after human review, do not apply it directly here.

Instead, hand off through `hermes-local-llm-promotion-handoff`:

- create a deterministic packet
- open or update a draft PR on a dedicated branch
- send the reasoning summary to `keith@snape.tech`

Use that handoff only for genuinely approval-worthy candidates. Routine
rejections and housekeeping stay inside this nightly skill.

If the pass changes repo files, validate the narrowest relevant test or script.
