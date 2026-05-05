# Hermes Agent Evolved Reproducibility Audit

This audit describes what a public user needs in order to clone the public
repository and reproduce the evolved deployment shape. It is written for both
humans and LLM agents that may be assisting with setup.

## Reproducibility Goal

A reproducer should be able to:

1. Clone a public repo.
2. Build the derived Hermes image.
3. Deploy one persistent Kubernetes Hermes gateway.
4. Point it at their own OpenAI-compatible model endpoint.
5. Optionally attach Firecrawl, Discord, GitHub/GitLab auth, Hindsight, and
   sibling coding-agent CLIs.
6. Verify that gateway and in-pod TUI share the same `/opt/data` state.

The target is reproducible architecture and workflow, not byte-for-byte
reproduction of a private cluster.

## Current Status

| Item | Status | Notes |
| --- | --- | --- |
| Upstream base is explicit | Good | Remotes and publish script identify `NousResearch/hermes-agent` as the base. |
| Fork/evolved purpose is documented | Good | README and deployment docs explain the overlay relationship. |
| Main deployment guide exists | Good | `deploy/k8s/README.md` covers the private package deployment. |
| Public-safe deployment guide exists | Good | `deploy/k8s/PUBLIC-DEPLOY.md` uses placeholders and a minimum recipe. |
| Reproducibility matrix exists | Good | `docs/reproducibility.md` separates checked-in artifacts, templates, operator-provided inputs, and private runtime state. |
| Decision rationale is centralized | Improved | This audit adds `docs/evolved-decisions.md`. |
| Custom tooling and update cycles are documented | Good | `docs/evolved-tooling.md` and `docs/research-update-cycles.md` explain overlay tooling and evidence-to-change workflows. |
| Public mirror publication path exists | Good | `scripts/publish_evolved_repo.sh` builds upstream plus sanitized overlay. |
| Sanitization scans exist | Good | Publisher scans for private markers and high-confidence secrets. |
| Exact private cluster reproduction | Not intended | Hostnames, tokens, runner labels, SSH identities, and Discord IDs must remain private. |
| Public starter manifests | Closed | `deploy/k8s/public-examples/minimal` provides a placeholder profile that avoids private cluster assumptions. |
| Optional integration profiles | Closed | `deploy/k8s/public-examples/discord` and `deploy/k8s/public-examples/hindsight` document optional add-ons. |
| Hardware/model requirements | Closed | `docs/evolved-model-matrix.md` separates external API, host-side local inference, in-cluster service, and router paths. |
| Secrets contract | Closed | `deploy/k8s/check-public-prereqs.sh` validates required and optional public reproduction inputs. |
| Public values template | Closed | `deploy/k8s/public-examples/values.example.env` lists the environment values used by prereq and smoke scripts. |
| Validation/results smoke | Closed | `deploy/k8s/smoke-public-deploy.sh` records reproducible health, TUI, state, model, and API checks. |
| Upstream sync procedure | Closed | `docs/upstream-sync.md` documents report, merge, test, and publication steps. |
| Exact live tuning snapshot | Partial by design | Current conservative defaults are documented, but private IDs, auth mirrors, runtime DBs, transcripts, logs, and PVC state are intentionally excluded. |

## Public Reproduction Path

### 1. Clone

```bash
git clone https://github.com/<org>/hermes-agent-evolved.git
cd hermes-agent-evolved
```

For local development from the private package repo, keep upstream configured
read-only:

```bash
git remote add upstream https://github.com/NousResearch/hermes-agent.git
git remote set-url --push upstream DISABLED
```

### 2. Choose Runtime Mode

There are two supported paths:

- upstream-style local Hermes install for laptop or shell use
- evolved Kubernetes deployment for persistent cluster use

Do not mix them accidentally. The evolved deployment path expects Kubernetes,
a PVC, a custom image, a model endpoint, and secrets supplied by the operator.

### 3. Prepare Required Infrastructure

Minimum:

- Kubernetes cluster with `kubectl` access
- a namespace such as `hermes`
- one writable persistent volume mounted at `/opt/data`
- container image build and distribution path
- OpenAI-compatible model endpoint reachable from the pod

Optional but commonly used:

- Firecrawl service
- Discord bot and allowlist
- GitHub CLI token secret
- GitLab SSH/API secret
- mirrored host SSH secret
- Hindsight structured memory service
- self-hosted GitHub Actions runner for private deploy automation

### 4. Build Image

```bash
IMAGE_TAG=hermes-agent-sudo:$(date -u +%Y%m%d)-1
docker build -t "$IMAGE_TAG" -f deploy/k8s/Dockerfile.sudo .
```

For k3s without a registry:

```bash
docker save "$IMAGE_TAG" | sudo k3s ctr images import -
```

For a normal cluster, push to your registry and update manifests to use that
registry image.

### 5. Configure Secrets

Use Kubernetes Secrets or your secret manager. Never commit real values.

Minimum examples are in `deploy/k8s/PUBLIC-DEPLOY.md`. Replace every
`replace-me`, `<host>`, `<channel-id>`, and `<user-id>` placeholder.
Starter Kustomize profiles are indexed in
[`deploy/k8s/public-examples/README.md`](../deploy/k8s/public-examples/README.md).
Use
[`deploy/k8s/public-examples/values.example.env`](../deploy/k8s/public-examples/values.example.env)
as the public-safe values template for local prereq and smoke runs.

For a no-Discord reproduction, omit the Discord secret and run only API/TUI
surfaces. For a no-Firecrawl reproduction, disable web search or point Hermes
at another supported backend.

### 6. Configure Model Endpoint

The evolved deployment assumes an OpenAI-compatible endpoint. The current live
shape uses a pod-local proxy that forwards to a host-side model service, but a
public reproducer can use any endpoint with the same API shape.

Required config concepts:

- `model.provider: custom`
- `model.base_url: http://<your-endpoint>/v1`
- `model.default: <your-model-name>`
- `model.context_length: <served-context-length>`

Do not advertise a context length lower than Hermes's minimum or higher than
the backend can actually serve.

### 7. Apply Manifests

Use the public-safe example profile first:

```bash
kubectl apply -k deploy/k8s/public-examples/minimal
kubectl -n hermes rollout status deploy/hermes-gateway
```

If using `kustomize`, verify image tags and any local patches before applying:

```bash
kubectl kustomize deploy/k8s/public-examples/minimal | sed -n '1,160p'
```

### 8. Validate

```bash
kubectl -n hermes get pods -l app=hermes-gateway -o wide
kubectl -n hermes logs deploy/hermes-gateway -c gateway --tail=120
kubectl -n hermes exec deploy/hermes-gateway -c gateway -- sh -lc 'test -d /app/ui-tui && test -d /app/tui_gateway && echo tui-assets-ok'
kubectl -n hermes exec deploy/hermes-gateway -c gateway -- sh -lc 'cd /app && HERMES_HOME=/opt/data /app/.venv/bin/hermes --help | rg -- --tui'
```

If an HTTP service is exposed:

```bash
curl -fsS http://<your-hermes-host>/health
```

### 9. Validate Shared State

Run the gateway and in-pod TUI against the same `HERMES_HOME`:

```bash
kubectl -n hermes exec -it deploy/hermes-gateway -c gateway -- sh -lc 'cd /app && HERMES_HOME=/opt/data /app/.venv/bin/hermes --tui --continue'
```

Create a session or memory item from one surface and confirm it is visible from
the other.

## Former Gaps And Artifacts

### Public Overlay Scope

The public evolved mirror now carries the decision and reproducibility docs in
addition to the public deployment guide.

Artifacts:

- `docs/reproducibility.md`
- `docs/evolved-decisions.md`
- `docs/evolved-tooling.md`
- `docs/research-update-cycles.md`
- `docs/reproducibility-audit.md`
- `deploy/k8s/PUBLIC-DEPLOY.md`

### Public Manifests

The private manifests remain available as the live deployment bundle, and public
users now have separate placeholder profiles.

Artifacts:

- `deploy/k8s/public-examples/minimal`
- `deploy/k8s/public-examples/discord`
- `deploy/k8s/public-examples/hindsight`

### Hardware And Model Matrix

The model matrix now documents external API, host-side local inference,
in-cluster model service, and router/proxy service shapes.

Artifact:

- `docs/evolved-model-matrix.md`

### Machine-Checkable Secrets Contract

The prereq script checks cluster access, namespace, StorageClass visibility,
required API secret, optional Discord secret, image placeholder status, model
endpoint, and optional Firecrawl endpoint.

Artifact:

- `deploy/k8s/check-public-prereqs.sh`

### Reproducible Smoke Results

The smoke script does not claim model quality. It gives a repeatable operational
result for rollout health, TUI availability, persistent state, model endpoint
reachability, and API reachability.

Artifact:

- `deploy/k8s/smoke-public-deploy.sh`

### Upstream Sync Procedure

The sync procedure is now documented for private package repos and public mirror
publication.

Artifacts:

- `docs/upstream-sync.md`
- `scripts/upstream_sync_report.sh`

## Agent-Assisted Setup Instructions

If an LLM agent is helping a user reproduce this deployment, it should follow
these rules:

1. Ask for the target runtime first: local upstream install or evolved
   Kubernetes deployment.
2. Never invent credentials, hostnames, Discord IDs, or model URLs.
3. Keep `NousResearch/hermes-agent` as the upstream base.
4. Use placeholder values in committed files.
5. Put real values in Kubernetes Secrets, environment variables, or local
   untracked files.
6. Verify the model endpoint with `/v1/models` or a small chat completion
   before deploying Hermes.
7. Verify image tags in both init and gateway containers.
8. Confirm `/opt/data` is persistent before starting real work.
9. Run the TUI validation commands after rollout.
10. Record exact upstream SHA, overlay SHA, image tag, model endpoint type, and
    config hash in any reproduction report.

## Minimum Reproduction Report Template

Use this template when someone claims they reproduced the deployment:

```text
upstream_repo: NousResearch/hermes-agent
upstream_sha:
evolved_repo:
evolved_sha:
image:
kubernetes_distribution:
storage_class:
model_provider:
model_name:
model_base_url_shape: local-proxy | host-service | external-api
served_context_length:
firecrawl_enabled: yes | no
discord_enabled: yes | no
hindsight_enabled: yes | no
gateway_health: pass | fail
tui_assets: pass | fail
tui_shared_state: pass | fail
memory_smoke: pass | fail | not-run
web_smoke: pass | fail | not-run
cron_list: pass | fail
notes:
```

## Definition Of Done

Reproducibility is good enough for public users when:

- a fresh clone can build the image
- a placeholder-based manifest path exists
- required and optional secrets are explicit
- the model endpoint contract is explicit
- validation commands are copy-pasteable
- the public mirror includes the decision and reproducibility docs
- sanitizer scans pass before publication
- upstream remains clearly identified as the primary base
