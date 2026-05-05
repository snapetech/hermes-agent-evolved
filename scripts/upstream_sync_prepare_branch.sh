#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PRIVATE_REMOTE="${PRIVATE_REMOTE:-origin}"
PRIVATE_REF="${PRIVATE_REF:-main}"
UPSTREAM_URL="${UPSTREAM_URL:-https://github.com/NousResearch/hermes-agent.git}"
UPSTREAM_REF="${UPSTREAM_REF:-main}"
UPSTREAM_TRACK_REF="${UPSTREAM_TRACK_REF:-refs/remotes/upstream-sync/${UPSTREAM_REF}}"
BRANCH_NAME="${BRANCH_NAME:-upstream-sync/$(date -u +%Y%m%d-%H%M%S)}"
REPORT_PATH="${REPORT_PATH:-docs/upstream-sync-report.md}"
APPLY_MERGE="${APPLY_MERGE:-0}"
AUTO_COMMIT="${AUTO_COMMIT:-0}"
INHERITED_WORKFLOW_PATHS=(
  ".github/workflows/contributor-check.yml"
  ".github/workflows/deploy-site.yml"
  ".github/workflows/docker-publish.yml"
  ".github/workflows/docs-site-checks.yml"
  ".github/workflows/nix-lockfile-check.yml"
  ".github/workflows/nix-lockfile-fix.yml"
  ".github/workflows/nix.yml"
  ".github/workflows/skills-index.yml"
  ".github/workflows/supply-chain-audit.yml"
  ".github/actions/nix-setup/action.yml"
)

cd "$ROOT_DIR"

prune_inherited_workflows() {
  local removed=0
  local path
  for path in "${INHERITED_WORKFLOW_PATHS[@]}"; do
    if [[ -e "$path" ]]; then
      rm -rf "$path"
      removed=1
    fi
  done
  if [[ "$removed" == "1" ]]; then
    echo "pruned inherited upstream CI/workflow noise from sync branch"
  fi
}

if [[ -n "$(git status --porcelain)" ]]; then
  echo "working tree must be clean before preparing an upstream sync branch" >&2
  exit 2
fi

git fetch "$PRIVATE_REMOTE" "$PRIVATE_REF" >/dev/null
git fetch "$UPSTREAM_URL" "${UPSTREAM_REF}:${UPSTREAM_TRACK_REF}" >/dev/null

private_ref="refs/remotes/${PRIVATE_REMOTE}/${PRIVATE_REF}"
upstream_ref="$UPSTREAM_TRACK_REF"

git checkout -B "$BRANCH_NAME" "$private_ref"

python3 "$ROOT_DIR/scripts/upstream_sync_triage.py" \
  --private-ref "$private_ref" \
  --upstream-ref "$upstream_ref" \
  --output "$REPORT_PATH" >/dev/null

echo "prepared branch $BRANCH_NAME from $private_ref"
echo "wrote policy-aware triage report to $REPORT_PATH"

if [[ "$APPLY_MERGE" != "1" ]]; then
  echo "selective merge is gated; review the report and cherry-pick/adapt fixes first"
  echo "rerun with APPLY_MERGE=1 to attempt a merge after review"
  exit 0
fi

if ! git merge --no-ff --no-commit "$upstream_ref"; then
  echo
  echo "merge produced conflicts on branch $BRANCH_NAME" >&2
  git status --short >&2
  exit 3
fi

prune_inherited_workflows

if [[ "$AUTO_COMMIT" == "1" ]]; then
  git commit -m "Merge upstream ${UPSTREAM_REF} into ${PRIVATE_REF}"
else
  echo "merge applied without conflicts on branch $BRANCH_NAME"
  echo "review and commit manually, or rerun with AUTO_COMMIT=1"
fi
