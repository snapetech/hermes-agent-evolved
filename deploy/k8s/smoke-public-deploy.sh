#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-hermes}"
DEPLOYMENT="${DEPLOYMENT:-hermes-gateway}"
CONTAINER="${CONTAINER:-gateway}"
SERVICE="${SERVICE:-hermes-gateway}"
MODEL_BASE_URL="${MODEL_BASE_URL:-}"
API_KEY="${API_KEY:-}"
LOCAL_PORT="${LOCAL_PORT:-18642}"
RUN_MODEL_CHECK="${RUN_MODEL_CHECK:-1}"

errors=0
warnings=0
port_forward_pid=""

ok() {
  printf 'ok: %s\n' "$*"
}

warn() {
  warnings=$((warnings + 1))
  printf 'warn: %s\n' "$*" >&2
}

fail() {
  errors=$((errors + 1))
  printf 'fail: %s\n' "$*" >&2
}

cleanup() {
  if [[ -n "$port_forward_pid" ]]; then
    kill "$port_forward_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

need_cmd() {
  if command -v "$1" >/dev/null 2>&1; then
    ok "found $1"
  else
    fail "missing command: $1"
  fi
}

need_cmd kubectl
need_cmd sed

if ! command -v curl >/dev/null 2>&1; then
  warn "curl not found; HTTP checks will be skipped"
fi

if [[ "$errors" -eq 0 ]]; then
  kubectl -n "$NAMESPACE" rollout status "deploy/$DEPLOYMENT" --timeout=180s
  ok "deployment rollout is complete"

  pod="$(kubectl -n "$NAMESPACE" get pods -l app="$DEPLOYMENT" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
  if [[ -z "$pod" ]]; then
    pod="$(kubectl -n "$NAMESPACE" get pods -l app=hermes-gateway -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
  fi
  if [[ -z "$pod" ]]; then
    fail "could not find gateway pod"
  else
    ok "gateway pod: $pod"
  fi
fi

if [[ "$errors" -eq 0 ]]; then
  kubectl -n "$NAMESPACE" exec "$pod" -c "$CONTAINER" -- sh -lc 'test -d /app/ui-tui && test -d /app/tui_gateway'
  ok "TUI assets exist in image"

  kubectl -n "$NAMESPACE" exec "$pod" -c "$CONTAINER" -- sh -lc 'cd /app && HERMES_HOME=/opt/data /app/.venv/bin/hermes --help | grep -q -- --tui'
  ok "Hermes CLI exposes --tui"

  kubectl -n "$NAMESPACE" exec "$pod" -c "$CONTAINER" -- sh -lc 'test -f /opt/data/config.yaml && test -d /opt/data/workspace && test -d /opt/data/sessions'
  ok "persistent Hermes home has expected files/directories"
fi

if [[ "$errors" -eq 0 && -n "$(command -v curl || true)" ]]; then
  kubectl -n "$NAMESPACE" port-forward "svc/$SERVICE" "$LOCAL_PORT:8642" >/tmp/hermes-port-forward.log 2>&1 &
  port_forward_pid="$!"
  sleep 3
  if curl -fsS --max-time 10 "http://127.0.0.1:$LOCAL_PORT/health" >/dev/null; then
    ok "gateway health endpoint responds through port-forward"
  else
    warn "gateway health endpoint did not respond through port-forward"
  fi
fi

if [[ "$RUN_MODEL_CHECK" == "1" ]]; then
  if [[ -z "$MODEL_BASE_URL" ]]; then
    warn "MODEL_BASE_URL not set; skipping model endpoint smoke"
  elif [[ -n "$(command -v curl || true)" ]]; then
    if curl -fsS --max-time 10 "$MODEL_BASE_URL/models" >/dev/null; then
      ok "model endpoint /models responds"
    else
      warn "model endpoint /models did not respond; run a chat-completions probe manually"
    fi
  fi
fi

if [[ -n "$API_KEY" && -n "$(command -v curl || true)" ]]; then
  if curl -fsS --max-time 10 \
    -H "Authorization: Bearer $API_KEY" \
    "http://127.0.0.1:$LOCAL_PORT/v1/models" >/dev/null; then
    ok "Hermes OpenAI-compatible /v1/models responds"
  else
    warn "Hermes /v1/models check failed; verify API key and API server route"
  fi
else
  warn "API_KEY not set; skipping authenticated Hermes API check"
fi

if [[ "$errors" -gt 0 ]]; then
  printf '\nSmoke test failed with %d blocker(s), %d warning(s).\n' "$errors" "$warnings" >&2
  exit 1
fi

printf '\nSmoke test passed with %d warning(s).\n' "$warnings"

