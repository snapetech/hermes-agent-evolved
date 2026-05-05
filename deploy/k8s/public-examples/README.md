# Public Kubernetes Examples

These examples are public-safe starter profiles for reproducing the evolved
Hermes deployment shape without private hostnames, runner labels, Discord IDs,
SSH identities, or internal service IPs.

Use these examples when starting from a public clone. Use the top-level
`deploy/k8s/*.yaml` bundle only when you are operating the private/live cluster
that those manifests describe.

The examples are intentionally not byte-for-byte copies of live `/opt/data`.
They reproduce the architecture, conservative runtime posture, and validation
path while leaving credentials, channel IDs, session history, auth mirrors, and
private workspace state to the operator.

## Profiles

| Profile | Path | Purpose |
| --- | --- | --- |
| Minimal | `minimal/` | One PVC-backed Hermes gateway, API server, in-pod TUI, external OpenAI-compatible model endpoint. No Discord, no Hindsight, no admission proxy. |
| Discord | [`discord/`](discord/README.md) | Kustomize overlay that adds Discord token/channel environment variables to the minimal profile. |
| Hindsight | [`hindsight/`](hindsight/README.md) | Public-safe Hindsight config template and integration notes for structured memory. |

## Values Template

Start with the public-safe environment template:

```bash
cp deploy/k8s/public-examples/values.example.env deploy/k8s/public-examples/values.local.env
$EDITOR deploy/k8s/public-examples/values.local.env
set -a
. deploy/k8s/public-examples/values.local.env
set +a
```

Keep `values.local.env` untracked. Put real API keys and tokens in Kubernetes
Secrets or a secret manager, not in the values file.

## Minimal Quickstart

1. Build and publish an image:

   ```bash
   IMAGE_REF=registry.example.com/hermes-agent-sudo:dev
   docker build -t "$IMAGE_REF" -f deploy/k8s/Dockerfile.sudo .
   docker push "$IMAGE_REF"
   ```

2. Create the API key secret:

   ```bash
   kubectl create namespace hermes --dry-run=client -o yaml | kubectl apply -f -
   kubectl -n hermes create secret generic hermes-api-server \
     --from-literal=API_SERVER_KEY='replace-with-random-token' \
     --dry-run=client -o yaml | kubectl apply -f -
   ```

3. Edit `minimal/configmap.yaml`:

   - `model.default`
   - `model.base_url`
   - `model.context_length`
   - `custom_providers[0].models`

4. Edit `minimal/deployment.yaml` and replace
   `registry.example.com/hermes-agent-sudo:replace-me` with your image.

5. Validate prerequisites:

   ```bash
   set -a
   . deploy/k8s/public-examples/values.local.env
   set +a
   MODEL_BASE_URL=https://your-model-endpoint.example/v1 \
   IMAGE_REF="$IMAGE_REF" \
   deploy/k8s/check-public-prereqs.sh
   ```

6. Apply:

   ```bash
   kubectl apply -k deploy/k8s/public-examples/minimal
   kubectl -n hermes rollout status deploy/hermes-gateway
   ```

   Or use the wrapper, which creates the API secret, patches the minimal
   example in a temporary directory, applies it, waits for rollout, and runs
   the smoke test:

   ```bash
   deploy/k8s/reproduce-minimal.sh deploy/k8s/public-examples/values.local.env
   ```

## Optional Seeds

The live private PVC is not exported, but public-safe starter state exists:

- `deploy/k8s/cron-seed.example.json`
- `deploy/k8s/skills.lock.example.json`
- `deploy/k8s/runtime-packages.lock.example.json`
- `deploy/k8s/memory.seed.example.md`

Use these only as templates. They avoid secrets, channel IDs, session history,
auth mirrors, and private workspace state.

7. Smoke test:

   ```bash
   deploy/k8s/smoke-public-deploy.sh
   ```

## Adding Discord

Create the Discord secret and edit the channel/user placeholders:

```bash
kubectl -n hermes create secret generic hermes-discord \
  --from-literal=DISCORD_BOT_TOKEN='replace-with-bot-token' \
  --dry-run=client -o yaml | kubectl apply -f -
```

Then apply:

```bash
kubectl apply -k deploy/k8s/public-examples/discord
```

## Adding Hindsight

Start from `hindsight/hindsight-config.example.json`. Replace the placeholder
model and embedding endpoints, deploy your Hindsight service, then set
`memory.provider: hindsight` in the Hermes config.

The example intentionally does not include live database credentials. Use
Kubernetes Secrets or your platform secret manager for Postgres/API credentials.
