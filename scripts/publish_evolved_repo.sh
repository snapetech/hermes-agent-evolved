#!/usr/bin/env bash
set -euo pipefail

TARGET_REPO="${TARGET_REPO:-snapetech/hermes-agent-evolved}"
TARGET_BRANCH="${TARGET_BRANCH:-main}"
UPSTREAM_REPO="${UPSTREAM_REPO:-https://github.com/NousResearch/hermes-agent.git}"
UPSTREAM_REF="${UPSTREAM_REF:-main}"
PRIVATE_REF="${PRIVATE_REF:-HEAD}"
PUSH="${PUSH:-0}"
STAGING="${STAGING:-0}"
KEEP_WORKDIR="${KEEP_WORKDIR:-0}"
WORKDIR=""

usage() {
  cat <<'EOF'
Usage: scripts/publish_evolved_repo.sh [--push|--staging] [--upstream-ref REF] [--private-ref REF]

Builds a public-safe Hermes Agent evolved tree as:

  NousResearch/hermes-agent:<upstream-ref>
    + one sanitized Snapetech mirror overlay commit

The destination gets upstream history plus the broadest public-safe overlay the
private fork can publish, not the private deployment repository history.

Modes:
  (default)       Dry run — build the sanitized tree, run all scans, do not push.
  --staging       Push to staging/YYYYMMDD-HHMMSS branch on TARGET_REPO for human
                  review before promotion. Never touches TARGET_BRANCH.
  --push          Force-push to TARGET_REPO:TARGET_BRANCH. Use only after a
                  successful --staging review, or for scheduled cron runs.

Environment:
  TARGET_REPO     Destination repository, default snapetech/hermes-agent-evolved
  TARGET_BRANCH   Destination branch, default main
  UPSTREAM_REPO    Upstream git URL, default NousResearch/hermes-agent
  UPSTREAM_REF     Upstream ref, default main
  PRIVATE_REF      Private source ref for public-safe overlay files, default HEAD
  PUSH             Set to 1 to push to main (equivalent to --push)
  STAGING          Set to 1 to push to staging branch (equivalent to --staging)
  REMOTE_URL       Optional destination remote URL
  KEEP_WORKDIR     Set to 1 to keep the temp workdir
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push)
      PUSH=1
      shift
      ;;
    --staging)
      STAGING=1
      shift
      ;;
    --upstream-ref)
      UPSTREAM_REF="${2:?missing upstream ref}"
      shift 2
      ;;
    --private-ref)
      PRIVATE_REF="${2:?missing private ref}"
      shift 2
      ;;
    --target-repo)
      TARGET_REPO="${2:?missing owner/repo}"
      shift 2
      ;;
    --target-branch)
      TARGET_BRANCH="${2:?missing branch}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_clean_private_worktree() {
  local status
  status="$(git status --short)"
  if [[ -n "$status" && "${ALLOW_DIRTY_PRIVATE_TREE:-0}" != "1" ]]; then
    cat >&2 <<EOF
Private worktree is dirty. Commit/stash first, or set ALLOW_DIRTY_PRIVATE_TREE=1
for a local dry run that intentionally ignores uncommitted changes.

$status
EOF
    exit 1
  fi
}

public_overlay_excluded_path() {
  local path="$1"

  case "$path" in
    .git/*|.github/workflows/*|benchmark_runs/*|benchmarks/llm/results/*|node_modules/*|__pycache__/*|.pytest_cache/*)
      return 0
      ;;
    .claude/*|.codex/*|.cursor/*|.ssh/*|.config/gh/*)
      return 0
      ;;
    .env|.env.local|.env.*.local|.env.production|.env.staging|*.pem|*.key|*.p12|*.pfx)
      return 0
      ;;
  esac

  case "$path" in
    deploy/k8s/PUBLIC-DEPLOY.md|deploy/k8s/hermes-resource-review.py)
      return 1
      ;;
    deploy/k8s/check-public-prereqs.sh|deploy/k8s/smoke-public-deploy.sh|deploy/k8s/reproduce-minimal.sh)
      return 1
      ;;
    deploy/k8s/public-examples|deploy/k8s/public-examples/*)
      return 1
      ;;
    deploy/k8s/*.example.*|deploy/k8s/*.lock.example.json|deploy/k8s/memory.seed.example.md)
      return 1
      ;;
    deploy/k8s/*)
      return 0
      ;;
    skills/security|skills/security/*|tools/siem_tool.py)
      return 0
      ;;
  esac

  return 1
}

repo_root="$(git rev-parse --show-toplevel)"
private_sha="$(git -C "$repo_root" rev-parse "$PRIVATE_REF")"

if [[ "$PUSH" == "1" ]]; then
  require_clean_private_worktree
fi

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/hermes-evolved-upstream.XXXXXX")"
upstream="$WORKDIR/upstream"
overlay="$WORKDIR/overlay"

cleanup() {
  if [[ "$KEEP_WORKDIR" == "1" ]]; then
    echo "Kept workdir: $WORKDIR" >&2
  else
    rm -rf "$WORKDIR"
  fi
}
trap cleanup EXIT

mkdir -p "$overlay"

retry() {
  local attempt
  for attempt in 1 2 3 4 5; do
    if "$@"; then
      return 0
    fi
    if [[ "$attempt" == "5" ]]; then
      return 1
    fi
    sleep "$((attempt * 5))"
  done
}

echo "==> cloning upstream base"
retry git clone --branch "$UPSTREAM_REF" "$UPSTREAM_REPO" "$upstream" >/dev/null
upstream_sha="$(git -C "$upstream" rev-parse HEAD)"

echo "==> removing inherited upstream GitHub Actions workflows"
rm -rf "$upstream/.github/workflows"

echo "==> extracting public-safe overlay from private ref $private_sha"
archive_paths=()
while IFS= read -r path; do
  if public_overlay_excluded_path "$path"; then
    continue
  fi
  archive_paths+=("$path")
done < <(git -C "$repo_root" ls-tree -r --name-only "$private_sha")

if [[ "${#archive_paths[@]}" -gt 0 ]]; then
  git -C "$repo_root" archive "$private_sha" "${archive_paths[@]}" | tar -x -C "$overlay"
fi

echo "==> applying public-safe tracked overlay (${#archive_paths[@]} files)"
rsync -a --delete --exclude='.git' "$overlay"/ "$upstream"/
rm -rf "$upstream/.github/workflows"

if [[ -f "$overlay/README.md" ]]; then
  cp "$overlay/README.md" "$upstream/README.md"
fi
mkdir -p "$upstream/deploy/k8s"
if [[ -f "$overlay/deploy/k8s/PUBLIC-DEPLOY.md" ]]; then
  cp "$overlay/deploy/k8s/PUBLIC-DEPLOY.md" "$upstream/deploy/k8s/README.md"
fi
if [[ -f "$overlay/deploy/k8s/hermes-resource-review.py" ]]; then
  cp "$overlay/deploy/k8s/hermes-resource-review.py" "$upstream/deploy/k8s/hermes-resource-review.py"
  chmod 0755 "$upstream/deploy/k8s/hermes-resource-review.py"
fi
if [[ -d "$overlay/deploy/k8s/public-examples" ]]; then
  rm -rf "$upstream/deploy/k8s/public-examples"
  cp -R "$overlay/deploy/k8s/public-examples" "$upstream/deploy/k8s/public-examples"
fi
for helper in check-public-prereqs.sh smoke-public-deploy.sh; do
  if [[ -f "$overlay/deploy/k8s/$helper" ]]; then
    cp "$overlay/deploy/k8s/$helper" "$upstream/deploy/k8s/$helper"
    chmod 0755 "$upstream/deploy/k8s/$helper"
  fi
done
mkdir -p "$upstream/docs"
for doc in evolved-decisions.md evolved-tooling.md improvement-system.md research-update-cycles.md reproducibility-audit.md evolved-model-matrix.md upstream-sync.md; do
  if [[ -f "$overlay/docs/$doc" ]]; then
    cp "$overlay/docs/$doc" "$upstream/docs/$doc"
  fi
done
for path in \
  benchmarks/llm/model_capability_cards.md \
  benchmarks/llm/model_capability_cards.generated.md \
  benchmarks/llm/local_llm_benchmark_report_20260421.md \
  benchmarks/llm/model_benchmark_scorecard.md \
  benchmarks/llm/nous_edge_watch_local_results_20260422.md \
  benchmarks/llm/run_slm_utility_bench.sh \
  benchmarks/llm/slm_candidates.tsv \
  benchmarks/llm/split_card_test_plan_20260422.md \
  scripts/hermes_model_benchmark.py \
  scripts/llama_throughput_compare.py \
  scripts/model_capability_cards.py \
  tests/scripts/test_model_capability_cards.py
do
  if [[ -f "$overlay/$path" ]]; then
    mkdir -p "$upstream/$(dirname "$path")"
    cp "$overlay/$path" "$upstream/$path"
    case "$path" in
      *.sh|scripts/*.py)
        chmod 0755 "$upstream/$path"
        ;;
    esac
  fi
done
for path in \
  tests/test_tui_gateway_server.py \
  tui_gateway/server.py \
  ui-tui/README.md \
  ui-tui/src/__tests__/pulseStore.test.ts \
  ui-tui/src/app/createGatewayEventHandler.ts \
  ui-tui/src/app/interfaces.ts \
  ui-tui/src/app/pulseStore.ts \
  ui-tui/src/app/uiStore.ts \
  ui-tui/src/app/useInputHandlers.ts \
  ui-tui/src/app/useMainApp.ts \
  ui-tui/src/components/appLayout.tsx \
  ui-tui/src/components/pulsePanel.tsx \
  ui-tui/src/gatewayTypes.ts \
  ui-tui/src/types.ts
do
  if [[ -f "$overlay/$path" ]]; then
    mkdir -p "$upstream/$(dirname "$path")"
    cp "$overlay/$path" "$upstream/$path"
  fi
done
for skill in hermes-introspection putter; do
  if [[ -f "$overlay/skills/autonomous-ai-agents/$skill/SKILL.md" ]]; then
    mkdir -p "$upstream/skills/autonomous-ai-agents/$skill"
    cp "$overlay/skills/autonomous-ai-agents/$skill/SKILL.md" \
      "$upstream/skills/autonomous-ai-agents/$skill/SKILL.md"
  fi
done

cat >"$upstream/PUBLICATION.md" <<EOF
# Hermes Agent Evolved

This repository is built from upstream Hermes Agent with a public-safe Snapetech
overlay.

Base:

- upstream: \`NousResearch/hermes-agent\`
- upstream_ref: \`$UPSTREAM_REF\`
- upstream_sha: \`$upstream_sha\`

Overlay:

- private_source_ref: \`$PRIVATE_REF\`
- private_source_sha: \`$private_sha\`
- private deployment history is not published here

Publication rules:

- Keep live Kubernetes manifests, host-specific runbooks, self-hosted runner
  labels, internal hostnames, private service IPs, Discord IDs, SSH key names,
  and GitLab topology in the private package repository.
- Remove inherited upstream GitHub Actions workflows from the public mirror.
  Public automation should be added only when it is purpose-built for this
  sanitized overlay and does not require private infrastructure or secrets.
- Mirror all tracked private-fork files by default, except paths blocked by the
  publication denylist. The sanitizer and leak scans are the publication gate.
- Publish generalized deployment examples and reusable deployment utilities;
  keep live manifests, host wrappers, runtime ConfigMaps, and operator runbooks
  private unless they have a dedicated public-safe form.
- Raw benchmark run artifacts are not published. Publish derived summaries,
  benchmark scripts, candidate manifests, and capability cards only after
  hostnames, local paths, service IPs, and runner-specific labels are scrubbed.
- Runtime credentials belong in environment variables, Kubernetes Secrets, or
  GitHub repository secrets. They must never be committed.

Start here:

- \`docs/evolved-decisions.md\`
- \`docs/evolved-tooling.md\`
- \`docs/improvement-system.md\`
- \`docs/research-update-cycles.md\`
- \`docs/reproducibility-audit.md\`
- \`docs/evolved-model-matrix.md\`
- \`docs/upstream-sync.md\`
- \`skills/autonomous-ai-agents/hermes-introspection/SKILL.md\`
- \`skills/autonomous-ai-agents/putter/SKILL.md\`
- \`deploy/k8s/README.md\`
- \`deploy/k8s/hermes-resource-review.py\`
- \`deploy/k8s/public-examples/README.md\`
- \`benchmarks/llm/model_capability_cards.md\`
- \`benchmarks/llm/slm_candidates.tsv\`
EOF

while IFS= read -r -d '' file; do
  if ! grep -Iq . "$file"; then
    continue
  fi
  perl -0pi \
    -e 's/node-a/node-a/g;' \
    -e 's/node-b/node-b/g;' \
    -e 's/gitlab\.home/gitlab.example.internal/g;' \
    -e 's/hermes\.home/hermes.example.internal/g;' \
    -e 's#example-org/hermes-agent-private#example-org/hermes-agent-private#g;' \
    -e 's#example-group/hermes-agent#example-group/hermes-agent#g;' \
    -e 's#hermes-agent-private#hermes-agent-private#g;' \
    -e 's/security-lab/security-lab/g;' \
    -e 's/SECURITY-PLATFORM-SETUP/SECURITY-PLATFORM-SETUP/g;' \
    -e 's#10\.42\.0\.1#10.0.0.10#g;' \
    -e 's#192\.168\.50\.([0-9]{1,3})#10.0.50.$1#g;' \
    -e 's#/opt/models/hermes-bench#/opt/models/hermes-bench#g;' \
    -e 's#/workspace/hermes-agent#/workspace/hermes-agent#g;' \
    -e 's#/home/example-user/Documents/code/llama\.cpp#/workspace/llama.cpp#g;' \
    -e 's#/home/example-user#/home/example-user#g;' \
    -e 's/public-k8s/public-k8s/g;' \
    -e 's/<discord-user-id>/<discord-user-id>/g;' \
    -e 's/<discord-channel-id>/<discord-channel-id>/g;' \
    -e 's/ghp_[A-Za-z0-9_]{20,}/GITHUB_TOKEN_PLACEHOLDER/g;' \
    -e 's/github_pat_[A-Za-z0-9_]{20,}/GITHUB_TOKEN_PLACEHOLDER/g;' \
    -e 's/glpat-[A-Za-z0-9_-]{20,}/GITLAB_TOKEN_PLACEHOLDER/g;' \
    -e 's/xox[baprs]-[A-Za-z0-9-]{20,}/SLACK_TOKEN_PLACEHOLDER/g;' \
    -e 's/sk-[A-Za-z0-9]{32,}/API_KEY_PLACEHOLDER/g;' \
    -e 's/AKIA[0-9A-Z]{16}/AWS_KEY_ID_PLACEHOLDER/g;' \
    -e 's/AIza[0-9A-Za-z_-]{35}/GOOGLE_API_KEY_PLACEHOLDER/g;' \
    "$file"
done < <(find "$upstream" -path "$upstream/.git" -prune -o -type f -print0)

run_scan() {
  local name="$1"
  shift
  echo "==> $name"
  if "$@"; then
    echo "ok: $name"
  else
    echo "FAILED: $name" >&2
    return 1
  fi
}

secret_pattern='ghp_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{30,}|glpat-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|BEGIN (RSA|OPENSSH|EC|DSA|PRIVATE) KEY|https?://oauth2:[^@[:space:]]+@|sk-[A-Za-z0-9]{32,}|AIza[0-9A-Za-z_-]{35}|AKIA[0-9A-Z]{16}'
private_pattern='node-a|node-b|gitlab\.home|hermes\.home|10\.42\.0\.1|192\.168\.50\.|/home/example-user|<discord-user-id>|<discord-channel-id>|public-k8s|security-lab|SECURITY-PLATFORM-SETUP|hermes-agent-private'
inline_secret_pattern='(kind:[[:space:]]*Secret|stringData:|password:[[:space:]]*[A-Za-z0-9_/+=.-]{8,}|token:[[:space:]]*[A-Za-z0-9_/+=.-]{20,})'

run_scan "private infrastructure marker scan" \
  bash -c "! rg -n -I --hidden --glob '!.git/**' '$private_pattern' '$upstream'"

run_scan "inline Kubernetes/private secret scan" \
  bash -c "! rg -n -I --hidden --glob '!.git/**' '$inline_secret_pattern' '$upstream/deploy' '$upstream/.github' 2>/dev/null"

if command -v gitleaks >/dev/null 2>&1; then
  run_scan "gitleaks filesystem scan" gitleaks detect --no-git --source "$upstream" --redact --verbose
else
  echo "warn: gitleaks not installed; using targeted scans"
  # Exclude .env.example from the primary scan (upstream ships placeholder
  # examples), but enforce that every secret-pattern match in .env.example
  # begins with a known-fake prefix. A real key accidentally added to
  # .env.example can no longer slip through.
  run_scan "high-confidence secret pattern scan" \
    bash -c "! rg -n -I --hidden --glob '!.git/**' --glob '!**/tests/**' --glob '!**/website/docs/**' --glob '!**/skills/mcp/native-mcp/SKILL.md' --glob '!**/.env.example' '$secret_pattern' '$upstream'"

  if [[ -f "$upstream/.env.example" ]]; then
    # Known-fake placeholder prefixes: these are either comment examples
    # (`sk-kimi-` with a bare suffix like 'your_key_here'), or prefixes that
    # obviously end with a placeholder word. A real key is typically >=32
    # base58/base62 chars with no underscore/dash/period after the prefix.
    fake_allowed='^(#.*|[[:space:]]*[A-Z_]+=)?.*(sk-[A-Za-z0-9-]*(your|example|placeholder|xxxxx|kimi-|proj-|openai-|anthropic-)[A-Za-z0-9_-]*|ghp_your|glpat-your|xoxb-your|AIza[A-Za-z0-9_-]*your|AKIA[0-9A-Z]*EXAMPLE)'
    if rg -n -I "$secret_pattern" "$upstream/.env.example" >/tmp/envexample.hits 2>/dev/null; then
      if [[ -s /tmp/envexample.hits ]]; then
        # Any line in .env.example that looked like a secret but doesn't match
        # the known-fake allowlist is a problem.
        real_looking=$(grep -v -E "$fake_allowed" /tmp/envexample.hits || true)
        if [[ -n "$real_looking" ]]; then
          echo "FAILED: .env.example contains non-placeholder-looking secret pattern(s):" >&2
          echo "$real_looking" >&2
          echo "If these are legitimate fake placeholders, add their prefix to fake_allowed in scripts/publish_evolved_repo.sh." >&2
          rm -f /tmp/envexample.hits
          exit 1
        fi
      fi
      rm -f /tmp/envexample.hits
    fi
    echo "ok: .env.example secret-pattern matches are all known-fake placeholders"
  fi
fi

if [[ -n "$(git -C "$upstream" status --porcelain)" ]]; then
  git -C "$upstream" add -A
  git -C "$upstream" -c user.name="Hermes Publisher" -c user.email="hermes-publisher@example.invalid" \
    commit -m "Add public-safe Snapetech evolved overlay" >/dev/null
fi

echo "Sanitized upstream-based tree ready:"
echo "- upstream_sha: $upstream_sha"
echo "- private_source_sha: $private_sha"
echo "- output: $upstream"
echo "- head: $(git -C "$upstream" rev-parse HEAD)"
echo "- files: $(git -C "$upstream" ls-files | wc -l)"

if [[ "$PUSH" == "1" && "$STAGING" == "1" ]]; then
  echo "error: --push and --staging are mutually exclusive" >&2
  exit 2
fi

if [[ "$STAGING" == "1" ]]; then
  staging_branch="staging/$(date -u +%Y%m%d-%H%M%S)"
  remote_url="${REMOTE_URL:-git@github.com:${TARGET_REPO}.git}"
  git -C "$upstream" remote remove origin
  git -C "$upstream" remote add origin "$remote_url"
  retry git -C "$upstream" push origin "HEAD:${staging_branch}"
  cat <<EOF
Staged sanitized tree to ${TARGET_REPO}:${staging_branch}

Review at:
  https://github.com/${TARGET_REPO}/tree/${staging_branch}
  https://github.com/${TARGET_REPO}/compare/${TARGET_BRANCH}...${staging_branch}

If it looks right, promote with:
  scripts/publish_evolved_repo.sh --push

Or reject by deleting the staging branch:
  git push ${remote_url} --delete ${staging_branch}
EOF
elif [[ "$PUSH" == "1" ]]; then
  remote_url="${REMOTE_URL:-git@github.com:${TARGET_REPO}.git}"
  git -C "$upstream" remote remove origin
  git -C "$upstream" remote add origin "$remote_url"
  retry git -C "$upstream" push --force origin "HEAD:$TARGET_BRANCH"
  echo "Pushed upstream-based sanitized tree to ${TARGET_REPO}:${TARGET_BRANCH}"
else
  echo "Dry run only. Re-run with --staging to push to a review branch, or --push/PUSH=1 to publish to ${TARGET_BRANCH}."
fi
