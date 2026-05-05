#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
VALUES="${1:-$ROOT/deploy/k8s/public-examples/values.local.env}"

if [ ! -f "$VALUES" ]; then
  cat >&2 <<EOF
missing values file: $VALUES

Create one from the public-safe template:
  cp deploy/k8s/public-examples/values.example.env deploy/k8s/public-examples/values.local.env
  \$EDITOR deploy/k8s/public-examples/values.local.env
EOF
  exit 2
fi

set -a
. "$VALUES"
set +a

: "${NAMESPACE:=hermes}"
: "${IMAGE_REF:?set IMAGE_REF in $VALUES}"
: "${MODEL_BASE_URL:?set MODEL_BASE_URL in $VALUES}"
: "${API_KEY:?set API_KEY in $VALUES or create the secret yourself}"

kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$NAMESPACE" create secret generic "${API_SECRET:-hermes-api-server}" \
  --from-literal=API_SERVER_KEY="$API_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

MODEL_BASE_URL="$MODEL_BASE_URL" IMAGE_REF="$IMAGE_REF" \
  "$ROOT/deploy/k8s/check-public-prereqs.sh"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
cp -R "$ROOT/deploy/k8s/public-examples/minimal/." "$tmp/"

python3 - "$tmp" "$IMAGE_REF" "$MODEL_BASE_URL" "${MODEL_NAME:-replace-model-name}" "${MODEL_CONTEXT_LENGTH:-65536}" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
image, base_url, model, ctx = sys.argv[2:6]
dep = root / "deployment.yaml"
cfg = root / "configmap.yaml"
dep.write_text(dep.read_text().replace("registry.example.com/hermes-agent-sudo:replace-me", image), encoding="utf-8")
text = cfg.read_text(encoding="utf-8")
text = text.replace("https://model-endpoint.example/v1", base_url)
text = text.replace("replace-model-name", model)
text = text.replace("context_length: 65536", f"context_length: {ctx}")
cfg.write_text(text, encoding="utf-8")
PY

kubectl apply -k "$tmp"
kubectl -n "$NAMESPACE" rollout status deploy/"${DEPLOYMENT:-hermes-gateway}" --timeout=180s

RUN_MODEL_CHECK="${RUN_MODEL_CHECK:-1}" "$ROOT/deploy/k8s/smoke-public-deploy.sh"
