---
name: hermes-introspection
description: Review Hermes Agent's own behavior from sessions, memories, skills, tool errors, and trajectories; turn recurring internal friction into skill/config/code/test improvement proposals. Load this when asked what is working well or badly inside Hermes, whether self-improvement is accounted for, or when running an introspective improvement cycle.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, introspection, self-improvement, retrospective, evals, skills, memory]
    related_skills: [hermes-agent]
---

# Hermes Introspection

Use this skill for internal Hermes improvement work: reviewing how Hermes itself behaved, identifying recurring friction, and converting evidence into scoped improvements.

## Operating Rule

Treat introspection as an evidence-gathering and validation loop, not as permission to self-modify production. Reports may recommend skill patches, config changes, tests, or code changes. Do not push branches, open PRs, merge, deploy, or mutate live services unless the user explicitly asks.

## Evidence Sources

Prefer bounded local evidence:

- Current temporal context injected with the skill invocation. Use it as the
  anchor for freshness, "recent", "latest", and overdue schedule reasoning.
- Maintenance freshness ledger via `maintenance_freshness`, when available.
  Start with `maintenance_freshness(action="seed")`, then
  `maintenance_freshness(action="due", limit=20)` to see stale self-review,
  edge-watch, runtime install, upstream sync, docs, tool, model, and cron work.
- Session SQLite store: `$HERMES_HOME/state.db`
- Memory files: `$HERMES_HOME/memories/MEMORY.md` and `USER.md`
- User and bundled skills: `$HERMES_HOME/skills` and repo `skills/`
- Trajectories: `trajectory_samples.jsonl` and `failed_trajectories.jsonl`
- Cron reports: `$HERMES_HOME/self-improvement/introspection/reports/`
- Existing external scan reports: `$HERMES_HOME/self-improvement/reports/` or `$HERMES_HOME/cron/output/edge-watch/`
- K3s resource review reports: `$HERMES_HOME/self-improvement/resource-review/reports/`

Run the collector when available:

```bash
python3 deploy/k8s/hermes-introspection-scan.py --window-days 7 --session-limit 80
```

For deployment resource review, run the advisory helper when available:

```bash
python3 deploy/k8s/hermes-resource-review.py --local-only
```

Inside the Kubernetes deployment:

```bash
/opt/data/scripts/hermes_resource_review.py --write-report
```

In the Kubernetes deployment, the installed path is:

```bash
/opt/data/scripts/hermes_introspection_scan.py --window-days 7 --session-limit 80
```

## Review Rubric

Separate findings into these buckets:

- Working well: successful tool sessions, useful memory writes, skill updates, clean session recovery, effective session search.
- Repeated friction: recurring tool errors, timeouts, missing credentials, wrong path/repo mistakes, failed tests, schema/config failures.
- User steering: repeated corrections or preferences that should become memory or a skill update.
- Memory quality: durable facts vs task progress, excessive entry length, noisy or stale entries.
- Skill quality: stale instructions, missing troubleshooting steps, overly large skills that should use references, skills that should have been patched.
- Evaluation gaps: repeated bugs without regression tests, missing replay/eval cases, failed trajectories that should become fixtures.
- K3s resource fit: gateway/proxy/CronJob requests or limits that look too low,
  too high, or unsupported by current usage evidence.

## Improvement Ladder

Choose the least invasive fix that addresses the evidence:

1. Memory update for stable user preference or environment fact.
2. Skill patch for reusable workflow, repeated correction, or tool/process pitfall.
3. Config/default change for recurring setup friction.
4. Tool error-message or preflight improvement when failures are diagnosable before execution.
5. Regression test for reproducible behavioral or code failures.
6. Resource recommendation for K3s requests/limits when usage, restarts, or
   OOM signals justify it.
7. Core code change only when the issue is systemic and narrower fixes will not hold.

Resource recommendations are advisory. Do not apply live Kubernetes changes,
restart workloads, or edit production manifests unless the user explicitly asks
for that change.

When an introspection pass completes a known maintenance item, record it:

```text
maintenance_freshness(action="record", key="introspection:self-review", status="ok|blocked|failed|proposed", evidence="<report path or summary>", actor="hermes-introspection")
```

Use the same pattern for related keys such as `memory:hygiene`,
`skills:review`, `tools:registry-smoke`, or `reproducibility:live-audit` when
the pass actually performed that work.

## Report Shape

When reporting, use this structure:

```md
## Working Well
- ...

## Repeated Friction
- Evidence, frequency, affected sessions/tools.

## Memory And Skill Quality
- ...

## Worth Adding
- Candidate improvements, ordered by score/impact.

## Research/Test Cycle
- What to inspect next.
- What test or replay proves the fix.
- Exact `scripts/run_tests.sh ...` selector.

## Guardrails
- What should require user approval.
```

## Validation

For Hermes repo code changes, activate the venv and use the wrapper:

```bash
source venv/bin/activate
scripts/run_tests.sh <selector>
```

Do not call `pytest` directly unless the wrapper is impossible to use.
