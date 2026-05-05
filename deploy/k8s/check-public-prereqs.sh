#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-hermes}"
API_SECRET="${API_SECRET:-hermes-api-server}"
DISCORD_SECRET="${DISCORD_SECRET:-hermes-discord}"
MODEL_BASE_URL="${MODEL_BASE_URL:-}"
IMAGE_REF="${IMAGE_REF:-}"
REQUIRE_DISCORD="${REQUIRE_DISCORD:-0}"
REQUIRE_FIRECRAWL="${REQUIRE_FIRECRAWL:-0}"
FIRECRAWL_API_URL="${FIRECRAWL_API_URL:-}"
SKIP_MODEL_CHECK="${SKIP_MODEL_CHECK:-0}"
STATIC_ONLY="${STATIC_ONLY:-0}"

errors=0
warnings=0

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

need_cmd() {
  if command -v "$1" >/dev/null 2>&1; then
    ok "found $1"
  else
    fail "missing command: $1"
  fi
}

need_cmd kubectl
need_cmd sed

if command -v curl >/dev/null 2>&1; then
  ok "found curl"
else
  warn "curl not found; endpoint checks will be skipped"
fi

if [[ "$errors" -eq 0 ]]; then
  if kubectl version --client >/dev/null 2>&1; then
    ok "kubectl client works"
  else
    fail "kubectl client is not usable"
  fi

  if kubectl cluster-info >/dev/null 2>&1; then
    ok "kubectl can reach a cluster"
  else
    fail "kubectl cannot reach a cluster"
  fi
fi

if [[ "$errors" -eq 0 ]]; then
  if kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
    ok "namespace exists: $NAMESPACE"
  else
    warn "namespace does not exist yet: $NAMESPACE; examples can create it"
  fi

  if kubectl get storageclass >/dev/null 2>&1; then
    if [[ -n "$(kubectl get storageclass --no-headers 2>/dev/null | sed -n '1p')" ]]; then
      ok "at least one StorageClass is available"
    else
      warn "no StorageClass found; create a PV/PVC plan before applying examples"
    fi
  else
    warn "could not list StorageClasses; verify PVC provisioning manually"
  fi

  if kubectl -n "$NAMESPACE" get secret "$API_SECRET" >/dev/null 2>&1; then
    ok "API secret exists: $API_SECRET"
  else
    fail "missing API secret: kubectl -n $NAMESPACE create secret generic $API_SECRET --from-literal=API_SERVER_KEY=replace-with-random-token"
  fi

  if [[ "$REQUIRE_DISCORD" == "1" ]]; then
    if kubectl -n "$NAMESPACE" get secret "$DISCORD_SECRET" >/dev/null 2>&1; then
      ok "Discord secret exists: $DISCORD_SECRET"
    else
      fail "missing Discord secret: $DISCORD_SECRET"
    fi
  else
    if kubectl -n "$NAMESPACE" get secret "$DISCORD_SECRET" >/dev/null 2>&1; then
      ok "optional Discord secret exists: $DISCORD_SECRET"
    else
      warn "optional Discord secret not found; fine for minimal/API-only reproduction"
    fi
  fi
fi

if [[ -n "$IMAGE_REF" ]]; then
  ok "IMAGE_REF set: $IMAGE_REF"
  if [[ "$IMAGE_REF" == *replace-me* || "$IMAGE_REF" == registry.example.com/* ]]; then
    fail "IMAGE_REF still looks like a placeholder"
  fi
else
  warn "IMAGE_REF is not set; set it to the image used in your manifests"
fi

if [[ "$STATIC_ONLY" == "1" ]]; then
  warn "STATIC_ONLY=1; skipping model endpoint requirement"
elif [[ -n "$MODEL_BASE_URL" ]]; then
  ok "MODEL_BASE_URL set: $MODEL_BASE_URL"
  if [[ "$MODEL_BASE_URL" == *example* || "$MODEL_BASE_URL" == *replace* ]]; then
    fail "MODEL_BASE_URL still looks like a placeholder"
  elif [[ "$SKIP_MODEL_CHECK" != "1" && -n "$(command -v curl || true)" ]]; then
    if curl -fsS --max-time 10 "$MODEL_BASE_URL/models" >/dev/null; then
      ok "model endpoint responds at /models"
    else
      warn "model endpoint did not respond at /models; verify it supports OpenAI-compatible chat completions"
    fi
  fi
else
  fail "MODEL_BASE_URL is required; set STATIC_ONLY=1 for static manifest checks only"
fi

if [[ "$REQUIRE_FIRECRAWL" == "1" ]]; then
  if [[ -z "$FIRECRAWL_API_URL" ]]; then
    fail "FIRECRAWL_API_URL is required when REQUIRE_FIRECRAWL=1"
  elif [[ "$FIRECRAWL_API_URL" == *example* || "$FIRECRAWL_API_URL" == *replace* ]]; then
    fail "FIRECRAWL_API_URL still looks like a placeholder"
  elif [[ -n "$(command -v curl || true)" ]]; then
    if curl -fsS --max-time 10 "$FIRECRAWL_API_URL" >/dev/null; then
      ok "Firecrawl URL responds"
    else
      warn "Firecrawl URL did not respond to a basic GET; verify service path manually"
    fi
  fi
else
  warn "Firecrawl check disabled; set REQUIRE_FIRECRAWL=1 FIRECRAWL_API_URL=... to require it"
fi

if [[ "$errors" -gt 0 ]]; then
  printf '\n%d blocker(s), %d warning(s)\n' "$errors" "$warnings" >&2
  exit 1
fi

printf '\nPrerequisite check passed with %d warning(s).\n' "$warnings"
