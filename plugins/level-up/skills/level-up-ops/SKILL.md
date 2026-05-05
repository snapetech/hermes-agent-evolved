---
name: level-up-ops
description: How to use the level-up plugin surfaces — recovery recipes, escalation channels, memory harvest/promotion, boot checks, audits, TaskPacket, LSP tool, and the shared-memory MCP bridge.
---

# Level-Up Ops

The `level-up` plugin adds operational surfaces that run continuously in the
Hermes cluster deployment. This skill is the operator-facing reference
for using them well.

State root: `$HERMES_HOME/level_up/` (normally `/opt/data/level_up/`).

---

## 1. Recovery recipes

Runs as a `post_tool_call` hook. Every failed tool call is classified
into a stable category and a recipe step is advanced:

| Category               | Recipe |
|------------------------|--------|
| `backend_timeout`      | retry_same → retry_different_backend → escalate |
| `backend_unreachable`  | retry_different_backend → escalate |
| `tool_crash`           | retry_same → simplify_strategy → escalate |
| `tool_output_invalid`  | simplify_strategy → escalate |
| `context_overflow`     | compact_context → retry_same → escalate |
| `strategy_exhausted`   | escalate |
| `approval_timeout`     | escalate |
| `workspace_conflict`   | escalate |
| `permission_denied`    | escalate |
| `network_error`        | retry_same → escalate |
| `unknown`              | retry_same → escalate |

Events are appended to `$HERMES_HOME/level_up/recovery.jsonl`. When the
recipe exhausts, `escalate()` fires through the configured channel.

### Using it
- Inspect recent failures: `/recovery [limit]` (default 10).
- After a tool fails, the recipe tells you what the *next* reasonable
  recovery step is — follow it rather than improvising a new retry.
- If you see repeated failures for the same category on the same tool,
  stop and fix the underlying cause (bad args, missing env, wrong
  permissions) rather than cycling the recipe.

---

## 2. Escalation channels

API: `from plugins.level_up.escalation import Escalation, escalate`.
Always writes one line to `$HERMES_HOME/level_up/escalations.log`, then
delivers to the configured default channel.

### Config — `$HERMES_HOME/level_up/escalation.yaml`

```yaml
default: file        # or: discord, <any named channel>
channels:
  file:
    type: file
    path: $HERMES_HOME/level_up/escalations.log
  discord:
    type: discord
    channel: home
  ntfy:
    type: webhook
    url: https://ntfy.sh/my-topic
    headers: {Title: "Hermes"}
```

### Using it
- Call `escalate(Escalation(reason=..., category=..., severity="error"))`
  for conditions that should interrupt the operator asynchronously.
- Bursts are rate-limited by category: after 5 alerts in 5 minutes,
  follow-up alerts are collapsed into a suppressed-count summary.
- Prefer `severity="info"` for completion notifications and
  `"warn"`/`"error"` for anything that needs attention.
- The file log is the authoritative audit trail — always check it before
  asking the user about a past alert.

---

## 3. Memory harvest

Runs on `on_session_end` and via `/harvest [N]`. Uses the `auxiliary.
compression` model to extract durable knowledge from each session's
message history and writes **proposals** (not live memories) to:

- `$HERMES_HOME/level_up/harvest/facts.jsonl`
- `$HERMES_HOME/level_up/harvest/corrections.jsonl`
- `$HERMES_HOME/level_up/harvest/avoid.jsonl`

All entries start with `"status": "proposed"`. Nothing is injected into
active prompts until an operator promotes it.

### Using it
- Manual run: `/harvest 5` to harvest the 5 most-recent sessions.
- Review flow: tail each JSONL, decide which entries to promote, then use
  `/promote <kind> <line-or-id> [memory|user|soul|hindsight]`.
- Promotion appends to `MEMORY.md`, `USER.md`, `SOUL.md`, or Hindsight
  and rewrites the JSONL entry with `"status": "promoted"`.
- Keep the file small — prune anything older than ~30 days that was
  never promoted.

---

## 4. Correction-aware approval elevation

`pre_tool_call` hook. Before any `terminal`, `execute_code`, or
file-write tool call, compare the call's text against prior corrections,
avoid-patterns, and `/decide` records. If overlap score ≥ 0.45 the call
is **blocked with a reminder**, not silently run.

Block message format:

```
level-up correction-guard: a prior {correction|decision|avoid} overlaps
this call (score=0.54). Re-read it before proceeding.
Prior note: <first 240 chars of the matching entry>
```

### Using it
- When blocked, **read the prior note**. If it still applies, change the
  command. If it's stale, remove the offending entry from
  `corrections.jsonl` / `avoid.jsonl` / `decisions.jsonl` before
  retrying.
- Simple in-container `apt`/`apt-get update` and `install` chains are
  intentionally exempt so short-lived runtime dependencies can be installed
  in the managed Hermes pod. They still do not survive pod replacement; bake
  durable system dependencies into the image.
- Do not try to phrase around the guard — the overlap is term-based and
  renaming variables doesn't change the underlying decision.
- The guard is silent on non-gated tools; it is not a substitute for
  general safety review.

---

## 5. Closed-loop self review

`/self-review [days]` scans recent:

- `$HERMES_HOME/level_up/recovery.jsonl`
- `$HERMES_HOME/level_up/tool_metrics.jsonl`

It clusters repeated failures and does three things:

1. auto-applies a very small set of low-risk lessons
2. appends those lessons to the harvest corpus with `status=auto_applied`
3. writes a review queue for anything that still needs judgment

Current output files:

- `$HERMES_HOME/level_up/review_queue.jsonl`
- `$HERMES_HOME/level_up/self_review_status.json`
- `$HERMES_HOME/level_up/self_review_status.md`
- `$HERMES_HOME/level_up/self_review_runs.jsonl`

Current low-risk auto-apply rules:

- repeated git branch mismatch from assuming `main`/`master`
- repeated `not a git repository` failures
- repeated cron/send-message misuse patterns

Everything else stays in the review queue.

Cron-safe entrypoint:

```bash
/app/.venv/bin/python -m plugins.level_up.self_review --days 7
```

Use this for nightly or weekly review. Keep it conservative; this loop is
for guardrails and recurring operator corrections, not autonomous large
behavioral rewrites.

---

## 6. TaskPacket — structured `/task`

A contract-driven wrapper around `delegate_task`. Parent agents supply a
packet; the child runs, then acceptance tests run, then results are
logged to `$HERMES_HOME/level_up/tasks.jsonl` and optionally escalated.

### Packet shape (YAML or JSON)

```yaml
objective: Refactor bootstrap-runtime.sh to split secret loading into its own function.
scope: deploy/k8s/bootstrap-runtime.sh
acceptance_tests:
  - shellcheck deploy/k8s/bootstrap-runtime.sh
  - bash -n deploy/k8s/bootstrap-runtime.sh
commit_policy: none        # none | squash | per-step
escalation_policy: on-failure  # never | on-failure | always
max_wall_time: 900
toolsets: [code, terminal]
max_diff_lines: 400
forbid_new_deps: true
files_touched_must_match: deploy/k8s/**
context: >-
  Keith wants the secret-mounting section extracted into a reusable function.
```

### Using it
- Invoke via `/task` with the packet body.
- `acceptance_tests` are plain shell commands run after the child exits.
  Keep them fast and deterministic — no network, no side effects.
- For multi-step work, prefer many small packets over one big one; the
  parent never sees intermediate reasoning, only the report.
- The delegate's output is trimmed to the first 1200 chars in the log,
  and the first 600 chars appear in the reply only on failure.
- Quality gates run after acceptance tests and can fail the packet even
  when shell tests pass.

---

## 7. LSP tool

Registered as `lsp`. A stdio Language Server Protocol client that
spawns the right server per language on first use. Config override at
`$HERMES_HOME/level_up/lsp.yaml`:

```yaml
servers:
  python: {command: pyright-langserver, args: [--stdio], languages: [python]}
  typescript: {command: typescript-language-server, args: [--stdio], languages: [typescript, javascript, tsx, jsx]}
  rust: {command: rust-analyzer, args: [], languages: [rust]}
  go: {command: gopls, args: [], languages: [go]}
```

### Actions

| Action              | Required args                         |
|---------------------|---------------------------------------|
| `definition`        | `path`, `line`, `character`           |
| `references`        | `path`, `line`, `character`           |
| `hover`             | `path`, `line`, `character`           |
| `symbols`           | `path`                                |
| `workspace_symbols` | `query`, `language`                   |

Line and character are **0-indexed**. Paths must be absolute. Returns
raw LSP JSON under `{"ok": true, "result": ...}` or
`{"ok": false, "error": ...}`.

### Using it
- Prefer `lsp` over grep when you need *semantic* information: "where is
  this symbol defined", "every place it's called", "types at cursor".
- Use `workspace_symbols` to jump to a declaration by name across the
  repo without knowing its path.
- If the server is not installed, you get a clear error — install it in
  the workspace venv / npm globals and retry; the client reuses a live
  server for the life of the process.

---

## 7. Boot check

`/boot-check` runs deterministic BOOT.md-style startup checks without
asking the model to remember the checklist:

- `kubectl get pods -n hermes` and flags non-running pods.
- Reads `$HERMES_HOME/cron/jobs.json` and flags `last_status != ok`.
- Checks the local Ollama endpoint on `localhost:11434`.

If everything is clean it returns exactly `[SILENT]`.

---

## 8. Audits and hygiene

- `/skill-audit` scans every `SKILL.md`, `MEMORY.md`, and `SOUL.md` it
  can see for stale local path references.
- `/skill-audit --urls` also checks HTTP(S) references with short
  HEAD/GET probes.
- `/decision-hygiene` checks `$HERMES_HOME/decision_memory/decisions.jsonl`
  for entries older than 90 days and high-overlap pairs in the last 50
  decisions.

---

## 9. Tool metrics

Every `post_tool_call` writes compact telemetry to
`$HERMES_HOME/level_up/tool_metrics.jsonl`:

- tool name
- duration in seconds
- result size
- argument keys
- session/task/tool-call identifiers

---

## 10. Shared-memory MCP bridge (cross-CLI)

`/opt/data/shared-memory-mcp.py` is a stdio MCP server that exposes
Hermes's Hindsight bank and level-up corpora to sibling coding-agent
CLIs in the pod (`claude`, `codex`, `cursor-agent`).

### Tools exposed
- `memory.retain(content, context?)` — store in Hindsight.
- `memory.recall(query)` — semantic search.
- `memory.reflect(query)` — synthesize an answer from memory.
- `memory.add_decision(text)` — append to `decisions.jsonl`.
- `memory.list(kind, limit?)` — tail `decisions|corrections|avoid|facts`.

### Resources exposed (read-only)
- `hermes://decisions`
- `hermes://corrections`
- `hermes://avoid`
- `hermes://facts`
- `hermes://escalations`

### Using it
- From inside Hermes you do **not** call this server directly — you
  already have the native `hindsight_retain` / `hindsight_recall` tools
  and the raw JSONL paths. Use those.
- When you spawn `claude` / `codex` / `cursor-agent` inside the pod,
  ensure their config file contains the `hermes-memory` MCP server
  entry (see deploy/k8s/README.md). Then they share your memory and
  institutional decisions.
- If a sibling CLI records a new decision via `memory.add_decision`, it
  appears in your own `/decisions` list immediately — no sync job.

---

## Operational rhythm

1. Tool fails → recovery hook records it → follow the recipe step.
2. Session ends → harvest proposes memories → review next session start.
3. Promote useful harvest entries with `/promote` instead of hand-editing
   JSONL status.
4. Before risky tool calls, trust the correction guard — re-read the
   prior note before overriding.
5. For multi-step delegations, wrap in `/task` with acceptance tests and
   quality gates rather than free-form `delegate_task`.
6. For cross-CLI work, make sure siblings have the MCP bridge wired so
   memory is shared, not duplicated.

State paths to know:

- `$HERMES_HOME/level_up/recovery.jsonl`       — recovery events
- `$HERMES_HOME/level_up/tasks.jsonl`          — TaskPacket log
- `$HERMES_HOME/level_up/tool_metrics.jsonl`   — tool latency/result-size log
- `$HERMES_HOME/level_up/escalations.log`      — every escalation (audit)
- `$HERMES_HOME/level_up/escalation.yaml`      — channel config
- `$HERMES_HOME/level_up/lsp.yaml`             — LSP server overrides
- `$HERMES_HOME/level_up/harvest/{facts,corrections,avoid}.jsonl`
- `$HERMES_HOME/decision_memory/decisions.jsonl` (from runtime-control, read by correction guard)
