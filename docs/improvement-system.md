# Hermes Evolved Improvement System

This document explains the custom improvement, inspection, introspection, and
self-maintenance stack in this repository.

The short version: Hermes Evolved does not rely on one vague
"self-improvement" mechanism. It uses several bounded evidence loops:

- external edge-watch for upstream, docs, community, and ecosystem signal
- internal introspection for Hermes's own runtime behavior
- K3s resource review for deployment requests, limits, restarts, and live usage
- level-up hooks for tool failures, recovery, metrics, harvest, and correction
  guardrails
- shared-memory MCP so sibling coding-agent CLIs share institutional memory
- manual putter passes for idle, low-risk cleanup and general improvement
- guarded self-edit helpers for tested local patches
- cron and Kubernetes policy that keep all scheduled work bounded and auditable

These loops are intentionally conservative. They collect evidence, propose
changes, run tests, and preserve operator review points. They do not silently
push branches, merge PRs, mutate production, or rewrite live memory without a
specific path that makes the change auditable.

## Design Goals

The improvement system exists because an always-on agent needs more than a
conversation history.

It needs to answer:

- What changed upstream that matters to this deployment?
- What failures keep happening in our own sessions?
- Which user corrections should become durable guidance?
- Which memories are useful, stale, or too noisy for the prompt?
- Which skills are missing, wrong, or too large?
- Which tool paths are slow, brittle, or misconfigured?
- Which fixes are safe as skill/config updates, and which need code/tests?
- How can Codex, Claude Code, Cursor Agent, and Hermes share the same lessons?

The system is built around a few rules:

1. Evidence first, mutation later.
2. Use the least invasive fix that solves the repeated problem.
3. Keep prompt-visible memory small.
4. Prefer skills for reusable procedure.
5. Prefer tests for reproducible code behavior.
6. Require explicit approval for pushes, PRs, merges, deployment changes, and
   live gateway mutation.
7. Treat upstream `NousResearch/hermes-agent` as read-only signal for Hermes
   self-improvement. Any upstream contribution is a separate, explicit,
   human-approved workflow.
8. Treat `snapetech/hermes-agent-evolved` as generated publication output, not
   a PR or issue target.

## Improvement Loops At A Glance

| Loop | Looks At | Writes | Primary Tools |
| --- | --- | --- | --- |
| Edge-watch | upstream Hermes, docs, GitHub, Discord relay, community, research, manual inbox | `/opt/data/self-improvement/hermes_watch.db`, reports | `hermes-self-improvement-scan.py`, `hermes-edge-watch-query.py`, `edge-watch-mcp.py` |
| Internal introspection | sessions, tool errors, user corrections, memories, skills, trajectories | `/opt/data/self-improvement/introspection/reports/` | `hermes-introspection-scan.py`, `hermes-introspection` skill |
| K3s resource review | Deployment/CronJob requests and limits, `kubectl top`, pod restart/OOM signals | `/opt/data/self-improvement/resource-review/reports/` | `hermes-resource-review.py`, Putter |
| Local LLM nightly review | retained-family upgrades, new candidate discovery, benchmark/retain/reject cleanup | `/opt/data/self-improvement/local-llm-nightly/reports/`, `state.json` | `hermes-local-llm-nightly` skill, `scripts/local_llm_nightly_state.py`, benchmark scripts |
| Local LLM approval handoff | promotion/remediation proposals that need human review | `/opt/data/self-improvement/local-llm-nightly/handoffs/` | `hermes-local-llm-promotion-handoff` skill, `scripts/local_llm_handoff_packet.py`, GitHub/email delivery |
| Level-up recovery | failed tool calls and tool latency | `$HERMES_HOME/level_up/recovery.jsonl`, `tool_metrics.jsonl` | `plugins/level-up` hooks, `/recovery` |
| Level-up harvest | completed session transcripts | `$HERMES_HOME/level_up/harvest/*.jsonl` | `/harvest`, `/promote` |
| Level-up self-review | recovery and metrics history | `review_queue.jsonl`, `self_review_status.*` | `/self-review`, `plugins.level_up.self_review` |
| Correction guard | previous corrections, avoid rules, decisions | blocked tool call plus reminder | level-up `pre_tool_call` hook |
| Shared memory MCP | Hindsight, decisions, harvest corpora | Hindsight bank, `decisions.jsonl` | `shared-memory-mcp.py` |
| HTUI Pulse | TUI gateway events, stderr/protocol warnings, errors | `/opt/data/observability/hermes-pulse*.jsonl`, pending-turn checkpoints | `Ctrl+P`, `pulse.recent`, `tui_gateway/server.py` |
| Putter | current repo/profile, recent reports, todos, cache/state, docs drift | optional tiny patch, report, todo, or proposal | `putter` skill |
| Guarded self-edit | repo diffs and test results | `self-improve/*` branches, test logs | `hermes-self-edit.py` |

## Evidence-To-Change Ladder

When a finding appears, choose the smallest durable change that handles it.

1. **Memory update**  
   Use for stable user preferences, durable environment facts, and recurring
   operator expectations.

2. **Skill patch**  
   Use for reusable workflows, missing steps, stale troubleshooting, or repeated
   "do it this way" corrections.

3. **Config/default change**  
   Use when repeated setup or routing friction comes from a bad default.

4. **Tool preflight or error-message improvement**  
   Use when a tool can know before execution that credentials, paths, or
   dependencies are missing.

5. **Regression test**  
   Use when the behavior is reproducible and should stay fixed.

6. **Core code change**  
   Use when the failure is systemic and cannot be solved with guidance,
   configuration, or a narrow tool wrapper.

7. **Deployment change**  
   Use only when the problem is operational topology, image contents,
   Kubernetes policy, model service behavior, or persistent state wiring.

## Local LLM Nightly Resilience

The local-LLM nightly loop is stateful by design, not just report-first. It
uses three durable artifacts under:

```text
$HERMES_HOME/self-improvement/local-llm-nightly/
```

- `reports/YYYY-MM-DD.md` for the immutable nightly decision record
- `reports/latest.md` for the rolling pointer
- `state.json` for in-progress phase, candidate, and recovery state

The state file is managed by:

```bash
python scripts/local_llm_nightly_state.py reconcile
python scripts/local_llm_nightly_state.py begin --phase startup
python scripts/local_llm_nightly_state.py checkpoint --phase benchmark --candidate model.gguf
python scripts/local_llm_nightly_state.py candidate --name model.gguf --status rejected --local-path /opt/models/hermes-bench/model.gguf
python scripts/local_llm_nightly_state.py finalize --status completed --report-path "$HERMES_HOME/self-improvement/local-llm-nightly/reports/$(date +%F).md"
```

This lets the next nightly pass detect and repair:

- stale runs left in `running`
- interrupted candidate evaluations
- rejected downloads that were documented but not deleted
- missing report pointers after an otherwise completed pass

The nightly loop should self-fix bounded local issues where safe, but it must
still avoid live production mutation.

## Local LLM Approval Handoff

Promotion or remediation proposals that would change live Hermes behavior use a
separate handoff lane after the nightly review.

Artifacts live under:

```text
$HERMES_HOME/self-improvement/local-llm-nightly/handoffs/
```

Each proposal gets:

- `packet.json`
- `pr_body.md`
- `email.txt`

The handoff lane should:

- create a dedicated branch
- open or update a draft PR
- auto-deliver the approval summary to `keith@snape.tech`

It should stay silent when the nightly review found nothing that genuinely
needs human approval.

## External Edge-Watch

Edge-watch is the outward-facing improvement loop. It collects signal about
Hermes and the surrounding ecosystem so the deployment can stay aligned without
asking the main agent to repeatedly browse the same sources.

### Components

- `deploy/k8s/hermes-self-improvement-scan.py`  
  Pulls bounded source evidence, scores findings, persists them, writes alerts
  and digests.

- `deploy/k8s/hermes-edge-watch-query.py`  
  Operator CLI for searching the findings store.

- `deploy/k8s/edge-watch-mcp.py`  
  Read-only MCP server exposing recent findings, alerts, digests, stats, and
  bounded refresh triggers to sibling CLIs.

- `deploy/k8s/hermes-intel-sources.yaml`  
  Source registry and weighting reference.

- `deploy/k8s/self-improvement-cron.yaml`  
  Kubernetes CronJobs for quick, daily, and weekly passes.

Detailed reference: [`deploy/k8s/EDGE-WATCH.md`](../deploy/k8s/EDGE-WATCH.md).

### Sources

Current lanes include:

- upstream `NousResearch/hermes-agent` issues, PRs, releases, commits
- fork `example-org/hermes-agent-private` issues and PRs
- official docs diffs
- upstream/fork git drift
- Snapetech Discord crosspost relay
- r/hermesagent and selected LocalLLaMA searches
- arXiv feeds for Nous/Teknium/Hermes-relevant signal
- Hugging Face Nous org model/dataset signal
- X via Nitter fallback instances
- GitHub org events
- manual markdown inbox

The manual inbox is important for human-fed tribal knowledge:

```text
/opt/data/self-improvement/inbox/
```

Drop a markdown file with optional front matter; the scout ingests it, records
it as a finding, and moves it to `inbox/processed/`.

### Schedule

| CronJob | Cadence | Purpose |
| --- | --- | --- |
| `hermes-edge-watch-quick` | every 6 hours | fast-moving docs/git/GitHub/Discord/manual signal |
| `hermes-edge-watch-daily` | daily | quick pass plus community, research, Hugging Face, X, org events |
| `hermes-edge-watch-weekly` | weekly | roll-up digest |

All jobs use `concurrencyPolicy: Forbid`, bounded deadlines, and modest
resource requests/limits (`100m` CPU and `256Mi` memory requested; `1` CPU and
`1Gi` memory limited).

### Querying

Inside the pod:

```bash
/opt/data/scripts/hermes_edge_watch_query.py recent --since 24h --min-score 0.5
/opt/data/scripts/hermes_edge_watch_query.py search -q "memory"
/opt/data/scripts/hermes_edge_watch_query.py alerts
/opt/data/scripts/hermes_edge_watch_query.py stats --since 7d
/opt/data/scripts/hermes_edge_watch_query.py digest --kind daily
```

From sibling CLIs, use the `hermes-edge-watch` MCP server:

- `edge_watch.recent`
- `edge_watch.alerts`
- `edge_watch.digest`
- `edge_watch.stats`
- `edge_watch.trigger`

## Internal Introspection

Internal introspection is the inward-facing improvement loop. It asks how Hermes
itself is behaving.

### Components

- `deploy/k8s/hermes-introspection-scan.py`  
  Standalone report-first collector.

- `skills/autonomous-ai-agents/hermes-introspection/SKILL.md`  
  Skill that defines the rubric for interpreting the evidence and choosing
  improvements.

- `hermes-internal-introspection` CronJob  
  Weekly Kubernetes job in `deploy/k8s/self-improvement-cron.yaml`.

### What It Reviews

The collector inspects:

- recent sessions from `$HERMES_HOME/state.db`
- tool-result errors and failure categories
- repeated user corrections
- memory writes and memory quality
- skill maintenance debt
- oversized skills that should use progressive-disclosure references
- completed and failed trajectory JSONL files
- compression events and session source counts

It classifies common issue clusters:

- test failures
- timeouts
- missing dependencies
- missing credentials/secrets
- path/repo errors
- backend/network failures
- schema/config failures
- generic tool errors
- memory noise
- skill debt
- user correction patterns

### Running It

Standalone from the repo:

```bash
python3 deploy/k8s/hermes-introspection-scan.py --window-days 7 --session-limit 80
```

In the Kubernetes deployment:

```bash
HERMES_HOME=/opt/data \
python3 /opt/data/scripts/hermes_introspection_scan.py --window-days 7 --session-limit 120
```

Reports are written to:

```text
/opt/data/self-improvement/introspection/reports/
/opt/data/self-improvement/introspection/reports/latest.md
```

Raw CronJob logs are mirrored to:

```text
/opt/data/cron/output/introspection/
```

### Report Shape

The report intentionally has the same sections every time:

- Health Snapshot
- Working Well
- Repeated Friction
- Memory Quality
- Skill Quality
- Candidate Experiments
- Validation Pattern

The report does not patch anything by itself. It tells the next agent or
operator what is worth inspecting and how to validate it.

## K3s Resource Review

K3s resource review is the deployment-facing performance loop. It lets Hermes
inspect whether its Kubernetes requests and limits still match observed usage.

The helper is:

```text
deploy/k8s/hermes-resource-review.py
```

Bootstrap installs it in the pod as:

```text
/opt/data/scripts/hermes_resource_review.py
```

Run it inside the pod:

```bash
/opt/data/scripts/hermes_resource_review.py --write-report
```

For local manifest-only review:

```bash
python3 deploy/k8s/hermes-resource-review.py --local-only
```

The helper reads:

- live `Deployment` and `CronJob` resource requests/limits when `kubectl` is
  available
- local manifests as a fallback
- `kubectl top pod --containers` when metrics-server is available
- pod restart and `OOMKilled` signals from `kubectl get pods -o json`

Reports land under:

```text
/opt/data/self-improvement/resource-review/reports/
/opt/data/self-improvement/resource-review/reports/latest.md
```

### Resource Review Policy

The resource reviewer is advisory. It does not patch Kubernetes resources or
edit manifests.

Hermes may recommend resource changes when evidence supports them:

- raise memory request when live usage is repeatedly close to the request
- raise memory limit or investigate memory growth when usage is close to the
  limit or pods were `OOMKilled`
- raise CPU request when sustained usage is close to the request
- raise CPU limit or inspect runaway work when usage is close to the limit
- consider lowering requests only after repeated low-usage snapshots

Live resource changes are a trust boundary. Hermes may prepare a manifest patch
or exact `kubectl set resources` proposal, but it should not apply the change,
restart the gateway, or alter CronJob/Deployment resources without explicit
operator approval. Durable changes should land in git manifests first, then be
tested and deployed deliberately.

## Putter

`putter` is the manual idle-work loop. It is for the moment when the operator
does not have a specific task, but wants Hermes to look around and do one small
useful thing if one is available.

The bundled skill is:

```text
skills/autonomous-ai-agents/putter/SKILL.md
```

At runtime, invoke it as:

```text
/putter
/putter docs
/putter cache cleanup
/putter sync docs with deploy
/putter research anything stale
```

The skill is deliberately bounded. A putter pass should inspect a small amount
of local evidence, choose one low-risk candidate, act or stop, validate what it
can, and report the result. "Nothing worth doing" is a valid outcome.

Putter can improve its own instructions. If an idle pass discovers a new
low-risk task category, candidate source, validation pattern, or guardrail, it
may either patch `skills/autonomous-ai-agents/putter/SKILL.md` as the one small
task for that pass or propose the exact expansion in its final response. Direct
patches should be conservative and keep Putter bounded.

### Putter Work Menu

Good putter candidates include:

- repo cleanup: broken links, stale comments, outdated examples, missing docs
  map entries, safe generated-file sync checks
- low-risk updates: generated indexes, configmap embed checks, stale command
  references, docs-to-script drift
- research and inspection: latest introspection reports, edge-watch digests,
  repeated session corrections, recurring tool failures, failed trajectories
- sync tasks: README/deployment/decision doc consistency, public mirror
  allowlists, CronJob names, skill metadata, CLI/gateway command docs
- K3s resource review: inspect requests/limits, live usage snapshots, restart
  signals, and produce justified resource-change proposals
- cache/state work: safe local cache checks, noisy scratch-note compaction,
  memory compaction proposals, recovery recipe inspection
- skills and memory: missing validation notes, troubleshooting additions,
  bloated skill split proposals, memory proposals for stable preferences
- tests and validation: narrow test selectors, shell syntax checks, fixture
  updates, skipped-test review, docs-only link checks

Putter may keep low-risk maintenance as a local commit. Putter should escalate
to a PR against `example-org/hermes-agent-private` for runtime code, deployment
manifests, auth/approval/RBAC/sudo/secret handling, MCP exposure, model routing,
memory/session persistence, context compression, public mirror behavior,
multi-file refactors, failed/untested changes, or anything that needs review.
When opening or updating a PR, pushing a non-`main` branch is allowed. Putter
should not push directly to `main`, merge, deploy, mutate production, edit
secrets, change provider defaults, rewrite memory wholesale, clear evidence
needed for an active investigation, or run destructive cleanup commands without
explicit approval.

Every Putter change should also update `HERMES_CHANGELOG.md` with the local
commit hash or eventual GitHub commit link so the operator has one review
ledger across local commits and PR-backed changes.

The evidence rule is strict: do not delete logs, reports, caches, generated
output, or scratch files when they may explain an active failure or recent
decision. Preserve or summarize the evidence first; cleanup can be proposed
afterward.

### Putter State

Most passes should not write extra state. If a pass produces useful evidence
but no code/docs change, it may write a short workspace-local report under:

```text
.hermes/putter/
```

Use that only when it helps the next agent avoid repeating the same
investigation. Prefer a final response or todo item for simple outcomes.

## Level-Up Plugin

The `level-up` plugin is the runtime feedback layer. Bootstrap copies it to:

```text
/opt/data/plugins/level-up/
```

The plugin adds hooks, slash commands, logs, and a skill:

- plugin code: [`plugins/level-up/`](../plugins/level-up)
- skill: [`plugins/level-up/skills/level-up-ops/SKILL.md`](../plugins/level-up/skills/level-up-ops/SKILL.md)
- state root: `$HERMES_HOME/level_up/`

### Recovery Recipes

After a tool fails, the post-tool hook classifies the failure and advances a
recovery recipe. Events go to:

```text
$HERMES_HOME/level_up/recovery.jsonl
```

Categories include:

- backend timeout
- backend unreachable
- tool crash
- invalid tool output
- context overflow
- strategy exhausted
- approval timeout
- workspace conflict
- permission denied
- network error
- unknown

Use:

```text
/recovery [limit]
```

The purpose is to stop repeated blind retries. The recipe tells the next agent
what recovery step is appropriate.

### Escalation

Escalations are always written to:

```text
$HERMES_HOME/level_up/escalations.log
```

Optional channels are configured in:

```text
$HERMES_HOME/level_up/escalation.yaml
```

Escalation channels can include file, Discord, and webhook-style sinks. Bursts
are rate-limited by category so repeated failures do not flood the operator.

### Memory Harvest

At session end, and via manual command, level-up can extract durable knowledge
from recent sessions and queue it as proposals:

```text
$HERMES_HOME/level_up/harvest/facts.jsonl
$HERMES_HOME/level_up/harvest/corrections.jsonl
$HERMES_HOME/level_up/harvest/avoid.jsonl
```

Use:

```text
/harvest 5
/promote <kind> <line-or-id> [memory|user|soul|hindsight]
```

Harvest proposals are not prompt-visible until promoted. This avoids dumping
every session summary into memory.

### Correction Guard

Before risky tools run, the pre-tool hook compares the call text against:

- harvested corrections
- avoid patterns
- decision records

If overlap is high enough, the call is blocked with a reminder. The agent must
read the prior note and change the call or intentionally clean up a stale rule.

This is how repeated user corrections become operational guardrails.

### Self-Review

Level-up self-review scans:

```text
$HERMES_HOME/level_up/recovery.jsonl
$HERMES_HOME/level_up/tool_metrics.jsonl
```

It writes:

```text
$HERMES_HOME/level_up/review_queue.jsonl
$HERMES_HOME/level_up/self_review_status.json
$HERMES_HOME/level_up/self_review_status.md
$HERMES_HOME/level_up/self_review_runs.jsonl
```

Run:

```bash
/app/.venv/bin/python -m plugins.level_up.self_review --days 7
```

It auto-applies only a narrow set of low-risk recurring lessons, such as:

- not assuming `main` or `master`
- checking for `.git` before git commands
- avoiding manual `send_message` misuse from cron contexts

Everything else goes to a review queue.

### TaskPacket

`/task` wraps `delegate_task` in a structured contract:

- objective
- scope
- acceptance tests
- commit policy
- escalation policy
- wall-time limit
- allowed files

Task results are logged to:

```text
$HERMES_HOME/level_up/tasks.jsonl
```

Use TaskPacket when a delegated task needs explicit acceptance criteria rather
than a free-form subagent prompt.

### LSP Tool

The plugin registers an `lsp` tool for semantic code inspection:

- definition
- references
- hover
- document symbols
- workspace symbols

Use it when grep is not enough and the question is about symbols or code
structure. Server config lives at:

```text
$HERMES_HOME/level_up/lsp.yaml
```

### Boot Check, Audits, Metrics

Additional surfaces:

- `/boot-check` for deterministic startup checks
- `/skill-audit` for stale local path references in skills/memory/SOUL
- `/decision-hygiene` for stale or overlapping decisions
- `tool_metrics.jsonl` for compact tool duration/result-size telemetry

## Shared-Memory MCP

The shared-memory MCP bridge lets sibling coding-agent CLIs share durable
context with Hermes instead of creating separate memory islands.

Script:

```text
/opt/data/shared-memory-mcp.py
```

Source:

```text
deploy/k8s/shared-memory-mcp.py
```

It exposes:

- Hindsight retain/recall/reflect
- decisions from `$HERMES_HOME/decision_memory/decisions.jsonl`
- level-up harvest corpora
- escalation log

Tools:

- `memory.retain`
- `memory.recall`
- `memory.reflect`
- `memory.add_decision`
- `memory.list`

Resources:

- `hermes://decisions`
- `hermes://corrections`
- `hermes://avoid`
- `hermes://facts`
- `hermes://escalations`

Bootstrap injects this server into:

- Claude Code config
- Codex config
- Cursor Agent config

That means `claude`, `codex`, `cursor-agent`, and Hermes can all read and write
the same institutional memory when running in the pod.

## Edge-Watch MCP

The edge-watch MCP server makes external findings available to sibling agents.

Script:

```text
/opt/data/edge-watch-mcp.py
```

Source:

```text
deploy/k8s/edge-watch-mcp.py
```

Tools:

- `edge_watch.recent`
- `edge_watch.alerts`
- `edge_watch.digest`
- `edge_watch.stats`
- `edge_watch.trigger`

Use MCP for agent-facing access. Use `hermes_edge_watch_query.py` for shell
operator workflows.

## Guarded Self-Edit Workflow

`deploy/k8s/hermes-self-edit.py` is a guarded helper for local deployment
improvement branches.

Installed path:

```text
/opt/data/scripts/hermes_self_edit.py
```

Important commands:

```bash
/opt/data/scripts/hermes_self_edit.py doctor
/opt/data/scripts/hermes_self_edit.py start <slug>
/opt/data/scripts/hermes_self_edit.py test -- <test-selector>
/opt/data/scripts/hermes_self_edit.py status
/opt/data/scripts/hermes_self_edit.py submit --create-pr
```

The helper enforces several policies:

- self-edit branches must use the `self-improve/` prefix
- submit refuses `main` / `master`
- submit refuses sensitive-looking paths
- submit refuses untested changes unless explicitly overridden
- submit may push the self-edit branch for PR creation or updates
- PRs and issues target `example-org/hermes-agent-private` only
- PRs and issues must never target `NousResearch/hermes-agent` from this
  self-improvement workflow
- PRs and issues must never target `snapetech/hermes-agent-evolved`; the public
  mirror is updated only by the publisher workflow
- it does not deploy, restart services, import images, or mutate the live
  gateway

This makes agent-prepared changes possible without letting a scheduled job
silently alter production.

## Kubernetes Cron Guardrails

Custom maintenance jobs in `deploy/k8s/self-improvement-cron.yaml` follow a
bounded pattern:

- `concurrencyPolicy: Forbid`
- `restartPolicy: Never`
- finite `activeDeadlineSeconds`
- small resource requests/limits
- persistent output under `/opt/data/cron/output/...`
- persistent state under `/opt/data/self-improvement/...`
- no push/merge/deploy behavior from scheduled runs

Cron is for evidence collection, digesting, and conservative review. It is not
the authority to mutate production.

## Deployment Image Contract

The base Kubernetes manifests use `hermes-agent-sudo:local`, not a checked-in
commit-specific image tag. This keeps direct `kubectl apply -f deploy/k8s/*.yaml`
from rolling workloads to a stale or missing `git-<sha>` image.

The GitHub deploy workflow remains immutable at runtime:

1. Build `hermes-agent-sudo:git-<sha>` from the pushed commit.
2. Tag the same image as `hermes-agent-sudo:local`.
3. Import both tags into k3s containerd.
4. Apply a temporary kustomize image override so all live `hermes-agent-sudo`
   workloads run the immutable `git-<sha>` tag.

`tests/test_snapetech_deploy_customizations.py` enforces this contract and
fails if base manifests reintroduce pinned `git-<sha>` images.

## Bootstrap Repair Contract

Bootstrap treats empty `BOOT.md` and `SOUL.md` as broken state. It repairs
missing-or-empty files from the ConfigMap, while preserving non-empty operator
edits. It also promotes these ConfigMap-delivered helpers into persistent
runtime paths:

- `/opt/data/scripts/hermes_self_improvement_scan.py`
- `/opt/data/scripts/hermes_introspection_scan.py`
- `/opt/data/scripts/hermes_self_edit.py`
- `/opt/data/scripts/hermes_edge_watch_query.py`
- `/opt/data/edge-watch-mcp.py`
- `/opt/data/shared-memory-mcp.py`

## State Paths

Important persistent paths:

| Path | Purpose |
| --- | --- |
| `/opt/data/state.db` | Hermes sessions and FTS5 search |
| `/opt/data/memories/MEMORY.md` | compact agent memory |
| `/opt/data/memories/USER.md` | compact user profile |
| `/opt/data/self-improvement/hermes_watch.db` | edge-watch findings |
| `/opt/data/self-improvement/reports/` | edge-watch reports |
| `/opt/data/self-improvement/introspection/reports/` | internal introspection reports |
| `/opt/data/self-improvement/resource-review/reports/` | K3s resource review reports |
| `/opt/data/self-improvement/local-llm-nightly/reports/` | nightly local-model review reports |
| `/opt/data/cron/output/edge-watch/` | raw edge-watch CronJob logs |
| `/opt/data/cron/output/introspection/` | raw introspection CronJob logs |
| `/opt/data/level_up/recovery.jsonl` | tool failure/recovery events |
| `/opt/data/level_up/tool_metrics.jsonl` | tool latency/result-size telemetry |
| `/opt/data/level_up/harvest/` | proposed facts/corrections/avoid rules |
| `/opt/data/level_up/review_queue.jsonl` | self-review queue |
| `/opt/data/decision_memory/decisions.jsonl` | shared decisions |
| `/opt/data/shared-memory-mcp.py` | shared memory MCP server |
| `/opt/data/edge-watch-mcp.py` | edge-watch MCP server |
| `/opt/data/scripts/hermes_self_edit.py` | guarded self-edit helper |
| `/opt/data/scripts/hermes_introspection_scan.py` | internal introspection collector |
| `/opt/data/scripts/hermes_resource_review.py` | K3s resource review helper |
| `/opt/data/scripts/hermes_self_improvement_scan.py` | edge-watch scout |

## Regression Tests

Custom deployment behavior is covered by:

```bash
scripts/run_tests.sh tests/test_snapetech_deploy_customizations.py
scripts/run_tests.sh tests/test_edge_watch_mcp.py
scripts/run_tests.sh tests/test_hermes_self_improvement_scan.py
scripts/run_tests.sh tests/test_hermes_introspection_scan.py
```

The deployment customization test checks ConfigMap embed sync, custom CronJob
resource policy, Edge-Watch env/secret wiring, introspection runtime wiring,
MCP bootstrap registration, empty `BOOT.md`/`SOUL.md` repair, stable base image
tags, and public evolved README publication behavior.

## Operating Rhythm

A healthy improvement cycle looks like this:

1. Edge-watch notices external changes and writes findings.
2. Introspection notices internal friction and writes a report.
3. Level-up hooks record concrete tool failures and metrics during real work.
4. Harvest proposes durable facts, corrections, and avoid rules after sessions.
5. The agent or operator reviews evidence and chooses the least invasive fix.
6. Skills/memory/config are updated when appropriate.
7. Code changes get targeted tests.
8. Self-edit helper prepares guarded branches only when asked.
9. Publishing/deployment still requires explicit approval.

## What Not To Do

Do not:

- put every session summary into prompt-visible memory
- treat edge-watch findings as automatic action items
- let cron jobs push branches or deploy changes
- open self-improvement PRs against `NousResearch/hermes-agent`
- open self-improvement PRs against `snapetech/hermes-agent-evolved`
- bypass correction guard wording instead of resolving the underlying note
- use MCP bridges as a substitute for reviewing sensitive diffs
- let public docs contain real hostnames, channel IDs, user IDs, tokens, or
  private service topology

## Where To Go Next

- External signal details: [`deploy/k8s/EDGE-WATCH.md`](../deploy/k8s/EDGE-WATCH.md)
- Kubernetes deployment details: [`deploy/k8s/README.md`](../deploy/k8s/README.md)
- Design rationale: [`docs/evolved-decisions.md`](evolved-decisions.md)
- Public reproduction: [`docs/reproducibility-audit.md`](reproducibility-audit.md)
- Model/backend decisions: [`docs/evolved-model-matrix.md`](evolved-model-matrix.md)
- Research/update cycles: [`docs/research-update-cycles.md`](research-update-cycles.md)
- Upstream sync: [`docs/upstream-sync.md`](upstream-sync.md)
