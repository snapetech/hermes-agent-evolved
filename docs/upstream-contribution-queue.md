# Upstream Contribution Queue

Fork-side changes that are generally useful — not tied to the Snapetech
deployment shape — and should be offered upstream to
`NousResearch/hermes-agent`.

## Policy

From `docs/evolved-decisions.md`:

> Upstream reusable fixes only through a separate human-approved contribution
> workflow, never through autonomous self-improvement.

Concretely:
1. Identify a candidate (local commit or ledger entry) that is generally
   useful and free of Snapetech-specific detail (no `node-a`, no
   `gitlab.example.internal`, no `/home/example-user`, no pod-only assumptions).
2. Cherry-pick to a clean branch cut from `upstream/main`.
3. Rewrite commit message in upstream style.
4. Open a PR against `NousResearch/hermes-agent`.
5. Record the PR here with its URL.

## Already Upstreamed (reference)

These went up as PRs already, visible in top-of-log merge commits on `main`:

- `fix(tui): @<name> fuzzy-matches filenames across the repo` — PR #14820
- `fix(tui): anchor inline_diff to the segment where the edit happened` — PR #14822
- `perf(ink): cache text measurements across yoga flex re-passes` — PR #14818
- `feat(computer-use): cua-driver backend, universal any-model schema` —
  commit `b07791db` (merged upstream)
- `fix(mcp): coerce stringified arrays/objects in tool args` —
  commit `9ff21437`
- `feat(tui-gateway): WebSocket transport + /chat web UI` — commit `25ba6783`

Keep going.

## Candidates

### Priority 1 — Generally useful, minimal Snapetech coupling

| Fork commit / changelog line | Description | Rationale | Owner | PR |
|---|---|---|---|---|
| `97b9b3d6 fix(gateway): drain-aware hermes update + faster still-working pings` | Gateway drain handling | Benefits any deployment that does live updates. | | |
| `44a0cbe5 fix(tui): voice mode starts OFF each launch (CLI parity)` | TUI/CLI parity for voice | Already CLI-parity in spirit; zero config coupling. | | |
| `2af0848f fix(tui): ignore SIGPIPE so stderr back-pressure can't kill the gateway` | Signal-handling hardening | Helps every multi-process deployment. | | |
| `3a959833 chore(tui): dump gateway crash traces to ~/.hermes/logs/tui_gateway_crash.log` | Crash log | Profile-aware path, generally useful. | | |
| `eeda18a9 chore(tui): record gateway exit reason in crash log` | Crash log detail | Pairs with the above. | | |
| Maintenance-freshness ledger (per 2026-04-21 ledger entry) | Durable ledger + tool for overdue maintenance | General use, not pod-specific. Scope check: ensure no `/opt/data` paths. | | |
| `hermes-upstream-sync` in-pod skill | Upstream-sync skill with behind-count banner retune | Skill could ship upstream; fork would install locally. Scope check: remove `snapetech/` specifics. | | |

### Priority 2 — Useful after genericization

| Fork change | Why useful | What to strip before PR |
|---|---|---|
| `live /reload` for CLI and gateway | Dev-loop speed for everyone | Anything referencing `/opt/data` or ConfigMap paths |
| Runtime apt/pip/npm install capture + promotion | Catches bootstrap drift | Pod-specific install list promotion — upstream version should just emit a report |
| Expanded context-engine / memory-provider surface | Plugin ergonomics | Snapetech-specific provider configs |
| `pending-turn` recovery across repeated interrupted replays | Robustness | None — already generic |

### Priority 3 — Discussion / RFC

Open an issue first; design feedback before code:

- Repo-first self-edit policy (could be an upstream-wide safety rail).
- Admission proxy interface contract (useful if upstream adopts a
  provider-side proxy mechanism).

## Anti-patterns (do not upstream)

- Anything referencing `snapetech`, `hermes-agent-private`, `hermes-agent-evolved`,
  `node-a`, `gitlab.example.internal`, `/opt/data`, or Snapetech ConfigMap layout.
- `scripts/publish_evolved_repo.sh` (fork's publication tool).
- `scripts/upstream_sync_*` helpers (fork's sync tooling).
- `docs/upstream-sync*.md`, `docs/evolved-decisions.md`, `docs/reproducibility*.md`,
  `FORK.md`, `HERMES_CHANGELOG.md`, `CVE_TRIAGE.md`.
- Private plugin directories (`mission-loop`, `level-up`, `runtime-control`,
  `ops-runtime`, `strike-freedom-cockpit`) — these are deployment product.
