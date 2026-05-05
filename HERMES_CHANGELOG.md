# Hermes Change Ledger

This ledger tracks changes made by Hermes or on Hermes' behalf in this fork.
Use it as the operator review index across local commits and PR-backed changes.

**Discipline rules** are in [`docs/changelog-discipline.md`](docs/changelog-discipline.md).
Install the pre-push warning hook via `bash scripts/install-git-hooks.sh`.

Policy:

- Add an entry for every Hermes-made file change **after the commit lands**,
  using the SHA-link format (`[<sha>](https://github.com/example-org/hermes-agent-private/commit/<sha>) -`).
  Do not pre-write `Pending commit -` lines.
- Low-risk maintenance may be recorded as local commits.
- Runtime code, deployment manifests, auth/approval/RBAC/sudo/secret handling,
  MCP exposure, model routing, memory/session persistence, context compression,
  public mirror behavior, multi-file refactors, failed/untested changes, or any
  change that needs review should use a PR against `example-org/hermes-agent-private`.
- Non-`main` branch pushes are allowed for PR creation and updates. Direct
  pushes to `main`, merges, deploys, and live service mutation require explicit
  user approval.

## Reconciliation Note — 2026-04-23

48 entries in the 2026-04-21 and 2026-04-23 sections below were originally
recorded as `Pending commit - ...`. A reconciliation pass on 2026-04-23 found
that these changes landed on `main` but were bundled into catch-all commits
(`25fae3f5 Commit pending Hermes workspace changes`,
`28c81823 Commit remaining workspace changes`,
`a12b99b1 Commit pending Hermes runtime updates`) whose messages do not
preserve the per-change SHA.

The `Pending commit -` prefix was bulk-replaced with
`Landed (bundled, SHA unmapped) -` to stop the ledger from lying.
The three 2026-04-23 entries with unambiguous 1:1 commit matches were
relinked to their SHAs.

Going forward, entries must be written **after** the commit lands, with a
real SHA link. `scripts/check_changelog.sh` enforces this; the pre-push hook
warns on missing entries.

## 2026-04-23

- [18f4374e](https://github.com/example-org/hermes-agent-private/commit/18f4374e) -
  Record website/ npm-audit investigation in `CVE_TRIAGE.md`:
  non-breaking `npm audit fix` breaks Docusaurus version lockstep;
  coordinated `@docusaurus/*` bump to 3.10.0 builds green but leaves
  count unchanged (38); `--force` downgrades to 2.2.0 and conflicts
  with React 19 peer deps. Reclassified all 38 remaining website/
  advisories as `accept` — every root lives in the build toolchain or
  the `npm run start` dev-server; none ship in the static site.
  Documented reopen criteria.

- [3cdea6fc](https://github.com/example-org/hermes-agent-private/commit/3cdea6fc) -
  Fix high/moderate npm advisories in `web/` via `npm audit fix`:
  resolves `vite` (path traversal + fs.deny bypass + websocket file
  read), `picomatch` (POSIX injection + ReDoS), `flatted` (prototype
  pollution), `brace-expansion` (ReDoS hang). Lockfile-only change
  (15/15 diff). Post-fix audit: 0 vulnerabilities in `web/`.

- [db5ba0e5](https://github.com/example-org/hermes-agent-private/commit/db5ba0e5) -
  Fix `scripts/check_changelog.sh` ledger-only carve-out: replace
  incompatible `git show --no-patch --name-only` invocation with
  `git diff-tree --no-commit-id --name-only -r` so the pre-push hook
  no longer fails fatally on HERMES_CHANGELOG-only commits.

- [0e6888ce](https://github.com/example-org/hermes-agent-private/commit/0e6888ce) -
  Fork audit pass: adds `FORK.md`, `docs/fork-evaluation-202604.md`,
  `docs/keep-local-manifest.yaml`, `docs/upstream-contribution-queue.md`,
  `docs/changelog-discipline.md`, and a populated `CVE_TRIAGE.md`. Ships
  enforcement: `scripts/check_changelog.sh` (with ledger-only and
  upstream-ancestor carve-outs), `scripts/hooks/pre-push` (hard-blocks
  upstream pushes, warns on missing ledger entries), and
  `scripts/install-git-hooks.sh`. Wires `on: pull_request` for
  `tests.yml`; adds `--staging` mode and narrowed `.env.example` secret
  allowlist to `scripts/publish_evolved_repo.sh`; teaches
  `scripts/upstream_sync_triage.py` to read the keep-local manifest.
  Pruned 4 redundant branches (`upstream-sync`, `upstream-preview`,
  `local/pre-upstream-sync-20260419`, `land/evolved-publisher-direct`)
  plus three ahead-branches whose unique commits had already landed on
  main with different SHAs (`pr-3` → `aab32a4d`,
  `stack-cve-runtime-inventory` → `9df167fe`,
  `fix/evolved-publisher-sanitizer-20260423` → `c2708c5e`). Added
  `tinker-atropos/` to `.gitignore`.

- [33552524](https://github.com/example-org/hermes-agent-private/commit/33552524) -
  Expand Edge Watch community and ecosystem sources at runtime: broader
  Reddit exact-match searches, Google News RSS, broad GitHub repo/issue
  ecosystem search, and HuggingFace model/dataset/Space searches beyond the
  NousResearch org. Update the reference source registry and workspace/Edge
  Watch docs to match the implemented daily-pass lanes.

- [9ada4b2a](https://github.com/example-org/hermes-agent-private/commit/9ada4b2a) -
  Add a Nous Discord browser-monitoring assessment and channel policy:
  documents the authenticated DOM-scrape lane, explains why screenshots/Ctrl+A
  cannot capture virtualized Discord history, classifies each accessible Nous
  channel by cadence and actionability, and updates the Edge Watch/workspace
  guidance to prefer `hermes-announcements`, `developers`, `research-papers`,
  `interesting-links`, `support-threads`, and `plugins-skills-and-skins` while
  excluding low-value routine channels and treating `github-tracker` as
  fallback/cross-check only because direct GitHub collection is more
  complete.

- [f2f1bed5](https://github.com/example-org/hermes-agent-private/commit/f2f1bed5) -
  Add date-bounded delta scraping to the Discord Wayland monitor.
  `scrape --since yesterday --pages N` now jumps to latest messages, pages
  upward until the lower-bound timestamp is reached or scrolling is exhausted,
  filters the message set, and emits messages sorted oldest-to-newest so
  downstream jobs can process forward from the previous capture point. The
  result exposes `delta_complete` so a run that hits `max_pages` before the
  since boundary cannot be mistaken for a complete capture.

- Landed (bundled, SHA unmapped) - Add desktop bridge incremental scrape + focus-free window
  capture: new `desktop.find_window`, `desktop.save_focus`,
  `desktop.restore_focus` tools; `desktop.screenshot` now accepts
  `window_id` and routes through `import -window` for focus-independent
  capture; active-window detection on Wayland now prefers KWin scripting over
  XWayland's stale xdotool reading. Driver at
  `scripts/desktop-bridge-discord-scrape.py` grew incremental mode with a
  fingerprint state file under `~/.local/state/hermes-desktop-bridge/` — a
  second consecutive run against the same channel halts at page 0 with 100%
  overlap and emits zero duplicate lines. Installs `wtype` and `xdotool`.

- Landed (bundled, SHA unmapped) - Promote the desktop bridge MCP from proof-of-concept to
  functional: add Wayland input backends (wtype preferred, ydotool fallback)
  for `desktop.type`/`desktop.hotkey`/`desktop.move`/`desktop.click`, add a KDE
  Plasma active-window backend via KWin scripting plus kdotool and GNOME Shell
  paths, relax the hotkey character class so `ctrl+space` and similar chords
  validate, add screenshot `region` + JPEG output via ImageMagick, flag OCR
  truncation with a `truncated`/`char_count` pair, add `init` and
  `print-pod-env` operator subcommands, ship a `systemd --user` unit under
  `deploy/k8s/systemd/`, cover the new surface with a live HTTP roundtrip
  integration test, and resync the ConfigMap embed. Bumps the server to
  `0.2.0`.

## 2026-04-21

- Landed (bundled, SHA unmapped) - Add live `/reload` support for CLI and gateway so `.env`,
  config-driven runtime knobs, bundled skills, skill command discovery, and
  cached prompt metadata can refresh in-process between turns without a pod
  rollout; keep `/reload-mcp` as the separate MCP reconnect path.
- Landed (bundled, SHA unmapped) - Enforce repo-first Hermes self-edits by auto-healing stale
  bundled-skill manifests, blocking writes to legacy/internal pod repo paths
  when the canonical checkout exists, and updating pod/Putter guidance to keep
  durable changes in `/opt/data/workspace/hermes-agent-private` instead of runtime
  or installed copies.
- Landed (bundled, SHA unmapped) - Add expanded Wave 2 7900 XT quality results for GLM
  IQ4_XS, LFM2 24B A2B, Qwen3-Coder Q3, Gemma3 12B, and Devstral Small 2;
  regenerate the model scorecard; and document the Qwen3-Coder Q6 fit failure
  plus the stalled Nemotron download.
- Landed (bundled, SHA unmapped) - Stop TUI pending-turn auto-replay loops after context-size
  recovery failures, preserve terminal failed records for inspection, and keep
  transient failures retryable up to a bounded limit.
- Landed (bundled, SHA unmapped) - Expire stale TUI pending-turn records after a bounded age so
  old interrupted runs do not remain eligible for automatic replay forever.
- Landed (bundled, SHA unmapped) - Make the pod bootstrap install of `shared-memory-mcp.py`
  idempotent/atomic so an existing persisted copy does not crash the gateway
  container on startup.
- Landed (bundled, SHA unmapped) - Clean up failed Discord gateway startup attempts by closing
  the client task and consuming background exceptions so network outages do not
  produce unhandled asyncio tracebacks.
- Landed (bundled, SHA unmapped) - Add the no-thinking NousCoder 14B smoke output, which
  produced valid compact JSON for the edge-watch routing/risk/log probes.
- Landed (bundled, SHA unmapped) - Add NousCoder 14B edge-watch throughput/smoke outputs and
  include expanded Wave 1 measured rows in the generated model scorecard.
- Landed (bundled, SHA unmapped) - Regenerate the local model benchmark scorecard with
  expanded Wave 1 model mappings and measured LFM/SmolLM quality rows.
- Landed (bundled, SHA unmapped) - Improve cron/Putter observability by deferring LLM calls on
  high-load pre-run gates, treating empty cron responses as diagnostic failures,
  and asking non-silent maintenance jobs for a concise evidence-based decision
  trace rather than hidden chain-of-thought.
- Landed (bundled, SHA unmapped) - Add the expanded Wave 1 local model benchmark outputs and
  Qwen 3.6 research follow-up notes to guide the next local routing/model tests.
- Landed (bundled, SHA unmapped) - Add a local model benchmark scorecard helper plus
  Nous edge-watch smoke/throughput outputs so routing candidates can be compared
  by Hermes task pass rate and generation speed.
- Landed (bundled, SHA unmapped) - Keep private SIEM review paths out of the public evolved
  mirror and add publication scans for local SIEM/private infrastructure
  markers.
- Landed (bundled, SHA unmapped) - Make the pod's legacy `/opt/data/hermes-agent` path a
  compatibility alias to the canonical writable package checkout, add orphan
  reports for dirty read-only sources, and teach self-edit/Putter guidance to
  refuse non-canonical Hermes edits.
- Landed (bundled, SHA unmapped) - Add retry, timeout, and resume handling to the deploy image
  Hindsight client pip upgrade so transient PyPI download stalls do not fail the
  local k3s deploy.
- Landed (bundled, SHA unmapped) - Correct the optional GLM validator route metadata to
  advertise its guarded 8K context limit and record the host-side service name
  in the local model manifest.
- Landed (bundled, SHA unmapped) - Retry the full Cursor Agent installer flow in the local
  deploy image build so transient DNS failures against `cursor.com` or
  `downloads.cursor.com` do not abort the k3s deploy after a partial package
  download.
- Landed (bundled, SHA unmapped) - Wire GLM-4.7 Flash as an optional secondary validator route
  for the node-a Hermes deployment, add a durable local model manifest, and
  document that Qwen 3.6 remains the primary while GLM is used for
  accuracy-first second opinions when its host endpoint is running.
- Landed (bundled, SHA unmapped) - Expand the local LLM benchmark matrix with a 7900 XT pass
  for the later 9070-sidecar candidates, including GLM-4.7 Flash Q6_K_L,
  Devstral Small 2, Gemma 3 12B, LFM2, Qwen3 14B, and Qwen3-Coder variants,
  while restoring the Qwen primary service after the batch.
- Landed (bundled, SHA unmapped) - Expand the `hermes-agent-evolved` publisher from a
  hand-picked public overlay to a broad tracked-file mirror with explicit
  publication denylist rules, preserving sanitizer and secret/private-infra
  scans as the gate before the generated public mirror can push.
- Landed (bundled, SHA unmapped) - Harden pod repo-sync so `/opt/data/hermes-agent` is treated
  as read-only deployment knowledge by default, stale source checkouts are
  refused, oversized syncs are capped, and embedded pod guidance points edits
  at `/opt/data/workspace/hermes-agent-private`.
- Landed (bundled, SHA unmapped) - Add optional smart model routing that can send short,
  simple CLI turns to a configured cheaper model while keeping complex,
  code/tool-heavy, or long prompts on the primary route.
- Landed (bundled, SHA unmapped) - Include the WhatsApp bridge package manifests in the
  Docker dependency-cache layer so bridge npm installs are cached separately
  from application source copies.
- Landed (bundled, SHA unmapped) - Add a test-package shim for `tests/hermes_cli` so direct
  Hermes CLI test runs import production `hermes_cli` modules instead of the
  empty test package.
- Landed (bundled, SHA unmapped) - Promote full-suite import dependencies into the `dev`
  extra, including ACP, FastAPI/Uvicorn, NumPy, and pytest-split, so local
  test environments do not rely on ad hoc venv installs.
- Landed (bundled, SHA unmapped) - Move pinned Hindsight Python dependency installs ahead of
  app source copies in the pod image Dockerfile, split the pod image's apt,
  CLI, npm, Cursor, and Hindsight installs into independently cached layers,
  and add BuildKit cache mounts/retries for apt, npm, and pip so ordinary
  code/docs deploys reuse dependency layers instead of redownloading the
  dependency tree.
- Landed (bundled, SHA unmapped) - Add a durable `maintenance_freshness` ledger/tool so Putter,
  introspection, cron-aware maintenance, and nightly self-review can seed,
  rank, explain, snooze, and record recurring work by stale/overdue score; add
  explicit temporal anchors to skill invocations so date-sensitive maintenance
  reasoning uses the actual current date/time.
- Landed (bundled, SHA unmapped) - Add the `hermes-upstream-sync` in-pod skill for safely
  merging `NousResearch/hermes-agent` into `example-org/hermes-agent-private`, and
  retune the TUI/CLI behind-count banner so it reads as upstream drift with the
  skill as the recommended action; invalidate stale legacy update-count caches
  and shorten the pod's update-check cache interval.
- Landed (bundled, SHA unmapped) - Clarify pod repository roles so Hermes treats
  `/opt/data/hermes-agent` as its deployment knowledge checkout, with
  `NousResearch/hermes-agent` as upstream source, `example-org/hermes-agent-private`
  as private build/deploy fork, and `snapetech/hermes-agent-evolved` as the
  generated public sanitized mirror; keep the pod `GITHUB.md` ConfigMap embed
  synced from its standalone source; make runbook recovery choose the remote
  pointing at the private fork instead of assuming one remote name.
- Landed (bundled, SHA unmapped) - Add a 2026-04-21 operator incident runbook covering Hermes
  pod log triage, llama proxy 503 interpretation, primary model stop safety,
  guarded 9070 sidecars, media workload placement, non-interactive sudo,
  runtime install persistence, and persistent repo drift recovery.
- Landed (bundled, SHA unmapped) - Document failed 9070+7900 llama.cpp split experiments,
  current ROCm/HIP mixed-architecture blocker, and safe model-cache cleanup.
- Landed (bundled, SHA unmapped) - Add small local utility-model benchmark tasks, run them
  against installed 9070 Qwen/Gemma candidates, and document the safety
  boundary for low-risk summaries/extraction versus approval-critical routing.
- Landed (bundled, SHA unmapped) - Add an external HF/community model-scout backlog for
  Qwen3-Coder, Devstral, Qwen3 14B, Gemma 3, Phi-4 mini, and LFM2 candidates,
  plus llama.cpp Vulkan and ik_llama.cpp runtime experiments.
- Landed (bundled, SHA unmapped) - Add live reproducibility drift auditing, public-safe cron,
  skill, package, and memory seed artifacts, a minimal reproduction wrapper,
  and BOOT warnings for stale persistent repo checkouts.
- Landed (bundled, SHA unmapped) - Add llama.cpp throughput measurements for all functional
  local Qwen/Gemma candidates and document prompt/generation tokens per second.
- Landed (bundled, SHA unmapped) - Fix opportunistic GPU guard self-matches, require explicit
  guard profiles for local llama.cpp benchmark services, and render guarded
  candidate services with low CPU/IO priority.
- Landed (bundled, SHA unmapped) - Carry forward live model-benchmark service helper updates
  and refreshed stack audit report timestamps.
- Handoff for Hermes after PR #1 lands - replace or disable the pod-local
  `CVE stack audit and fix proposals` cron job that uses the `cve-check` skill
  and writes to `/opt/data/self-improvement/cve-reports/`. The canonical path
  should be the repo-backed `stack-cve-checkup` skill/tool, updating
  `docs/stack-inventory.json`, `docs/stack-cve-report.md`, and
  `docs/stack-cve-report.json` in the checked-out repo, with code or lockfile
  fixes handled by branch/PR unless the operator explicitly approves otherwise.
- Landed (bundled, SHA unmapped) - Add stack inventory/CVE audit tooling, a stack-cve-checkup
  skill, generated baseline inventory/report artifacts, and repo-durability
  guardrails so pod runs update the checked-out repository instead of only
  image-local or internal Hermes state.
- Landed (bundled, SHA unmapped) - Add a Hermes model-benchmark skill and local GGUF lineup
  runbook for Qwen/Gemma/Kimi-watch candidates on the 7900/9070 llama.cpp
  stack, plus benchmark script task listing and default aliases.
- Landed (bundled, SHA unmapped) - Finish hostname-safe fallback routing tests and carry the
  agent-browser dependency refresh.
- Landed (bundled, SHA unmapped) - Carry forward dirty reliability hardening: redact secrets in
  compaction inputs/outputs, match provider base URLs by hostname, coalesce
  concurrent API idempotency requests, and suppress repeated edge-watch alerts.
- Landed (bundled, SHA unmapped) - Replace the always-on Hermes gateway GPU reservation with
  documented opportunistic GPU jobs guarded by host workload checks, low
  process priority, and preemption for games/Plex; keep passwordless pod sudo
  non-interactive.
- [78e8f5a9](https://github.com/example-org/hermes-agent-private/commit/78e8f5a9) -
  Switch the local Kubernetes deploy script to server-side apply and remove
  stale client-side ConfigMap last-applied annotations so the large embedded
  bootstrap ConfigMap can deploy without hitting Kubernetes annotation limits.
- [80331f71](https://github.com/example-org/hermes-agent-private/commit/80331f71) -
  Add an optional desktop bridge MCP with read-only screenshot/OCR/window
  observation by default, gated mouse/keyboard control, gated audio tools,
  pod bootstrap/image packaging, deployment docs, and regression tests.
- [0f76bc14](https://github.com/example-org/hermes-agent-private/commit/0f76bc14) -
  Carry pending-turn recovery context across repeated interrupted replays and
  add runtime apt/pip/npm install capture with promotion into declarative pod
  package lists.
- [3cb9f8fc](https://github.com/example-org/hermes-agent-private/commit/3cb9f8fc) -
  Tighten HTUI Pulse rows to `[HH:MM]B| event text`, remove padded badge/type
  columns, and enrich rows with model/provider, response usage, and tool
  duration metadata.
- [b39f9fbf](https://github.com/example-org/hermes-agent-private/commit/b39f9fbf) -
  Bake the Hindsight API runtime into the pod image, keep a persistent fallback
  runtime, tighten BOOT startup checks, fix the gateway drain hook, document
  Pulse journaling boundaries, and include interrupted TUI turn recovery.
- [0b7c27c0](https://github.com/example-org/hermes-agent-private/commit/0b7c27c0) -
  Lower the local llama admission limit to 42K tokens, keep proxy compaction
  disabled by default, add an explicit summary model option, and default
  delegation back to single-card local mode.
- [b68a1de5](https://github.com/example-org/hermes-agent-private/commit/b68a1de5) -
  Preserve leading and trailing whitespace in Pulse stream deltas so coalesced
  live text does not glue words together.
- [9f28096d](https://github.com/example-org/hermes-agent-private/commit/9f28096d) -
  Document auxiliary model routing, compression model choice, and clarify the
  auxiliary configuration menu wording.
- [27346c11](https://github.com/example-org/hermes-agent-private/commit/27346c11) -
  Document public reproducibility boundaries, add a public values template, and
  align public starter defaults with the current conservative deployment
  posture.
- [c4ab0a96](https://github.com/example-org/hermes-agent-private/commit/c4ab0a96) -
  Add a general Hermes research best-practices skill for source quality,
  stack-aware evidence gathering, and synthesis.
- [95eb79ba](https://github.com/example-org/hermes-agent-private/commit/95eb79ba) -
  Expose compaction artifact recall tools for current-session compressed
  context recovery.
- [2ae07d20](https://github.com/example-org/hermes-agent-private/commit/2ae07d20) -
  Tighten HTUI Pulse display with compact timestamps, LLM badges, stream
  coalescing, and duplicate-noise suppression.
- [bf6b44e9](https://github.com/example-org/hermes-agent-private/commit/bf6b44e9) -
  Add compaction artifacts and calibrated estimates.
- [7376dc4e](https://github.com/example-org/hermes-agent-private/commit/7376dc4e) -
  Keep YOLO opt-in and require git commits.
- [fe2ee8fd](https://github.com/example-org/hermes-agent-private/commit/fe2ee8fd) -
  Make YOLO approval mode explicit.
- [262aa3ca](https://github.com/example-org/hermes-agent-private/commit/262aa3ca) -
  Collapse expanded skill pending turns.
- [c9ad37c0](https://github.com/example-org/hermes-agent-private/commit/c9ad37c0) -
  Document evolved operations and recovery.
- [2bd3e16d](https://github.com/example-org/hermes-agent-private/commit/2bd3e16d) -
  Recover interrupted TUI turns.
- [8ded5a6f](https://github.com/example-org/hermes-agent-private/commit/8ded5a6f) -
  Persist client Pulse gateway events.
- [d1b94ed6](https://github.com/example-org/hermes-agent-private/commit/d1b94ed6) -
  Improve Pulse panel responsive layout.
