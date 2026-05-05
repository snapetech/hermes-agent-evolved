# Changelog Discipline

`HERMES_CHANGELOG.md` is the operator audit ledger for fork-side changes.
If it is wrong or stale, reviewers cannot tell what is local-only vs. upstream,
and the public evolved mirror cannot be trusted to match what we think shipped.

This file documents the discipline rules and the tooling that enforces them.

## Rules

1. **Every fork-side commit gets one line in `HERMES_CHANGELOG.md`.**
   Add it *after* the commit lands — do not pre-write "Pending commit -"
   lines.
2. **Use the SHA-link format** for landed commits:
   ```
   - [<short-sha>](https://github.com/example-org/hermes-agent-private/commit/<short-sha>) -
     Human-readable description in one paragraph.
   ```
3. **Group by calendar date** (`## YYYY-MM-DD` header in the file). Newest
   section at the top. Within a day, newest entry at the top.
4. **PR-backed commits** reference the PR with the merge commit SHA.
5. **Upstream merge commits** do not need ledger entries (they record
   upstream authors' commits, not fork work).
6. **Catch-all commits** (`Commit remaining workspace changes`, `Commit pending
   Hermes workspace changes`) are an anti-pattern. If you must use one, list
   every functional change in its ledger entry.

## What counts as "fork-side"

A commit is fork-side if ALL of:

- It was authored locally (not imported from upstream).
- It modifies files not in `adopt_upstream` in `docs/keep-local-manifest.yaml`
  *or* modifies keep-local files with deployment-intended changes.
- It is not a pure upstream-merge commit (those are authored by git merge).

Rule of thumb: if `git log upstream/main..HEAD --author=keith` shows it, it
needs a ledger line.

## Carve-outs (commits that do NOT need their own ledger entry)

- **Pure ledger-only commits** — a commit whose only change is
  `HERMES_CHANGELOG.md` itself (typically to back-fill a SHA link after the
  landing commit, or to record a reconciliation pass). The commit is
  self-documenting; adding a recursive entry pointing at itself is noise.
- **Pure upstream-merge commits** — produced by `git merge upstream/main`.
  The upstream-sync report and `docs/upstream-sync*.md` cover these.

The `scripts/check_changelog.sh` helper excludes the first case by treating
any commit whose touched-files are only `HERMES_CHANGELOG.md` as
self-documenting. Upstream-ancestor commits are excluded by the
`merge-base --is-ancestor` check.

## Tooling

### `scripts/check_changelog.sh`

Reports commits in a given range that lack a ledger entry. Usage:

```bash
# Check everything ahead of upstream main
bash scripts/check_changelog.sh upstream/main..HEAD

# Check a PR range
bash scripts/check_changelog.sh origin/main..HEAD

# Summary only
bash scripts/check_changelog.sh --summary upstream/main..HEAD
```

Exit code is non-zero when entries are missing. Intended for CI and the
pre-push hook.

### Pre-push hook

`scripts/hooks/pre-push` runs `check_changelog.sh` for pushes to `origin/*`
and prints a warning (non-blocking) when commits lack ledger entries. It also
*hard-blocks* any push to `upstream/*` — upstream contributions go through
`docs/upstream-contribution-queue.md`, not `git push`.

Install: `bash scripts/install-git-hooks.sh`.

## Reconciliation

When the ledger drifts (as it did pre-2026-04-23), reconciliation proceeds
as follows:

1. For each ledger entry prefixed `Pending commit -`, try to match a commit
   by description keywords against `git log --since=<section-date>`.
2. If a clean match is found, replace the prefix with
   `[<sha>](https://github.com/example-org/hermes-agent-private/commit/<sha>) -`.
3. If multiple plausible commits exist, or if the change was bundled into a
   catch-all commit, mark the entry as
   `Landed (bundled, SHA unmapped) -` and move on.
4. Add a **Reconciliation Note** at the top of the section identifying the
   reconciliation date and scope.

Unmapped entries are better than lying entries — the goal is that the ledger
never contains "pending" for anything that actually landed.

## Review checklist

Reviewers auditing a fork-side PR should check:

- [ ] Every new commit in the PR has a ledger line.
- [ ] Lines use SHA-link format, not `Pending commit -`.
- [ ] Description mentions the user-visible impact, not just the file
      changed.
- [ ] PR-backed commits cite the PR number.
- [ ] No ledger entries reference Snapetech-specific detail that shouldn't
      survive the `publish_evolved_repo.sh` sanitizer
      (`node-a`, `gitlab.example.internal`, `/home/example-user`, etc.) — but reasonable
      mention of the `pkg`/`evolved` names is fine in the ledger itself,
      which is not published to `evolved`.
