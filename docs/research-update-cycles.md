# Research, Update, And Upgrade Cycles

This document explains how Hermes Evolved researches changes, evaluates update
candidates, upgrades safely, and keeps its skills/tools/docs current.

It complements:

- [`docs/improvement-system.md`](improvement-system.md)
- [`docs/evolved-tooling.md`](evolved-tooling.md)
- [`docs/upstream-sync.md`](upstream-sync.md)
- [`deploy/k8s/EDGE-WATCH.md`](../deploy/k8s/EDGE-WATCH.md)

## Operating Rule

Research is allowed broadly. Mutation is bounded.

Hermes may collect evidence, summarize findings, compare versions, inspect
release notes, run local checks, and prepare proposed patches. It must not
silently upgrade production, push branches, open PRs, merge, deploy, restart
the gateway, rotate secrets, or change live Kubernetes resources without
explicit approval.

Self-improvement PRs and issues target `example-org/hermes-agent-private` only.
`NousResearch/hermes-agent` is read-only signal for autonomous work, and
`snapetech/hermes-agent-evolved` is generated publication output.

## Cycle Map

| Cycle | Purpose | Primary Tools | Output | Mutation Policy |
| --- | --- | --- | --- | --- |
| Edge-watch | Track upstream, docs, community, and ecosystem changes | `hermes-self-improvement-scan.py`, `hermes_edge_watch_query.py`, `edge-watch-mcp.py` | findings DB, alerts, daily/weekly reports | report-only |
| Upstream sync | Decide whether to merge upstream Hermes | `scripts/upstream_sync_report.sh`, `scripts/upstream_sync_prepare_branch.sh` | sync report, human-reviewed branch | branch only; no direct main merge |
| Dependency/package review | Inspect Python/npm/image/tooling drift | `rg`, package manifests, lockfiles, release notes, targeted tests | proposal or tested patch | no speculative upgrades |
| Skill update | Keep procedural knowledge current | `/skills`, `skill_view`, bundled `skills/`, Putter | skill patch or proposal | patch only with evidence |
| Research skill use | Pull technical/research context | `arxiv`, `blogwatcher`, `llm-wiki`, `research-paper-writing`, web tools | summary, citation, candidate action | no mutation by itself |
| Runtime tooling review | Check custom/semi-custom integrations | `docs/evolved-tooling.md`, tests, provider/Hindsight checks | docs/test/config patch | approval for live route changes |
| K3s resource review | Evaluate requests/limits/restarts/OOMs | `hermes-resource-review.py`, `kubectl top`, pod status | advisory report | no live resource changes without approval |
| Nightly local LLM review | Research upgrades and replacements for local GGUF/llama.cpp lanes, benchmark viable newcomers, retain winners, and document/delete rejects | `hermes-local-llm-nightly`, `hermes_model_benchmark.py`, `llama_throughput_compare.py`, `qwen36_knob_bench.sh` | updated matrix docs, retention/rejection notes, bounded downloads | no live primary switch or deploy without approval |
| Public mirror publication | Publish sanitized evolved overlay | `scripts/publish_evolved_repo.sh`, `publish-evolved.yml` | public mirror commit | generated output only |
| Putter | Manual idle improvement pass | `putter` skill, local evidence, targeted checks | one small change/proposal/nothing | low-risk only |

## Research Sources

Use the least noisy source that answers the question.

### Internal Sources

- recent sessions in `$HERMES_HOME/state.db`
- prompt-visible memory and user memory
- Hindsight recall/reflect
- level-up recovery and tool metrics
- edge-watch reports and finding DB
- introspection reports
- resource-review reports
- current git diff and recent commits
- tests and failure logs
- bundled skills and plugin docs

### External Sources

- upstream `NousResearch/hermes-agent` issues, PRs, releases, commits, and docs
- `example-org/hermes-agent-private` issues and PRs
- official provider/model docs
- package release notes and changelogs
- security advisories when dependency changes are involved
- arXiv, Hugging Face, Nous org activity, selected community sources
- manual inbox notes under `/opt/data/self-improvement/inbox/`

For changing or unstable facts, verify current sources before acting.

## Skills Used For Research And Updates

Relevant bundled skills include:

- `skills/research/arxiv/SKILL.md`  
  Use for paper discovery and arXiv evidence.

- `skills/research/blogwatcher/SKILL.md`  
  Use for blog/source monitoring and web update tracking.

- `skills/research/llm-wiki/SKILL.md`  
  Use for model/ecosystem background research.

- `skills/research/research-paper-writing/SKILL.md`  
  Use for deeper research synthesis and citation workflows.

- `skills/github/codebase-inspection/SKILL.md`  
  Use for repository investigation before changing code.

- `skills/github/github-issues/SKILL.md` and
  `skills/github/github-pr-workflow/SKILL.md`  
  Use for issue/PR work, respecting the repo target policy.

- `skills/software-development/systematic-debugging/SKILL.md`  
  Use when an update causes a failure or repeated symptom.

- `skills/software-development/test-driven-development/SKILL.md`  
  Use when a reproducible behavior needs a regression test.

- `skills/autonomous-ai-agents/hermes-introspection/SKILL.md`  
  Use for inward-facing improvement reviews.

- `skills/autonomous-ai-agents/hermes-local-llm-nightly/SKILL.md`  
  Use for the recurring local-model research, benchmark, retention, and cleanup
  cycle across retained families and new candidates.

- `skills/autonomous-ai-agents/hermes-local-llm-promotion-handoff/SKILL.md`  
  Use when the nightly local-model cycle found a promotion or remediation that
  should become a draft PR plus approval email instead of an inline live
  change.

- `skills/autonomous-ai-agents/putter/SKILL.md`  
  Use for low-risk idle cleanup, update checks, docs sync, cache/state review,
  and small research passes.

When a repeated research/update workflow emerges, prefer a skill patch over
remembering it only in a chat transcript.

## Evidence-To-Action Ladder

Use this ladder for update and upgrade decisions:

1. **Record or summarize**  
   Store the finding in an edge-watch/introspection/resource report, final
   response, or todo.

2. **Research**  
   Verify current facts from primary sources, release notes, upstream issues,
   or local evidence.

3. **Classify risk**  
   Label the candidate as docs-only, skill-only, config, dependency,
   deployment, model route, memory, or core code.

4. **Choose the smallest durable action**  
   Prefer docs, skills, config, or preflight checks before code changes.

5. **Patch locally**  
   Make the smallest repo change that captures the new knowledge or fixes the
   issue.

6. **Validate narrowly**  
   Run the relevant `scripts/run_tests.sh ...` selector, shell syntax check,
   link check, resource review, or configmap sync check.

7. **Escalate for approval**  
   Ask before pushing, opening PRs, publishing, deploying, restarting services,
   changing live resources, or rotating secrets.

## Upgrade Categories

### Upstream Hermes

Use [`docs/upstream-sync.md`](upstream-sync.md).

Normal flow:

1. Generate upstream sync report.
2. Read upstream releases/PRs for touched surfaces.
3. Classify overlap and keep-local surfaces before touching code.
4. Prepare a branch from the private fork `main`.
5. Adapt or cherry-pick high-value upstream fixes first.
6. Merge only when justified, not by default.
7. Run targeted tests.
8. Publish sanitized mirror only after private repo changes pass.

Do not let autonomous self-improvement open upstream PRs. Human-approved
upstream contributions are separate.

### Python Dependencies

Use dependency changes only when justified by:

- security fix
- compatibility requirement
- failed install/build/runtime evidence
- explicit feature need
- upstream Hermes change requiring it

Avoid broad version bumps during Putter or scheduled jobs. If lockfiles or
package metadata change, summarize why and run the narrowest relevant tests.

### Node/TUI Dependencies

Treat `ui-tui` separately:

```bash
cd ui-tui
npm run type-check
npm test
npm run build
```

Do not run broad dependency upgrades unless the target is clear and testable.

### Image And OS Packages

The derived image should gain tools only when they are repeatedly useful,
stable, and hard to install at runtime.

Prefer:

- image baseline for durable operational tooling
- persistent workspace venv/npm prefix for project/runtime additions
- docs/skills for one-off commands

Image changes require rebuild and deployment approval.

### Model Providers And Routes

Provider changes affect cost, latency, capability, credentials, and failure
modes. Treat these as config/runtime changes, not casual cleanup.

Relevant docs:

- [`docs/evolved-tooling.md`](evolved-tooling.md)
- [`docs/evolved-model-matrix.md`](evolved-model-matrix.md)
- `website/docs/developer-guide/provider-runtime.md`

Changing the live model route, Manifest.build route, fallback route, or
provider credentials requires explicit approval.

### Hindsight And Memory

Memory updates need a stable reason:

- repeated user preference
- durable environment fact
- reusable operational decision
- recurring correction

Do not promote every research result into prompt-visible memory. Use Hindsight,
session search, reports, or skills when the knowledge is too large or too
procedural for `MEMORY.md`.

### Skills

Skills are the preferred place for reusable procedure. Update a skill when:

- the user corrected a repeated workflow
- a tool has a recurring pitfall
- validation steps changed
- setup instructions drifted
- a new useful research/update loop emerged

Keep skills concise. Put deep references in `references/`.

### Kubernetes Resources

Use `hermes-resource-review.py` for evidence.

Resource changes need justification:

- sustained usage near request
- near-limit memory/CPU
- `OOMKilled`
- repeated restarts
- clear workload shape change

Do not apply live resource changes without approval. Prefer manifest patches in
git plus targeted checks.

## Cadence

| Cadence | Cycle |
| --- | --- |
| Every 6 hours | edge-watch quick pass |
| Daily | broader edge-watch pass |
| Weekly | edge-watch roll-up and internal introspection |
| On demand | Putter, resource review, upstream sync report, public mirror dry run |
| Before deploy | targeted tests, configmap sync check, image/tag checks, publisher scans |
| After repeated correction | skill or memory update proposal |

## Commands

Edge-watch:

```bash
/opt/data/scripts/hermes_edge_watch_query.py recent --since 24h --min-score 0.5
/opt/data/scripts/hermes_edge_watch_query.py search -q "provider"
/opt/data/scripts/hermes_edge_watch_query.py digest --kind daily
```

Introspection:

```bash
python3 deploy/k8s/hermes-introspection-scan.py --window-days 7 --session-limit 80
```

Resource review:

```bash
python3 deploy/k8s/hermes-resource-review.py --local-only
/opt/data/scripts/hermes_resource_review.py --write-report
```

Upstream sync:

```bash
scripts/upstream_sync_report.sh
scripts/upstream_sync_prepare_branch.sh
APPLY_MERGE=1 scripts/upstream_sync_prepare_branch.sh
```

ConfigMap embeds:

```bash
python3 scripts/sync_configmap_embeds.py
python3 scripts/sync_configmap_embeds.py --check
```

Public mirror:

```bash
scripts/publish_evolved_repo.sh
scripts/publish_evolved_repo.sh --push
```

Tests:

```bash
source .venv/bin/activate
scripts/run_tests.sh <selector>
```

## What Not To Do

Do not:

- upgrade dependencies speculatively
- change live model/provider routing without approval
- promote noisy research into prompt-visible memory
- treat edge-watch findings as automatic work orders
- apply live Kubernetes resource changes from a report alone
- open self-improvement PRs outside `example-org/hermes-agent-private`
- publish private manifests or secrets to the public mirror
- let scheduled jobs push branches, merge, deploy, or restart services
