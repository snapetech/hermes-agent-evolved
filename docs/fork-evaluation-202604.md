# Fork Evaluation — April 2026

Health check of the `example-org/hermes-agent-private` fork against upstream
`NousResearch/hermes-agent`, conducted 2026-04-23.

## Scope

Inventory, customizations, links, documentation, process discipline, remote
topology, publication pipeline, CI, security posture. Excludes upstream debt
(the monster files, the upstream `README.md`/`AGENTS.md`/`.env.example`)
because those are untouchable during a fork sync.

## Summary

The fork is **substantively healthy** — good upstream-sync policy, scripted
sanitized publication, fork-gated CI, and real operational differentiation
(mission-loop, level-up, runtime-control plugins; llama-admission-proxy;
Hindsight integration; Edge-Watch monitoring). Divergence is 249 commits ahead
of upstream, 0 behind — the sync pass at `8126a3bb` was effective.

But process discipline is starting to drift: the changelog ledger is lying
(48 "Pending commit" entries with a clean worktree), stale local branches
are piling up, automated CI isn't running on PRs, and known CVE findings
aren't being tracked to resolution. All fixable without touching upstream.

## Strengths

### Upstream-sync policy is unusually mature

- `docs/upstream-sync.md` states the "would we still build it this way on
  fresh upstream today?" test per file.
- `docs/upstream-sync-design-deltas.md` enumerates the durable local design
  choices (deferred runtime reload, repo-first self-edit, llama admission
  proxy, adaptive fallback order, context-length advertisement policy).
- `docs/evolved-decisions.md` is a proper decision log with upstream
  relationship annotations.
- `scripts/upstream_sync_report.sh` produces a drift report before any merge.

### Publication is scripted and gated

- `scripts/publish_evolved_repo.sh` rebuilds the public tree as upstream
  + one sanitized overlay commit (not private history).
- Sanitizer regex covers `ghp_/github_pat_/glpat-/xox[baprs]-/sk-/AKIA/AIza`
  and PEM markers.
- Inline Kubernetes `Secret`/`stringData:`/`password:`/`token:` scan.
- Private-infrastructure marker scan (`node-a`, `node-b`, `gitlab.example.internal`,
  `hermes.example.internal`, `/home/example-user`, private Discord channel IDs, etc.).
- `gitleaks` used when available, regex fallback when not.

### CI hygiene

- All workflows gated `if: github.repository == 'example-org/hermes-agent-private'`
  so upstream PRs pulling these files don't run them.
- Actions pinned by SHA (`actions/checkout@34e114876...`).
- Publish-evolved runs daily via cron (`37 15 * * *`).
- Upstream-sync-report runs daily via cron (`17 14 * * *`).

### Real operational differentiation

The overlay earns its keep:

- Plugins: `mission-loop`, `level-up`, `runtime-control`, `disk-cleanup`,
  `ops-runtime`, `strike-freedom-cockpit`.
- `deploy/k8s/` — full Kubernetes overlay with llama admission proxy,
  Hindsight integration, Edge-Watch MCP, shared-memory MCP, desktop bridge
  MCP, self-improvement cron, stack-CVE checkup.
- Repo-first self-edit policy prevents runtime/pod drift.
- Maintenance-freshness ledger for recurring operator work.

## Issues & Oversights

### 1. HERMES_CHANGELOG.md ledger discipline is broken

As of this audit: 48 `Pending commit -` entries vs. 20 with SHA links. Worktree
is clean. `main` is current. This means the "pending" entries either landed
(and were never back-filled with their SHA) or were bundled into catch-all
commits like `25fae3f5 Commit pending Hermes workspace changes` /
`28c81823 Commit remaining workspace changes` / `a12b99b1 Commit pending
Hermes runtime updates`.

**Impact**: the ledger is the operator audit index. Right now it cannot be
trusted. Reviewers auditing the fork can't confirm what was committed when.

**Fix**: reconcile — mark unmatchable entries as "Landed (bundled)" with an
explanation, best-effort SHA-match what's distinctive, and install a pre-push
hook that warns when local commits lack ledger references. See
[`docs/changelog-discipline.md`](changelog-discipline.md).

### 2. Stale local branches

Seven local branches behind `main` by 100s–1100s of commits:

| Branch | Ahead | Behind | Disposition |
|---|---|---|---|
| `upstream-sync` | 0 | 1111 | Retired sync branch — delete |
| `upstream-preview` | 0 | 985 | Retired preview — delete |
| `local/pre-upstream-sync-20260419` | 0 | 1107 | Pre-sync snapshot — delete |
| `land/evolved-publisher-direct` | 0 | 357 | Zero unique content — delete |
| `pr-3` | 1 | 357 | 1 unique: "Fix deploy bootstrap and package watchdog helper" — review + cherry-pick or delete |
| `stack-cve-runtime-inventory` | 1 | 913 | 1 unique: "Record 9070 model benchmark services" — review |
| `fix/evolved-publisher-sanitizer-20260423` | 2 | 359 | 2 unique inc. sanitizer fix — review |

Automated cleanup handles the 0-ahead set. The 3 ahead branches need human
review of unique commits before deletion.

### 3. No PR-time test enforcement

`.github/workflows/tests.yml` is `workflow_dispatch` only — PRs to
`example-org/hermes-agent-private` don't trigger the test suite. Combined with
~700 test files of surface, upstream syncs land without automated validation
unless someone clicks "Run workflow".

**Fix**: add `on: pull_request` with `paths-ignore` to skip docs-only PRs.
Single-runner (`node-a`) SPOF acknowledged; queueing is fine.

### 4. Stack CVE findings aren't tracked to resolution

`docs/stack-cve-report.md` (2026-04-21) shows 3 critical, 32 high,
4 moderate npm findings + 66 OSV findings across 2716 packages. Report is
regenerated, nothing escalates, no triage record.

**Fix**: add `CVE_TRIAGE.md` with per-CVE decisions (accept / upgrade /
waived-with-reason / pending) and update it alongside each report refresh.

### 5. Nothing has gone back upstream

`docs/evolved-decisions.md` says reusable fixes upstream "through a separate
human-approved contribution workflow" — but no such workflow artifacts exist.
Several fork changes look clearly general-use:

- Voice-mode-off-on-launch parity (`fix(tui)`, commit `44a0cbe5`)
- SIGPIPE handling (`fix(tui)`, commit `2af0848f`)
- MCP stringified-args coercion (`fix(mcp)`, commit `9ff21437`)
- TUI inline-diff segment anchoring (commit `11b2942f`)
- Gateway drain-aware update (`fix(gateway)`, commit `97b9b3d6`)

Some already went upstream as PRs (visible in merge commits at the top of
log — good). Keep the pipeline open; see
[`docs/upstream-contribution-queue.md`](upstream-contribution-queue.md).

### 6. `upstream` push "DISABLED" is a string, not a guarantee

`git remote set-url --push upstream DISABLED` just sets an invalid URL.
`git push upstream` fails with a cryptic fetch error but the intent isn't
enforced. A pre-push hook that rejects pushes to `upstream/*` is cheap
insurance.

### 7. Sanitizer `.env.example` exemption is broad

`scripts/publish_evolved_repo.sh:378` has
`--glob '!**/.env.example'` in the high-confidence secret scan. Today
`.env.example` is upstream's placeholder file — fine. But any real-looking
string added there silently bypasses the scan.

**Fix**: narrow the exception to a known-fake-placeholder allowlist, or at
least add a secondary check that every `sk-`/`ghp_`/etc pattern in
`.env.example` matches a known-fake prefix (`sk-proj-abc...`,
`sk-kimi-abc...`, etc.).

### 8. `keep-local` list is prose, not machine-readable

`docs/upstream-sync-design-deltas.md` has the keep-local files in prose.
`scripts/upstream_sync_triage.py` duplicates a subset as Python constants
(`KEEP_LOCAL_METHOD_PATTERNS`). Drift between prose and code is invisible.

**Fix**: single source of truth in `docs/keep-local-manifest.yaml`; teach the
triage script to read it.

### 9. Ghost directories

`.worktrees/` is empty (already in `.gitignore` — fine).
`tinker-atropos/` is empty and not ignored — reference to a retired
integration. Add to `.gitignore` or remove.

### 10. No staging-branch dry-run on evolved publish

`scripts/publish_evolved_repo.sh --push` force-pushes to
`snapetech/hermes-agent-evolved:main` in one shot. A reviewer-optional staging
mode (`--staging`) that pushes to a `staging/YYYYMMDD` branch and stops would
let humans sanity-check the public tree before it goes live.

## Upstream Debt (Noted, Not Touched)

These are upstream's files and touching them creates sync conflicts:

- `cli.py` (504 KB), `run_agent.py` (655 KB), `hermes_state.py` (78 KB),
  `toolsets.py` (25 KB) — fork customizations must live in plugins/hooks.
- `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md` — upstream voice.
  Fork context lives in the new `FORK.md` and this `docs/` tree.
- `.env.example` (18.6 KB) — upstream placeholder set; narrow the sanitizer
  exemption rather than editing the file.
- `docker/SOUL.md` — upstream default persona. Snapetech persona, if desired,
  lives in ConfigMap overlay (already the deployment reality).

## Priority Order

1. **Changelog reconciliation + enforcement hook** — restores audit trust.
2. **Stale branch cleanup (0-ahead safe set)** — 30 seconds of work.
3. **Tests on PR** — catches regressions in sync merges.
4. **CVE triage file** — actually close the loop on findings.
5. **Sanitizer hardening + staging mode** — shrinks publication blast radius.
6. **Keep-local manifest + triage script integration** — single source of truth.
7. **Fork-facing README (`FORK.md`)** — operator orientation.
8. **Upstream contribution queue** — stops generally-useful fixes from rotting.

## Follow-Up (Not Actioned In This Pass)

- Review-and-cherry-pick or delete the 3 branches with unique commits
  (`pr-3`, `stack-cve-runtime-inventory`, `fix/evolved-publisher-sanitizer-20260423`).
- Single-runner SPOF: `node-a` is the only self-hosted runner on CI.
  Consider a secondary for redundancy.
- Upstream-contribution workflow: actually land the top 3 candidates from the
  queue file.
- CVE triage: first pass on the 3 critical + 32 high findings.
