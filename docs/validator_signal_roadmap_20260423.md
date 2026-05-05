# Validator Signal Roadmap

Hermes now returns a richer post-edit validation block from file patch flows:

- `lint`: existing syntax/static-check result
- `formatter`: canonical-format check without rewriting files
- `status`: aggregate `ok` / `error`
- `blocking_failures`: failed validation checks
- `passed_checks`: checks that passed
- `skipped_checks`: checks skipped because no tool was available

Current implementation lives in:

- `tools/file_operations.py`
- `tools/patch_parser.py`

## What This Enables

These signals make it possible to treat code edits as something stronger than
"tool returned success".

The first downstream layer is now implemented:

- benchmark rows record validation, formatter, and lint failure counts
- benchmark summaries expose a `validator` rubric block
- the scorecard renders a `Validator` column
- queue-aware routing can now escalate validation-failure retries into the
  validator route class
- the gateway now extracts validation failures from real tool-result messages,
  stores a one-shot per-session validation hint, and feeds it into the next
  route selection so repair-follow-up turns can auto-escalate

The next layer should keep extending validator output in three places:

1. Routing

- Done for one-turn gateway carryover.
- A turn that ends with blocking validation failures now leaves behind a
  session-scoped hint containing validation, formatter, and lint failure counts.
- Repair-shaped follow-up turns consume that hint and can route as `validator`
  even if the user message itself is short like "retry that patch".
- Unrelated next-turn messages suppress the hint instead of consuming it, so a
  casual follow-up like a status question does not get accidentally escalated.
- The hint expires automatically after a short TTL if no repair follow-up arrives.
- Session resets and other true session-boundary operations clear that hint so
  it cannot leak into a fresh conversation.
- Next improvement is richer policy on when to retain or suppress that carryover
  for ambiguous follow-up messages.

2. Benchmarking

- Done for the current deterministic harness and scorecard.
- Next improvement is task-level breakdowns for "edit succeeded but validator
  failed" versus "edit itself failed".

3. Repair Loops

- Feed `blocking_failures` directly back into the model instead of asking it to
  infer what went wrong from a diff alone.
- Treat formatter drift as a lightweight repair target before escalating to a
  stronger model.

## Next Technical Layer

The next technical layer should add optional semantic diagnostics:

- Python: `pyright`
- JS/TS: `tsc --noEmit`, `eslint`
- Rust: `cargo check`, `clippy`
- Go: `go test`, `go vet`
- LSP diagnostics where a language server is available

Those should extend the existing `validation` block rather than introducing a
separate schema.
