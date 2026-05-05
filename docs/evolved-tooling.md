# Hermes Evolved Tooling

This document lists the custom and semi-custom tooling in this repository that
goes beyond stock `NousResearch/hermes-agent`. The goal is to make the overlay
auditable: what was added, why it exists, where it lives, and whether it is
active in the live deployment or just available as an integration path.

Related references:

- [`docs/evolved-decisions.md`](evolved-decisions.md) explains why the overlay
  exists and which changes belong upstream versus in the deployment layer.
- [`docs/improvement-system.md`](improvement-system.md) is the detailed
  internal/external self-improvement operating manual.
- [`docs/research-update-cycles.md`](research-update-cycles.md) explains the
  evidence-to-change cycle for research, upgrades, sync, resource review, and
  publication.
- [`deploy/k8s/README.md`](../deploy/k8s/README.md) maps the tooling to the
  live Kubernetes deployment.

## Boundary

Stock Hermes provides the agent loop, CLI, gateway, tools, skills, memory
interface, cron, MCP support, ACP, TUI, provider registry, and plugin system.

Hermes Evolved adds an operating layer around those primitives:

- Kubernetes deployment and bootstrap conventions
- a derived runtime image
- host-side/local-model routing choices
- structured memory deployment
- sibling-agent MCP bridges
- bounded self-improvement loops
- operational plugins and dashboards
- publication tooling for the public evolved mirror

Self-improvement PRs and issues target `example-org/hermes-agent-private` only.
`NousResearch/hermes-agent` is read-only signal for autonomous improvement, and
`snapetech/hermes-agent-evolved` is generated publication output.

## Tooling Inventory

| Tooling | Type | Primary Paths | Status |
| --- | --- | --- | --- |
| Manifest provider | semi-custom provider integration | `hermes_cli/auth.py`, `hermes_cli/models.py`, `hermes_cli/runtime_provider.py`, `tests/hermes_cli/test_manifest_provider.py` | available, not the live default |
| Hindsight memory | structured memory provider and optional K8s service | `plugins/memory/hindsight/`, `deploy/k8s/hindsight.yaml`, `deploy/k8s/hindsight-config.json` | optional structured memory path |
| Shared-memory MCP | sibling-agent memory bridge | `deploy/k8s/shared-memory-mcp.py` | installed into `/opt/data/shared-memory-mcp.py` |
| Desktop bridge MCP | local desktop/audio companion | `deploy/k8s/desktop-bridge-mcp.py` | installed into `/opt/data/desktop-bridge-mcp.py`, disabled until configured |
| Level-up plugin | runtime feedback plugin | `plugins/level-up/` | copied into `/opt/data/plugins/level-up/` |
| Runtime-control plugin | operational policy hooks | `plugins/runtime-control/` | copied into `/opt/data/plugins/runtime-control/` |
| Ops Runtime dashboard | dashboard extension | `plugins/ops-runtime/dashboard/` | bundled dashboard tab |
| Admission proxy | local model guard/proxy | `deploy/k8s/llama-admission-proxy.py` | live model path in the K8s deployment |
| HTUI Pulse and pending turns | TUI observability/recovery | `ui-tui/`, `tui_gateway/server.py`, `deploy/k8s/htui.sh` | active in the pod-backed TUI |
| Edge-watch | external signal scout | `deploy/k8s/hermes-self-improvement-scan.py`, `deploy/k8s/EDGE-WATCH.md` | scheduled evidence collection |
| Internal introspection | internal behavior review | `deploy/k8s/hermes-introspection-scan.py`, `skills/autonomous-ai-agents/hermes-introspection/SKILL.md` | scheduled/report-first |
| K3s resource review | resource recommendation helper | `deploy/k8s/hermes-resource-review.py` | advisory/report-first |
| Putter | manual idle-work skill | `skills/autonomous-ai-agents/putter/SKILL.md` | explicit operator-invoked skill |
| Guarded self-edit | local branch/test/PR helper | `deploy/k8s/hermes-self-edit.py` | explicit operator-approved workflow |
| Public mirror publisher | sanitized publication | `.github/workflows/publish-evolved.yml`, `scripts/publish_evolved_repo.sh` | publishes to `snapetech/hermes-agent-evolved` |
| Research/update cycles | evidence-to-change workflow | `docs/research-update-cycles.md`, `deploy/k8s/EDGE-WATCH.md`, `docs/upstream-sync.md` | policy and operator reference |

## Manifest Provider

Manifest.build is represented in Hermes as the `manifest` provider.

Provider behavior:

- provider id: `manifest`
- aliases: `mnfst`, `manifest-build`, `manifest.build`
- model catalog: `manifest/auto`
- default base URL: `http://localhost:3001/v1`
- API key env var: `MANIFEST_API_KEY`
- base URL env var: `MANIFEST_BASE_URL`
- context metadata: `manifest/auto` is treated as a large-context route so
  Hermes does not fall back to a tiny unknown-provider default.

Why it exists:

Manifest can route across local and subscription-backed endpoints without
forcing Hermes to model every downstream endpoint as a first-class provider.
Adding it as a normal provider keeps `/model`, config loading, auth resolution,
runtime provider resolution, and tests on the stock Hermes provider path.

Current live status:

The provider is available in code, but the live K8s gateway is not currently
routed through Manifest. The live path remains the local Qwen/GGUF model behind
the pod-local admission proxy unless `MANIFEST_API_KEY` and
`MANIFEST_BASE_URL` are explicitly configured and selected.

Validation:

```bash
scripts/run_tests.sh tests/hermes_cli/test_manifest_provider.py
```

## Hindsight

Hindsight is the structured memory layer. It complements, rather than replaces,
small prompt-visible memory files.

Primary pieces:

- `plugins/memory/hindsight/` provides the Hermes memory provider.
- `deploy/k8s/hindsight.yaml` defines the optional in-cluster Hindsight service
  and Postgres backing store.
- `deploy/k8s/hindsight-config.json` seeds the deployment configuration.
- `deploy/k8s/public-examples/hindsight/` documents a public-safe reproduction
  path.

Hindsight supports retain, recall, and reflect operations. In this overlay, it
is also exposed to sibling coding-agent CLIs through the shared-memory MCP
bridge, so Hermes, Codex, Claude Code, and Cursor Agent can share durable facts
and decisions when they run in the same pod.

The policy is still conservative: prompt-visible `MEMORY.md` and `USER.md`
should stay compact. Durable, searchable, cross-session knowledge belongs in
structured memory or session search.

## Shared-Memory MCP

`deploy/k8s/shared-memory-mcp.py` is a local stdio MCP server installed at:

```text
/opt/data/shared-memory-mcp.py
```

It exposes:

- Hindsight retain/recall/reflect
- compact decision memory
- level-up harvest corpora
- correction and avoid-rule signal

This is deployment glue. It gives sibling CLIs a shared institutional memory
without requiring every tool to understand Hermes internals.

## Desktop Bridge MCP

`deploy/k8s/desktop-bridge-mcp.py` is a companion bridge for cases where Hermes
needs to observe or drive an operator desktop instead of only the pod.

The bridge has two sides:

- a local HTTP process on the desktop that owns the real display and audio
- a stdio MCP process in the pod that proxies tool calls to that desktop URL

Read-only tools are available by default on the desktop side:

- `desktop.status`
- `desktop.screenshot`
- `desktop.ocr`
- `desktop.active_window`
- `desktop.window_list`

Mouse, keyboard, and audio tools are opt-in gates:

- `DESKTOP_BRIDGE_ALLOW_CONTROL=1` enables `desktop.move`,
  `desktop.click`, `desktop.type`, and `desktop.hotkey`
- `DESKTOP_BRIDGE_ALLOWED_WINDOW_RE` can restrict control to window titles or
  metadata matching a regex such as `Discord|Chrome|Chromium`
- `DESKTOP_BRIDGE_ALLOW_AUDIO=1` enables `desktop.audio_capture`,
  `desktop.audio_play`, and `desktop.audio_transcribe`

The pod config includes the MCP server as `desktop_bridge`, but it is disabled
by default. Enable it only after `DESKTOP_BRIDGE_URL` and
`DESKTOP_BRIDGE_TOKEN` are available in the pod environment.

This is intentionally not a hidden remote-control channel. The desktop host
keeps the display/audio authority, the bridge requires a bearer token when
bound off loopback, and control/audio require explicit environment gates.

## Level-Up Plugin

`plugins/level-up/` is the runtime feedback plugin. Bootstrap copies it to:

```text
/opt/data/plugins/level-up/
```

It adds:

- recovery recipes for failed tool calls
- tool latency/result-size metrics
- escalation logs and optional escalation sinks
- session-end harvest proposals
- promotion into `MEMORY.md`, `USER.md`, `SOUL.md`, or Hindsight
- correction guard checks before risky tool calls
- TaskPacket delegation helpers
- LSP/code-intelligence tooling
- conservative self-review
- `level-up-ops` skill instructions

Detailed behavior is covered in [`docs/improvement-system.md`](improvement-system.md).

## Runtime-Control Plugin

`plugins/runtime-control/` provides deployment policy hooks and durable decision
notes. It is copied into:

```text
/opt/data/plugins/runtime-control/
```

Its purpose is operational control, not general product behavior. It helps keep
live-cluster actions inside local policy.

## Ops Runtime Dashboard

`plugins/ops-runtime/dashboard/` is a bundled dashboard extension. Its
`manifest.json` defines an "Ops Runtime" tab for operational status across:

- gateway runtime
- Kubernetes
- model backend
- MCP-like child processes
- runtime boundaries

This uses Hermes' dashboard plugin mechanism but the content is specific to the
evolved deployment.

## Admission Proxy

`deploy/k8s/llama-admission-proxy.py` fronts the host-side local model service
with an OpenAI-compatible API surface.

It exists because a single local inference slot can be tied up by a request
that is too large to complete usefully. The proxy should reject or mark
oversized requests early. Hermes remains responsible for transcript compaction
and retry because Hermes owns session state, memory flushes, and context
compression telemetry.

The live K8s deployment routes the gateway through this proxy by default.
Alternative endpoint shapes are documented in
[`docs/evolved-model-matrix.md`](evolved-model-matrix.md).

## HTUI Pulse And Pending Turns

The pod-backed HTUI is an operational surface for the shared Hermes instance.
It runs through the normal `ui-tui` Ink client and `tui_gateway` JSON-RPC
backend, but the evolved deployment adds two reliability features:

- Pulse observer: a `Ctrl+P` panel that shows live gateway events in a
  right-side column on wide terminals or a compact bottom drawer on narrower
  terminals. Rows use `[HH:MM]B| event text`, where `B` is the model/source
  badge (`L`, `Cl`, `Cu`, `K`, etc.) when known.
- Pending-turn recovery: a checkpoint written before `prompt.submit` starts so
  an interrupted rollout can replay the submitted prompt with run-ledger
  recovery context when the operator resumes the same session.

Runtime journals and checkpoints live under:

```text
/opt/data/observability/hermes-pulse.jsonl
/opt/data/observability/hermes-pulse-client.jsonl
/opt/data/observability/pending-turns/
```

Pulse is read-only. Pending-turn recovery is replay-with-recovery, not a
literal continuation of a partially completed model stream. The Pulse files are
compact event journals: server-side journaling excludes streaming token deltas,
and the client journal is reserved for client-synthesized gateway stderr,
protocol, and startup events.

## Improvement Helpers

These helpers are intentionally report-first or approval-gated:

- `hermes-self-improvement-scan.py` collects external signal.
- `hermes-introspection-scan.py` reviews Hermes' own behavior.
- `hermes-resource-review.py` reviews K3s requests, limits, restarts, and live
  usage.
- `hermes-self-edit.py` creates guarded self-improvement branches and refuses
  PRs outside `example-org/hermes-agent-private`.
- `edge-watch-mcp.py` exposes findings to sibling agents.
- `putter` gives the operator a manual low-risk idle-work loop.

The scheduled jobs collect evidence and write reports. They do not push,
deploy, merge, restart the live gateway, or mutate production.

## Research, Update, And Upgrade Cycles

The update/upgrade workflow is documented in
[`docs/research-update-cycles.md`](research-update-cycles.md).

That reference ties together edge-watch, upstream sync, research skills,
Putter, dependency review, provider/model route changes, Hindsight/memory
promotion, Kubernetes resource review, ConfigMap embed sync, and public mirror
publication.

The rule is evidence first, mutation later. Research may be broad; upgrades,
route changes, deploys, publishing, PRs, and live resource changes require
explicit approval and targeted validation.

## ConfigMap Embeds

Several deployment helpers are embedded into `deploy/k8s/configmap.yaml` for
bootstrap-time installation into `/opt/data`. Edit the standalone source files
first, then sync the ConfigMap:

```bash
python3 scripts/sync_configmap_embeds.py
python3 scripts/sync_configmap_embeds.py --check
```

The regression suite checks that embedded content stays byte-for-byte synced.

## Public Mirror

`scripts/publish_evolved_repo.sh` publishes a sanitized upstream-based tree to
`snapetech/hermes-agent-evolved`.

The public mirror is not a development target. It is rebuilt from upstream plus
a selected public-safe overlay. Private manifests, live hostnames, Discord IDs,
runner labels, secrets, and inherited upstream GitHub Actions workflows are
stripped or sanitized.

Self-improvement work lands in `example-org/hermes-agent-private`; the public mirror
is updated only through the publisher after private-repo changes pass scans.
