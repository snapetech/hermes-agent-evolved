# Public-Safe Hermes Kubernetes Deployment

This document describes the Hermes cluster deployment in a way that is safe to publish. It intentionally uses placeholders and generalized topology.

Related references:

- [Main deployment README](README.md) explains the private overlay structure and
  file inventory.
- [Public examples](public-examples/README.md) provide starter Kustomize
  profiles for minimal, Discord, and Hindsight reproductions.
- [Evolved tooling](../../docs/evolved-tooling.md) identifies custom and
  semi-custom pieces that differ from stock Hermes Agent.
- [Research/update cycles](../../docs/research-update-cycles.md) explains how
  upgrades, dependency reviews, upstream sync, resource review, and public
  publication are handled.
- [Improvement system](../../docs/improvement-system.md) documents edge-watch,
  internal introspection, putter, level-up, and guarded self-editing.
- [Reproducibility matrix](../../docs/reproducibility.md) separates published
  artifacts, templates, operator-provided secrets, and private runtime state.

## Overview

This deployment runs Hermes as a single persistent Kubernetes workload with:

- one PVC-backed Hermes home at `/opt/data`
- a custom image derived from upstream `nousresearch/hermes-agent`
- a host-side OpenAI-compatible inference endpoint reached from the pod through a local proxy
- Firecrawl as the web search/extraction backend
- optional Discord integration
- optional GitLab secret for cluster-local SSH/API access
- optional GitHub CLI token secret
- optional mirrored host SSH secret

The same Hermes home is shared by:

- the long-running messaging gateway
- the in-pod Hermes TUI

That makes multiple client surfaces operate on the same underlying agent state.

## Topology

Example topology:

- namespace: `hermes`
- deployment: `hermes-gateway`
- service/ingress: optional
- persistent volume claim: one PVC mounted at `/opt/data`
- inference backend: `http://<local-proxy>:8002/v1` inside the pod, forwarding to `http://<host-llm>:8001/v1`
- web backend: `http://<firecrawl-service>:3002`

## Image design

The custom image adds:

- CLI/system packages commonly needed by a self-operating agent
- passwordless `sudo` for the in-container `hermes` user
- runtime overlay files from the repo
- the Hermes TUI assets:
  - `ui-tui`
  - `tui_gateway`

This is important because in-pod TUI support is not just a config flag; the image must actually contain those assets.

## Persistent state model

The deployment expects Hermes state to live under `/opt/data`.

Persisted data includes:

- `config.yaml`
- `SOUL.md`
- memory files
- session history
- cron definitions and output
- structured memory database
- workspace files
- persistent Python venv
- persistent npm global tools

The public repo intentionally does not include live `/opt/data` contents such
as auth mirrors, kubeconfigs, session databases, request dumps, transcripts,
Pulse logs, Discord thread state, Hindsight runtime state, or private workspace
repos. Those files are either operator-provided secrets or private runtime
history, not reproducible source artifacts.

## Model strategy

Recommended baseline for this deployment shape:

- default model: `<primary-model>`
- optional compression/session-search model: `<aux-model-or-same-endpoint>`
- provider: `custom`
- backend: OpenAI-compatible host service, optionally fronted by a pod-local admission proxy

Why:

- this is a good quality/speed balance for a single-user agent workflow
- a host-side service keeps the pod simpler and lets the operator tune inference separately from the gateway

## Important config choices

The private/live overlay currently carries these non-default settings. Public
examples keep the same safety posture where it is useful, but use placeholders
for model endpoints, channel IDs, hostnames, and credentials.

- `agent.reasoning_effort: none`
- `compression.threshold: 0.15`
- `compression.target_ratio: 0.15`
- `compression.protect_last_n: 4`
- `streaming.enabled: true`
- `streaming.transport: edit`
- `display.tool_progress: off`
- `display.tool_progress_command: true`
- `display.interim_assistant_messages: false`
- `display.lifecycle_status_messages: false`
- `terminal.backend: local`
- `terminal.cwd: /opt/data/workspace`
- `approvals.mode: manual`
- `approvals.cron_mode: deny`
- `adaptive_fallback_routing.enabled: true`
- `adaptive_fallback_routing.free_first: true`
- `gateway.worktrees.enabled: true`
- `worktree: true`
- `checkpoints.enabled: true`

YOLO approvals are session-scoped opt-in via `/yolo`, not a global deployment
default. Cron jobs default to denied approvals unless explicitly configured
otherwise.

Memory strategy:

- keep built-in markdown memory very small
- use structured memory for durable facts
- avoid storing bulky artifacts in prompt-visible memory

Self-maintenance policy:

- file changes in any git repo must be committed before the agent reports the
  work as complete
- every Hermes-originated change should add a short review entry to
  `HERMES_CHANGELOG.md`
- low-risk maintenance may stay as a local commit
- runtime, deploy, auth, RBAC, sudo, secret, MCP, model-routing, memory,
  session, context-compression, public-mirror, refactor, failed, or untested
  changes should go through a PR against the private package repo
- branch pushes are allowed for PRs, but direct pushes to `main`, merges,
  deploys, and live service mutations require explicit operator approval

## Discord strategy

For a single-channel Discord deployment:

- use a bot token
- keep an explicit allowlist
- mark the main channel as free-response
- disable auto-threading
- explicitly mark the main channel as no-thread

Document with placeholders only:

- `DISCORD_BOT_TOKEN`
- `DISCORD_ALLOWED_USERS`
- `DISCORD_ALLOWED_CHANNELS`
- `DISCORD_HOME_CHANNEL`

## Build and deploy

Use a fresh image tag for each rollout.

```bash
IMAGE_TAG=hermes-agent-sudo:YYYYMMDD-1
docker build -t "$IMAGE_TAG" -f deploy/k8s/Dockerfile.sudo .
docker save "$IMAGE_TAG" | sudo k3s ctr images import -
```

Update both image references in the deployment:

- init container image
- main gateway container image

Apply:

```bash
kubectl apply -f deploy/k8s/configmap.yaml
kubectl apply -f deploy/k8s/deployment.yaml
kubectl -n hermes rollout restart deploy/hermes-gateway
kubectl -n hermes rollout status deploy/hermes-gateway
```

For a public-safe starter that avoids private cluster assumptions, use:

- `deploy/k8s/public-examples/minimal`
- `deploy/k8s/public-examples/discord`
- `deploy/k8s/public-examples/hindsight`

Before applying examples:

```bash
set -a
. deploy/k8s/public-examples/values.example.env
set +a

MODEL_BASE_URL=https://your-model-endpoint.example/v1 \
IMAGE_REF=registry.example.com/hermes-agent-sudo:tag \
deploy/k8s/check-public-prereqs.sh
```

After rollout:

```bash
deploy/k8s/smoke-public-deploy.sh
```

Or use the public-safe wrapper, which creates the API secret, patches the
minimal example in a temporary directory, applies it, and runs the smoke test:

```bash
cp deploy/k8s/public-examples/values.example.env deploy/k8s/public-examples/values.local.env
$EDITOR deploy/k8s/public-examples/values.local.env
deploy/k8s/reproduce-minimal.sh deploy/k8s/public-examples/values.local.env
```

Do not commit `values.local.env`.

## Secrets

Use placeholders in all published examples.

Examples:

```bash
kubectl -n hermes create secret generic hermes-api-server \
  --from-literal=API_SERVER_KEY='replace-me' \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n hermes create secret generic hermes-discord \
  --from-literal=DISCORD_BOT_TOKEN='replace-me' \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n hermes create secret generic hermes-gitlab \
  --from-file=id_ed25519=/secure/path/id_ed25519 \
  --from-file=id_ed25519.pub=/secure/path/id_ed25519.pub \
  --from-file=known_hosts=/secure/path/known_hosts \
  --from-literal=token='replace-me' \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n hermes create secret generic hermes-github \
  --from-literal=token='replace-me' \
  --from-file=config.yml=/secure/path/config.yml \
  --from-file=hosts.yml=/secure/path/hosts.yml \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n hermes create secret generic hermes-host-ssh \
  --from-file=config=/secure/path/ssh_config \
  --from-file=known_hosts=/secure/path/known_hosts \
  --from-file=id_ed25519=/secure/path/id_ed25519 \
  --from-file=id_ed25519.pub=/secure/path/id_ed25519.pub \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Validation

Minimum validation:

```bash
kubectl -n hermes get pods -l app=hermes-gateway -o wide
kubectl -n hermes exec deploy/hermes-gateway -c gateway -- sh -lc 'cat /opt/data/config.yaml | sed -n "1,120p"'
curl -fsS http://<hermes-host>/health
```

Drift validation:

```bash
python scripts/audit_live_reproducibility.py --output docs/reproducibility-live-audit.md
```

The audit compares the repo, live image refs, ConfigMap hash, persistent repo
checkout, cron seed names, and skill seed names. It does not export sessions,
logs, secrets, request dumps, auth mirrors, or private workspace contents.

TUI validation:

```bash
kubectl -n hermes exec deploy/hermes-gateway -c gateway -- sh -lc 'test -d /app/ui-tui && test -d /app/tui_gateway && echo ok'
kubectl -n hermes exec deploy/hermes-gateway -c gateway -- sh -lc 'cd /app && HERMES_HOME=/opt/data /app/.venv/bin/hermes --help | rg -- --tui'
```

## Publishing checklist

Before publishing:

- replace internal hostnames with examples
- replace real channel IDs and user IDs with placeholders
- replace private ingress hostnames with placeholders
- remove any private SSH identity naming or host-specific filenames
- remove auth mirrors, kubeconfigs, `.env`, `.netrc`, git credentials, request
  dumps, transcripts, session databases, Pulse logs, and Discord thread state
- keep the actual architectural decisions and tuning choices
- run the public mirror sanitizer and inspect any findings before pushing

## Minimum reproducible recipe

1. Build the custom image with `ui-tui` and `tui_gateway`.
2. Mount one PVC at `/opt/data`.
3. Point Hermes at an OpenAI-compatible model endpoint.
4. Point Hermes at Firecrawl if web search is needed.
5. Mount secrets for API/Discord/Git as needed.
6. Deploy the single `hermes-gateway` workload.
7. Verify both Discord and the in-pod TUI use the same `/opt/data`.

For model/backend choices, see `docs/evolved-model-matrix.md`. For keeping an
overlay aligned with Nous upstream, see `docs/upstream-sync.md`.
