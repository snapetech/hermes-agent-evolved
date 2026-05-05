# Hermes Agent Evolved Decisions

This document records the public-safe design decisions behind the
`hermes-agent-evolved` line. The base project remains
`NousResearch/hermes-agent`; this repository layers a reproducible deployment
and operating model on top of that upstream, then explains which parts are
deployment opinion and which parts could be considered for a separate,
human-approved upstream contribution when generally useful.

## Operating Principle

Hermes Agent Evolved is not a fork with a different product direction. It is an
upstream-aligned deployment overlay:

- keep upstream Hermes as the primary source of product behavior
- keep deployment-specific code, manifests, and runbooks in the overlay
- treat upstream releases, docs, issues, and PRs as read-only signal
- keep Hermes self-improvement PRs and issues in `example-org/hermes-agent-private`
  only
- treat `snapetech/hermes-agent-evolved` as generated publication output, not a
  PR or issue target
- upstream reusable fixes only through a separate human-approved contribution
  workflow, never through autonomous self-improvement
- publish only sanitized, reproducible material in the public evolved mirror

The practical goal is that someone can start from the public repository,
understand the choices, replace private endpoints with their own, and reproduce
the same kind of always-on Hermes system without needing private chat history or
operator shell history.

## Decision Log

| Area | Decision | Why | Upstream relationship |
| --- | --- | --- | --- |
| Repository model | Maintain a private package/deploy repo and publish a sanitized upstream-based evolved mirror. | The live cluster needs private manifests, hostnames, tokens, runner labels, and runbooks that cannot be public. The public mirror should still be reproducible and reviewable. | Public mirror is rebuilt from upstream plus a small overlay commit. Upstream history is preserved. |
| Public CI | Strip inherited upstream GitHub Actions workflows from the public evolved mirror. | Upstream workflows test the full upstream product and deployment/site assumptions, not this sanitized overlay. Running them in the public mirror creates noisy failures and can pressure future changes to add secrets or private runner details. | Purpose-built public checks can be added later when they are self-contained and secret-free. |
| Kubernetes deployment | Run Hermes as a persistent Kubernetes workload with one PVC-backed Hermes home. | The agent is intended to survive pod replacement with sessions, memories, cron jobs, workspace files, auth state, and installed tools intact. | Upstream supports many runtimes; this is one deployment profile. |
| State root | Use `/opt/data` as the persistent Hermes home and `/opt/data/workspace` as the terminal working tree. | Keeps runtime state separate from the replaceable container image. Makes rollouts deterministic. | Consistent with upstream profile/state isolation concepts, but pathing is deployment-specific. |
| Image shape | Build a derived image with ops/debug tools, coding-agent CLIs, TUI assets, and passwordless in-container `sudo`. | A self-operating cluster agent repeatedly needs Git, SSH, Kubernetes tools, diagnostics, Node, Python packaging, and TUI runtime files. Preinstalling them avoids first-session bootstrap churn. | Image additions are overlay packaging. Reusable runtime fixes should be upstreamed separately. |
| Image tags | Keep base manifests on `hermes-agent-sudo:local`; have the deploy workflow build/import both `git-<sha>` and `local`, then apply a kustomize override to the immutable git tag. | Direct `kubectl apply -f` should not roll workloads to a stale missing commit image, while normal deploys should remain immutable and traceable to a commit. | `tests/test_snapetech_deploy_customizations.py` prevents checked-in `git-<sha>` pins from creeping back into base manifests. |
| Runtime bootstrap | Create a persistent workspace venv and persistent npm global prefix on boot. | Dependencies installed by the agent should survive rollouts without baking every possible package into the image. | Deployment-specific. It uses normal Python/npm mechanisms rather than changing upstream dependency resolution. |
| Config source of truth | Seed `/opt/data/config.yaml` from the Kubernetes ConfigMap during pod initialization. | Rollouts should converge to known config. Hot edits inside the pod should not silently become the long-term source of truth. | Deployment-specific. |
| Model backend | Use an OpenAI-compatible host-side `llama.cpp` service as the primary backend, reached through a pod-local admission proxy. | The live deployment is GGUF-first, single-operator, and benefits from tuning inference independently of the gateway container. The proxy protects the single local inference slot from oversized requests. | Upstream remains provider-neutral. This is one custom-provider deployment shape. |
| Context policy | Advertise the context length actually served by the backend and keep it at or above Hermes's minimum. | Hermes rejects too-small context windows before a turn starts. Lying lower than the served window breaks agent startup; lying higher than served capacity causes runtime overflow. | Aligns with upstream context metadata expectations. |
| Admission overflow handling | Let the proxy reject or mark oversized requests; let Hermes own transcript compaction and retry. | Hermes owns the session transcript, memory flushes, compressor, and session metrics. The proxy should stay focused on admission control. | Hermes-side generic overflow handling is upstreamable when it is not tied to this proxy. |
| Fallback routing | Keep the local model primary and use adaptive fallback only for configured remote routes. Avoid retrying a wedged local backend as its own fallback. | A failed local backend can otherwise burn repeated timeouts before recovering. Fallback should change route or fail clearly. | Uses upstream provider/fallback concepts. Route order is deployment-specific. |
| Memory | Keep prompt-visible markdown memory small and put durable recall in structured memory. | Large always-visible memory bloats every turn. Structured memory gives better long-term recall without filling the prompt. | Aligns with upstream memory architecture; Hindsight deployment is overlay-specific. |
| Shared memory bridge | Expose Hermes memory/decisions to sibling coding-agent CLIs through a local MCP server. | Codex, Claude Code, Cursor Agent, and Hermes should share durable deployment knowledge when running in the same pod. | Overlay integration. Could become a general example if sanitized. |
| Messaging surface | Use Discord as a persistent chat surface with streaming/progress enabled. | Long-running turns need visible progress or users will assume the bot died. | Upstream gateway supports multiple platforms; Discord choices are deployment-specific. |
| TUI surface | Run the upstream TUI inside the live pod against the same Hermes home as the gateway. | CLI/TUI and Discord should see the same sessions and state. Host-local TUI would create a separate state island. | Uses upstream TUI. Image/layout work is overlay packaging. |
| Cron and self-maintenance | Run bounded maintenance jobs for memory hygiene, operational checks, and upstream/community signal gathering. | Always-on agents need scheduled review, but jobs must be bounded and auditable to avoid drift and chat noise. | Cron is upstream capability; job content is deployment-specific. |
| Edge watch | Collect upstream docs/release/issue/PR/community signals into a local evidence store. | The overlay should stay aligned with upstream and notice install, memory, gateway, security, and automation issues before they become deployment failures. | Upstream is signal, not mutation target. |
| Self-edit guardrails | Allow guarded branches/tests for local improvements, but require explicit approval for pushes, deploys, and live gateway mutation. | Autonomy is useful for triage and patch preparation; live operations remain a trust boundary. | Deployment policy. |
| Public publication | Publish sanitized docs and examples, not live manifests with real infrastructure details. | Reproducibility needs architecture and commands; security requires placeholders for hosts, tokens, IDs, runner labels, and private topology. | Keeps upstream and public users safe while preserving useful operational knowledge. |

## Extension Inventory

These are the major evolved extensions that someone reproducing this work
should understand.

### Kubernetes Overlay

Location: `deploy/k8s/`

The overlay defines the long-running gateway deployment, persistent state,
bootstrap ConfigMap, derived image, optional Hindsight service, admission proxy,
operator scripts, and public-safe deployment notes.

The important behavior is not just "run a pod." It is:

- one durable Hermes home
- one durable workspace
- replaceable containers
- deterministic bootstrap
- shared state across gateway and in-pod TUI
- explicit secrets instead of committed credentials

### Derived Runtime Image

Location: `deploy/k8s/Dockerfile.sudo`

The derived image packages the tools the cluster agent is expected to need in
normal work. This includes operational tools, coding-agent CLIs, browser/tooling
dependencies, and the TUI runtime assets.

This decision trades a larger image for a much lower chance that the agent
spends early turns repairing its own environment.

### Custom And Semi-Custom Tooling

Detailed inventory: [`docs/evolved-tooling.md`](evolved-tooling.md)

This includes the Manifest.build provider integration, Hindsight structured
memory, shared-memory MCP, edge-watch MCP, level-up, runtime-control,
ops-runtime dashboard, admission proxy, putter, resource review, and guarded
self-edit helpers. Some are live deployment paths; others are integrated and
tested but only active when explicitly configured.

### Research And Update Cycles

Detailed workflow: [`docs/research-update-cycles.md`](research-update-cycles.md)

The evolved overlay treats research, upgrades, dependency review, upstream sync,
skill maintenance, memory promotion, K3s resource review, and public mirror
publication as evidence-to-change cycles. Scheduled jobs and skills may collect
evidence and produce reports, but mutation stays bounded: broad research does
not imply automatic upgrades, live route changes, resource changes, PRs,
publishing, or deploys.

### Admission Proxy

Location: `deploy/k8s/llama-admission-proxy.py`

The proxy fronts an OpenAI-compatible local model service. It estimates request
size and prevents oversized turns from occupying the only local inference slot.
When overflow occurs, Hermes should compact and retry with awareness of its own
transcript instead of asking the proxy to perform opaque prompt surgery.

### Hindsight Memory Deployment

Locations:

- `deploy/k8s/hindsight.yaml`
- `deploy/k8s/hindsight-config.json`
- `deploy/k8s/shared-memory-mcp.py`

The evolved deployment uses structured memory for durable facts and exposes
that memory to sibling agent CLIs. Prompt-visible markdown memory remains small
and procedural.

### Self-Improvement Watch

Locations:

- `deploy/k8s/hermes-self-improvement-scan.py`
- `deploy/k8s/hermes-introspection-scan.py`
- `deploy/k8s/hermes-resource-review.py`
- `deploy/k8s/hermes-edge-watch-query.py`
- `deploy/k8s/edge-watch-mcp.py`
- `deploy/k8s/hermes-intel-sources.yaml`
- `deploy/k8s/self-improvement-cron.yaml`
- `skills/autonomous-ai-agents/putter/SKILL.md`
- `docs/improvement-system.md`

The watch system has three lanes. Edge-watch collects bounded evidence from
upstream and public/community signals. Internal introspection reviews Hermes's
own sessions, tool errors, user corrections, memory quality, skill debt, and
trajectory artifacts. K3s resource review checks whether deployment requests
and limits still match observed usage, restart, and OOM evidence. Putter is the
manual idle-work lane: when the operator asks Hermes to putter, it may do one
low-risk cleanup, update, research, sync, cache, compaction, resource-review,
docs, test, or general-improvement task, then stop. All lanes should surface
candidate issues, regressions, docs changes, and reproducible workflows without
mutating upstream or live infrastructure.

### Level-Up Runtime Feedback

Locations:

- `plugins/level-up/`
- `plugins/level-up/skills/level-up-ops/SKILL.md`
- `deploy/k8s/shared-memory-mcp.py`
- `docs/improvement-system.md`

The level-up plugin records failed tool calls, recovery recipes, tool metrics,
session-end harvest proposals, correction guardrails, TaskPacket delegations,
LSP code intelligence, and conservative self-review output. The shared-memory
MCP bridge exposes Hindsight, decisions, corrections, avoid rules, facts, and
escalations to sibling coding-agent CLIs so Hermes, Codex, Claude Code, and
Cursor Agent share institutional memory in the pod.

### Public Evolved Mirror

Locations:

- `.github/workflows/publish-evolved.yml`
- `scripts/publish_evolved_repo.sh`

The publisher builds a clean public tree from upstream `NousResearch/hermes-agent`
plus selected sanitized overlay files. It also scans for high-confidence secrets
and private infrastructure markers before pushing.

## What Belongs Upstream

Prefer upstream PRs for changes that are broadly useful and do not depend on
this cluster:

- provider integration that fits Hermes's normal provider registry
- generic context-overflow handling
- gateway interruption or streaming fixes
- profile-safe path fixes
- tests for upstream behavior
- docs that help all Hermes users

Keep these in the overlay unless they become general:

- private Kubernetes manifests
- hostnames, runner labels, Discord IDs, and local service IPs
- cluster-specific model flags
- mirrored operator auth contracts
- self-hosted deploy scripts
- local memory jobs and watch-source weighting

## Maintenance Rules

Before syncing or publishing:

1. Run the upstream sync report to see what changed upstream.
2. Re-check any local patches touching agent loop, gateway, model routing,
   compression, memory, and deployment bootstrap.
3. Keep public docs placeholder-based.
4. Keep credentials in environment variables, Kubernetes Secrets, or GitHub
   repository secrets.
5. Run the sanitizer/publisher dry run before pushing an evolved mirror.
6. Treat upstream as the primary product line and the evolved overlay as an
   operational layer.
