# Hermes Evolved Reproducibility Matrix

This document answers a narrow question: what does the repo publish, what must
an operator provide, and what is intentionally private runtime state?

The public reproduction target is architecture and operating behavior, not a
byte-for-byte clone of a private Hermes instance.

## Reproducibility Levels

| Level | Meaning | Expected outcome |
| --- | --- | --- |
| Source reproducible | Code, manifests, docs, skills, and scripts are checked in. | A reader can inspect the design and build the image. |
| Template reproducible | Public-safe examples exist with placeholders. | A reader can fill their own model endpoint and secrets. |
| Operator reproducible | Requires user-owned infrastructure or credentials. | A reader can run the same shape with their own accounts. |
| Private runtime state | Live state, logs, credentials, sessions, and memories. | Not published and not required for reproduction. |

## Published In Repo

| Area | Examples | Reproduction status |
| --- | --- | --- |
| Upstream base | `NousResearch/hermes-agent` remote guidance and upstream-sync docs | Source reproducible |
| Kubernetes overlay | `deploy/k8s/configmap.yaml`, `deployment.yaml`, `hindsight.yaml`, public examples | Source and template reproducible |
| Runtime image | `deploy/k8s/Dockerfile.sudo` | Source reproducible |
| Bootstrap | `bootstrap-runtime.sh` embedded in ConfigMap, helper scripts under `deploy/k8s/` | Source reproducible |
| HTUI/Pulse | `ui-tui/`, `tui_gateway/`, Pulse docs in README | Source reproducible |
| Edge-Watch/introspection | `deploy/k8s/EDGE-WATCH.md`, `edge-watch-mcp.py`, scan scripts | Source reproducible |
| Desktop bridge MCP | `deploy/k8s/desktop-bridge-mcp.py` and docs | Source reproducible; desktop host setup is operator-provided |
| Skills | `skills/autonomous-ai-agents/putter`, `skills/autonomous-ai-agents/hermes-introspection`, `skills/research/research-best-practices` | Source reproducible |
| Hindsight integration | Hindsight manifests and public example config | Template reproducible |
| Public starter manifests | `deploy/k8s/public-examples/minimal`, `discord`, `hindsight` | Template reproducible |
| Validation | `check-public-prereqs.sh`, `smoke-public-deploy.sh` | Operator reproducible |
| Change policy | `SOUL.md` in ConfigMap, `HERMES_CHANGELOG.md`, README policy | Source reproducible |

## Operator-Provided Inputs

These are required or optional inputs a reproducer must provide locally. They
must not be committed with real values.

| Input | Why it is needed | Where to place it |
| --- | --- | --- |
| OpenAI-compatible model endpoint | Hermes needs a model backend. | ConfigMap placeholder or secret-managed config |
| Model name and served context length | Hermes needs to size prompts and compression. | ConfigMap placeholder |
| API server key | Protects the Hermes API surface. | `hermes-api-server` Kubernetes Secret |
| Container image ref | Cluster needs a pullable image. | Kustomize image override or deployment patch |
| Discord bot token and IDs | Needed only for Discord operation. | `hermes-discord` Secret plus placeholder config |
| GitHub token/config | Needed only for GitHub CLI/API work. | `hermes-github` Secret or secret manager |
| GitLab SSH/API auth | Needed only for GitLab mirrors and private repos. | `hermes-gitlab` Secret |
| Kubeconfig/RBAC | Needed only if Hermes should inspect or operate the cluster. | Kubernetes ServiceAccount/RBAC or mounted secret |
| Firecrawl URL/key | Needed only for Firecrawl-backed web extraction. | Config placeholder plus Secret if keyed |
| Hindsight database/API credentials | Needed only for structured memory. | Hindsight Secret/config |
| Desktop bridge URL/token | Needed only if Hermes should observe or control an operator desktop. | Pod env/Secret plus a local desktop bridge process |
| TLS/DNS/Ingress | Environment-specific exposure. | Cluster ingress/cert manager config |

The public template is
[`deploy/k8s/public-examples/values.example.env`](../deploy/k8s/public-examples/values.example.env).
Copy it to an untracked local file before filling in real values.

## Intentionally Private Runtime State

The following should stay out of both public and private source history unless
represented only as placeholders or examples:

| Runtime state | Reason |
| --- | --- |
| `.env`, `auth.json`, `.netrc`, git credentials, GitHub/PAT files | Credentials |
| kubeconfigs and private SSH keys | Cluster and host access |
| session databases, transcripts, request dumps, trajectory artifacts | User/private conversation history |
| Hindsight runtime DBs and private config | Durable private memory and credentials |
| Pulse logs and gateway stderr journals | Operational history, possible sensitive tool output |
| Discord thread/channel state | Private channel metadata and conversation routing |
| cron runtime output and job state | Private operational history |
| private workspace repos under `/opt/data/workspace` | Unrelated private projects |
| model weights and host-side service state | Large, host-specific, and often license-bound |

## Cold-Start Path

A capable reproducer should be able to get a minimal cluster-hosted Hermes in
this order:

1. Clone the public evolved repo.
2. Build and publish the derived image.
3. Copy `deploy/k8s/public-examples/values.example.env` to an untracked local
   values file and fill in their own endpoint/image values.
4. Create the `hermes-api-server` Secret.
5. Edit `deploy/k8s/public-examples/minimal/configmap.yaml` for their model.
6. Apply `deploy/k8s/public-examples/minimal`.
7. Run `deploy/k8s/check-public-prereqs.sh`.
8. Run `deploy/k8s/smoke-public-deploy.sh`.
9. Add Discord, Hindsight, GitHub/GitLab, Firecrawl, or host-side local
   inference only after the minimal profile is healthy.

For a guided public-safe wrapper around steps 3-8:

```bash
cp deploy/k8s/public-examples/values.example.env deploy/k8s/public-examples/values.local.env
$EDITOR deploy/k8s/public-examples/values.local.env
deploy/k8s/reproduce-minimal.sh deploy/k8s/public-examples/values.local.env
```

Keep `values.local.env` untracked and put real credentials in Kubernetes
Secrets or a secret manager.

## Repo-Backed Seeds

The live PVC is private state, but several operational behaviors can be seeded
without exporting secrets or personal data:

| Seed artifact | Purpose |
| --- | --- |
| `deploy/k8s/cron-seed.example.json` | Public-safe cron job templates. |
| `deploy/k8s/skills.lock.example.json` | Repo-backed skill install manifest. |
| `deploy/k8s/runtime-packages.lock.example.json` | References package manifests and the drift checker. |
| `deploy/k8s/memory.seed.example.md` | Minimal non-private prompt-visible memory starter. |

Seed commands:

```bash
python scripts/seed_cron_jobs.py --manifest deploy/k8s/cron-seed.example.json --dry-run
python scripts/install_skill_manifest.py --manifest deploy/k8s/skills.lock.example.json --dry-run
python scripts/check_runtime_package_drift.py --json
```

## Drift Audits

Use the live reproducibility audit to compare a checked-out repo to the running
pod without dumping private state:

```bash
python scripts/audit_live_reproducibility.py --output docs/reproducibility-live-audit.md
```

It records commit/config hashes, image refs, persistent repo drift, seeded cron
and skill drift, and redacted findings. It intentionally does not export live
sessions, logs, secrets, auth mirrors, request dumps, or workspace contents.

## Current Honest Rating

| Pillar | Rating | Why |
| --- | --- | --- |
| Architecture reproducibility | 7/10 | The repo contains the main deployment shape, docs, scripts, and examples. |
| Exact behavior reproducibility | 5/10 | Behavior depends on operator secrets, model endpoint behavior, and private state. |
| Random cold-start friendliness | 5/10 | Public examples and a wrapper exist; a random user still needs a model endpoint, image registry, and secrets. |

## Remaining Gaps

| Gap | Impact | Next improvement |
| --- | --- | --- |
| No full opinionated fresh-cluster installer | The wrapper covers the minimal public path, but registry publishing and optional integrations still require operator choices. | Add a scripted `make public-smoke` or equivalent entrypoint around the existing wrapper. |
| Host-side local inference is documented but not fully automated | Local GGUF reproduction is still operator-heavy. | Add systemd and model-service examples. |
| Public examples are minimal by design | They do not reproduce every private integration. | Add optional overlays only when they can stay public-safe. |
| Live PVC state is intentionally excluded | A clone starts empty. | Provide seedable examples for skills/cron/reporting without private data. |
| Public mirror safety depends on sanitizer discipline | Publication can regress if checks are skipped. | Keep sanitizer in the publish path and add CI coverage. |
| Persistent pod repo can drift from deployed image | Repo-backed tools may edit or audit stale source. | Use `audit_live_reproducibility.py` and BOOT warnings; sync only through approved deploy flow. |

## Publication Rule

Publish decisions, patterns, source, templates, and validation commands.
Do not publish live secrets, auth mirrors, private state, session history,
workspace repos, operational logs, or identity-bearing channel/user IDs.
