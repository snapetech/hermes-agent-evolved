# Workflow Map

Use this file with `hermes-local-llm-promotion-handoff`.

## Inputs

Primary evidence should come from:

- `$HERMES_HOME/self-improvement/local-llm-nightly/reports/latest.md`
- `$HERMES_HOME/self-improvement/local-llm-nightly/state.json`
- current benchmark docs under `benchmarks/llm/`
- current deploy/runbook docs if the proposal changes live serving

## Packet Convention

Write a deterministic packet under:

- `$HERMES_HOME/self-improvement/local-llm-nightly/handoffs/YYYY-MM-DD-<slug>/packet.json`
- `$HERMES_HOME/self-improvement/local-llm-nightly/handoffs/YYYY-MM-DD-<slug>/pr_body.md`
- `$HERMES_HOME/self-improvement/local-llm-nightly/handoffs/YYYY-MM-DD-<slug>/email.txt`

Use:

```bash
python scripts/local_llm_handoff_packet.py \
  --kind promotion \
  --title "promote qwen3.6-27b q5_k_s" \
  --summary "replaces current lane with better utility and acceptable throughput" \
  --reasoning "repeat benches and utility checks beat the retained baseline without new regressions" \
  --report-path "$HERMES_HOME/self-improvement/local-llm-nightly/reports/latest.md" \
  --evidence "benchmarks/llm/model_benchmark_scorecard.md"
```

## GitHub Flow

Prefer `gh` when authenticated:

```bash
git checkout -b llm-handoff/YYYY-MM-DD-slug
git add <docs/config/packet files>
git commit -m "docs: propose local LLM promotion handoff"
git push -u origin HEAD
gh pr create --draft --base main --title "<packet pr title>" --body-file <packet pr_body.md>
```

If a PR for the branch already exists, update it instead of opening a second one.

## Email Flow

Preferred:

- cron auto-delivery with `deliver: local,email:keith@snape.tech`

Fallback:

- use the rendered `email.txt` packet artifact as the source of truth
- if SMTP is configured, send the same content directly

## Decision Rule

Open a PR and send email only if:

- the proposal is evidence-backed
- the candidate materially improves a lane or fixes a real regression
- human approval is genuinely required before rollout

Otherwise:

- update the nightly report/state
- return `[SILENT]`
