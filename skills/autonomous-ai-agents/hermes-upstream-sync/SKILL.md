---
name: hermes-upstream-sync
description: Safely bring the Snapetech Hermes deployment fork back in line with upstream NousResearch/hermes-agent from inside the pod. Use this when the banner shows commits behind upstream or the operator asks to sync/merge upstream into the private deployment fork and redeploy.
version: 1.0.0
author: Snapetech Hermes deployment
license: MIT
metadata:
  hermes:
    tags: [hermes, upstream-sync, deployment, fork, kubernetes, github-actions]
    related_skills: [hermes-agent, github-pr-workflow, test-driven-development, systematic-debugging]
---

# Hermes Upstream Sync

Use this skill inside the Hermes pod to bring the private deployment fork
`example-org/hermes-agent-private` closer to upstream `NousResearch/hermes-agent`
without losing local deployment changes.

Repository roles:

- `NousResearch/hermes-agent` is upstream source/reference.
- `example-org/hermes-agent-private` is the private fork used for builds, deploys,
  self PRs, self issues, and operator-reviewed changes.
- `snapetech/hermes-agent-evolved` is generated public sanitized mirror output.
  Do not open sync PRs or issues there.
- `/opt/data/hermes-agent` is the in-pod persistent deployment knowledge
  checkout. It should track the private fork, not become a pure upstream clone.

## Safety Rules

Do not push to `main`, merge PRs, or mutate the live deployment without explicit
operator approval. The normal end state is a branch or PR against
`example-org/hermes-agent-private`; the existing GitHub Actions deploy pipeline handles
the pod restart after approved changes land on `main`.

Ask the operator before continuing when:

- upstream touched auth, sudo, RBAC, Kubernetes manifests, model routing,
  compaction, memory/session persistence, approval handling, MCP exposure,
  secrets, public mirror publishing, or gateway restart behavior
- a merge conflict cannot be resolved mechanically from local intent
- tests fail and the fix is not obvious
- local dirty changes exist and are not clearly generated artifacts from this
  sync attempt
- the next step would push a branch, open a PR, merge, deploy, or restart Hermes

Prefer small, reviewable syncs. If upstream drift is very large, split the work
by subsystem instead of producing one unreviewable merge.

Do not default to a blind merge. The baseline assumption is selective
adaptation: keep the private deployment method where it is intentional and
working, unless upstream is clearly better.

Use this intake frame before resolving any overlap:

- pretend none of the old SnapE local work exists yet
- start from today's upstream Hermes Agent
- ask what implementation you would choose now to reach the SnapE deployment
  target
- if you would still choose the local method, keep it and re-apply it
- if upstream now gets you there cleanly, adapt to upstream and delete the old
  divergence

The invariant:

- all required SnapE outputs, tooling, connections, pod workflows, and operator
  paths must still work after the sync
- or the newer Hermes functionality must replace them completely enough that the
  custom path is genuinely obsolete

If neither condition is true, the sync is incomplete.

## Standard Workflow

Start from the persistent checkout:

```bash
cd /opt/data/hermes-agent
git status --short --branch
git remote -v
```

Identify remotes by URL, not only by name. In older pod checkouts,
`fork` points at `example-org/hermes-agent-private` and `origin` points at upstream
NousResearch. In local/package checkouts, `origin` usually points at Snapetech
and `upstream` points at NousResearch.

```bash
DEPLOY_REMOTE=$(git remote -v | awk '/snapetech\/hermes-agent-private/ {print $1; exit}')
UPSTREAM_REMOTE=$(git remote -v | awk '/NousResearch\/hermes-agent/ {print $1; exit}')
test -n "$DEPLOY_REMOTE"
test -n "$UPSTREAM_REMOTE"
git fetch "$DEPLOY_REMOTE" main
git fetch "$UPSTREAM_REMOTE" main
git checkout main
git reset --hard "$DEPLOY_REMOTE/main"
```

Inspect the drift before changing anything:

```bash
git rev-list --left-right --count "HEAD...$UPSTREAM_REMOTE/main"
bash scripts/upstream_sync_report.sh
git log --oneline --left-right --cherry-pick --boundary --max-count=80 "HEAD...$UPSTREAM_REMOTE/main"
```

Read the report before deciding what to do. Treat these sections as mandatory:

- private-only commits
- upstream-only commits
- files changed on both sides
- design-sensitive overlap
- keep-local-method overlap

Before touching code, classify each overlap as:

- `upstream-first`: upstream already does what we need today
- `local-first`: we would still choose the local method on fresh upstream
- `hybrid`: upstream helps, but SnapE-specific behavior still requires local
  adaptation

If the repo is already `0` behind upstream, skip branch creation for the moment
and refresh the report/ledger first so the baseline stays accurate.

Create a branch when upstream-only commits remain:

```bash
BRANCH="sync/upstream-$(date -u +%Y%m%d-%H%M%S)"
git switch -c "$BRANCH"
```

Update the durable design ledger for this sync pass before merging:

```bash
$EDITOR docs/upstream-sync-design-deltas.md
```

Default preparation path:

```bash
scripts/upstream_sync_prepare_branch.sh
```

That script now prepares the branch and writes the report. It does not attempt
the merge unless explicitly told to do so.

Only attempt a merge after review:

```bash
APPLY_MERGE=1 scripts/upstream_sync_prepare_branch.sh
```

If conflicts occur, resolve them with LLM assistance and preserve deployment
intent:

- keep Snapetech deployment manifests, secrets wiring, local model routing,
  runtime persistence, public mirror policy, and pod-specific docs unless the
  upstream change clearly supersedes them
- keep the local deferred reload/restart workflow, repo-first self-edit policy,
  and stale-manifest auto-heal unless upstream is clearly better and the change
  is revalidated locally
- remove old local work when upstream now makes it obsolete; do not preserve
  divergence out of habit
- keep upstream bug fixes and tests unless they directly conflict with local
  deployment constraints
- inspect both sides with `git diff --ours`, `git diff --theirs`, and
  `git show "$UPSTREAM_REMOTE/main:<path>"`
- after resolving each file, run `git add <path>`
- if uncertain, stop and ask the operator with the exact file and competing
  choices

After the merge is clean:

```bash
git status --short
source .venv/bin/activate 2>/dev/null || source /app/.venv/bin/activate
scripts/run_tests.sh tests/test_snapetech_deploy_customizations.py tests/hermes_cli/test_update_check.py
scripts/run_tests.sh
python scripts/audit_live_reproducibility.py --kubectl 'sudo kubectl' --json
```

Use targeted tests first when resolving conflicts, then the full suite before
requesting merge. If the full suite is too expensive or blocked, report the
blocker and the exact targeted tests that passed.

When a local method is kept over an upstream alternative, document why we would
still choose it on fresh upstream in `docs/upstream-sync-design-deltas.md`.
When upstream wins, document that the old local path is obsolete and why.

If `git rev-list --left-right --count "HEAD...$UPSTREAM_REMOTE/main"` shows `0`
upstream-only commits, do this instead of opening a new sync branch:

```bash
$EDITOR docs/upstream-sync-report.md docs/upstream-sync-design-deltas.md
git add docs/upstream-sync-report.md docs/upstream-sync-design-deltas.md
git commit -m "Refresh upstream sync baseline"
```

Update the ledger:

```bash
$EDITOR HERMES_CHANGELOG.md docs/upstream-sync-design-deltas.md
git add HERMES_CHANGELOG.md docs/upstream-sync-design-deltas.md
git commit
```

Commit message pattern:

```text
Merge upstream NousResearch main
```

Push only after operator approval:

```bash
git push "$DEPLOY_REMOTE" "$BRANCH"
```

Open a PR against `example-org/hermes-agent-private:main`. The PR body should include:

- upstream commit merged
- ahead/behind counts before and after
- conflicts and resolutions
- tests run
- deployment risk notes
- whether the existing GitHub Actions deploy pipeline should handle rollout

## Deployment Path

Do not manually restart the pod if the approved PR is merged into
`example-org/hermes-agent-private:main`; the GitHub Actions deploy pipeline should
build the image, apply Kubernetes manifests, and roll the pod.

After the pipeline completes, verify:

```bash
gh run list --repo example-org/hermes-agent-private --branch main --limit 5
sudo kubectl -n hermes rollout status deploy/hermes-gateway --timeout=240s
python scripts/audit_live_reproducibility.py --kubectl 'sudo kubectl' --json
```

Then sync the persistent checkout to the private fork remote if needed:

```bash
cd /opt/data/hermes-agent
DEPLOY_REMOTE=$(git remote -v | awk '/snapetech\/hermes-agent-private/ {print $1; exit}')
git fetch "$DEPLOY_REMOTE" main
git reset --hard "$DEPLOY_REMOTE/main"
```

A clean finish means:

- live image tag matches the merged `main` commit
- `/opt/data/hermes-agent` HEAD matches the private fork `main`
- live reproducibility audit has no findings
- the banner's upstream-behind count is zero or reduced to any deliberately
  deferred upstream commits
