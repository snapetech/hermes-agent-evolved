#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PRIVATE_REMOTE="${PRIVATE_REMOTE:-origin}"
PRIVATE_REF="${PRIVATE_REF:-main}"
UPSTREAM_URL="${UPSTREAM_URL:-https://github.com/NousResearch/hermes-agent.git}"
UPSTREAM_REF="${UPSTREAM_REF:-main}"
UPSTREAM_TRACK_REF="${UPSTREAM_TRACK_REF:-refs/remotes/upstream-sync/${UPSTREAM_REF}}"
REPORT_PATH="${REPORT_PATH:-}"

cd "$ROOT_DIR"

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

need_cmd git
need_cmd python3

git fetch "$PRIVATE_REMOTE" "$PRIVATE_REF" >/dev/null
git fetch "$UPSTREAM_URL" "${UPSTREAM_REF}:${UPSTREAM_TRACK_REF}" >/dev/null

private_ref="refs/remotes/${PRIVATE_REMOTE}/${PRIVATE_REF}"
upstream_ref="$UPSTREAM_TRACK_REF"
cmd=(
  python3
  "$ROOT_DIR/scripts/upstream_sync_triage.py"
  --private-ref "$private_ref"
  --upstream-ref "$upstream_ref"
)

if [[ -n "$REPORT_PATH" ]]; then
  cmd+=(--output "$REPORT_PATH")
fi

"${cmd[@]}"
