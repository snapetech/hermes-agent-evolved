# Snapetech Fork — Operator Pointer

This repository is **`example-org/hermes-agent-private`**, a private deployment fork of
[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).

The `README.md` and `AGENTS.md` in this tree are deliberately kept as
upstream's — this file exists to give operators and fork-aware agents the
context upstream's docs cannot provide.

## Three-Repo Model

| Role | Repository | Remote | Purpose |
|---|---|---|---|
| Upstream source | `NousResearch/hermes-agent` | `upstream` (push DISABLED) | Product source. Read-only signal. |
| Private deployment fork | `example-org/hermes-agent-private` | `origin` (GitHub) + `gitlab` (GitLab mirror) | This tree. Holds private k8s manifests, hostnames, runner labels, runbooks. |
| Public sanitized mirror | `snapetech/hermes-agent-evolved` | — (generated, never hand-written) | Published via `scripts/publish_evolved_repo.sh`. |

Sync direction is strictly: `upstream → pkg → evolved`. Pushes **never** go back
to `upstream` (push URL is `DISABLED`); backports to upstream happen only
through the contribution workflow documented in
[`docs/upstream-contribution-queue.md`](docs/upstream-contribution-queue.md).

## Conventions That Differ From Upstream

1. **HERMES_CHANGELOG.md is the audit ledger.** Every fork-made change is
   recorded there with the commit SHA. Discipline rules live in
   [`docs/changelog-discipline.md`](docs/changelog-discipline.md). A pre-push
   hook (installable via `scripts/install-git-hooks.sh`) warns when commits
   lack ledger entries.
2. **Upstream supersedes fork code during sync.** Policy is in
   [`docs/upstream-sync.md`](docs/upstream-sync.md). When `upstream/main`
   conflicts with local implementation, take upstream first, then back-build
   any Snapetech-only gaps as follow-up overlay changes. The keep-local
   manifest is historical context, not permission to prefer fork code over
   official code during an upstream merge.
3. **Repo-first self-edit.** Hermes edits the canonical repo checkout, not the
   runtime/pod copies. See the `hermes-upstream-sync` skill and the pod
   canonicalization docs.
4. **Publication is gated.** Public mirror is rebuilt as *upstream + one
   sanitized overlay commit*. The sanitizer runs regex + inline-Kubernetes
   secret scans before push. Staging-branch dry-run is preferred; see
   `scripts/publish_evolved_repo.sh --staging`.
5. **CI is fork-gated.** All workflows in `.github/workflows/` carry
   `if: github.repository == 'example-org/hermes-agent-private'` so upstream PRs
   pulling these files don't run them.

## Where to Look

| Question | File |
|---|---|
| What's changed in this fork? | `HERMES_CHANGELOG.md` |
| How is the public mirror generated? | `scripts/publish_evolved_repo.sh`, `docs/evolved-decisions.md` |
| How do upstream syncs work? | `docs/upstream-sync.md`, `docs/upstream-sync-design-deltas.md` |
| What files are intentionally kept local? | `docs/keep-local-manifest.yaml` |
| What's reproducible vs. private? | `docs/reproducibility.md` |
| Current fork health assessment | `docs/fork-evaluation-202604.md` |
| Open CVE findings + decisions | `CVE_TRIAGE.md` |
| Backport candidates for upstream | `docs/upstream-contribution-queue.md` |
| Operator runbooks | `deploy/k8s/*.md` |

## First-Time Fork Contributor / Agent

1. Read this file.
2. Install git hooks: `bash scripts/install-git-hooks.sh`.
3. Read `docs/changelog-discipline.md` before your first commit.
4. Before any `git push upstream ...`: stop. The push URL is `DISABLED` for a
   reason; upstream contributions go through `docs/upstream-contribution-queue.md`.
