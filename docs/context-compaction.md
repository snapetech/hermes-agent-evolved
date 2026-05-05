# Context Compaction

Hermes compaction is designed as a **lossless archive plus lossy live prompt**
system.

The live prompt cannot keep an unlimited transcript. When pressure gets high,
Hermes replaces older turns with a structured handoff summary. The exact
compacted span is archived in SQLite as a compaction artifact so later turns can
recover details with tools instead of relying entirely on the summary.

## Goals

- Keep long sessions below provider context limits.
- Avoid losing task state, file paths, commands, errors, and user asks.
- Compact early enough to avoid provider/admission-proxy failures.
- Avoid compacting on a soft threshold when the summary model is unavailable.
- Make compacted current-session context recoverable without searching unrelated
  past sessions.

## Flow

1. Hermes estimates the request size before an API call.
2. The estimate is adjusted by a rolling provider/model calibration multiplier
   learned from previous actual `prompt_tokens`.
3. If the calibrated estimate crosses the effective threshold, preflight
   compaction may run.
4. The compressor chooses a middle span:
   - protects the configured head messages,
   - protects the latest user ask,
   - protects a dynamic recent tail by token budget,
   - avoids splitting tool-call/tool-result groups.
5. Before LLM summarization, Hermes builds a deterministic extractive
   checkpoint from the selected span:
   - user asks,
   - tool calls and arguments,
   - tool result summaries and excerpts,
   - file paths,
   - commands,
   - error excerpts,
   - assistant notes.
6. The summary model receives both the serialized transcript span and the
   deterministic checkpoint.
7. Hermes validates that critical checkpoint facts reached the summary.
8. The live prompt receives the summary and recent tail.
9. The raw compacted span, checkpoint, summary, validation metadata, and trigger
   event are stored as a `compaction_artifacts` row.

## Lossless Archive

Compaction artifacts are stored in `state.db`:

- `source_session_id`: session that held the original raw span.
- `continuation_session_id`: new session created after compaction.
- `summary`: summary injected into the live prompt.
- `checkpoint_json`: deterministic extractive checkpoint.
- `raw_messages_json`: exact messages removed from the live prompt.
- `validation_json`: cheap validation result.
- `event_json`: trigger/source/token metadata.

The old session transcript also remains in the normal `messages` table. The
artifact table is a focused index over exactly what compaction removed.

## Retrieval Tools

Two tools recover compacted current-session context:

- `compaction_search`: searches artifacts in the active session lineage only.
- `compaction_expand`: expands one artifact and can return exact raw messages.

Use these when a detail probably happened earlier in the same long session but
is missing from the live prompt. Use `session_search` for unrelated historical
sessions.

## Timing

The baseline trigger is:

```yaml
compression:
  threshold: 0.50
```

This means compact near 50% of the detected model context window. Hermes may
trigger earlier when recent tail activity contains tool calls or reasoning, so
there is enough room for the next tool burst.

The recent tail budget is:

```yaml
compression:
  target_ratio: 0.20
  protect_last_n: 20
```

`target_ratio` controls how much of the threshold is reserved for recent context.
`protect_last_n` is a message-count floor; token budget is the primary control.

## Failure Policy

There are two compaction modes:

```yaml
compression:
  soft_static_fallback: false
  forced_static_fallback: true
```

Soft compaction happens at preflight or after a normal response. If the summary
model is unavailable and `soft_static_fallback` is false, Hermes skips
compaction. This avoids dropping live context just because a background summary
call failed.

Forced compaction happens after a provider/admission-proxy overflow. If the
request cannot be sent as-is, Hermes may use a static fallback summary containing
the deterministic checkpoint. This still shrinks the live prompt while keeping
the exact raw span archived when session storage is available.

## Archive Knob

```yaml
compression:
  artifacts_enabled: true
```

When enabled, compaction artifacts are persisted and searchable. Disabling this
returns Hermes to pure live-prompt summaries plus normal parent session logs.
Leave this enabled unless storage size is more important than recoverability.

## Summary Validation

Validation is intentionally cheap. It checks whether important deterministic
checkpoint facts appear in the summary:

- file paths,
- commands,
- error excerpts,
- latest user ask representation.

Validation warnings are recorded in compaction telemetry. They do not block
forced compaction because provider overflow still needs a smaller prompt.

## Telemetry

`/compaction` shows trigger/source counts, archived artifact counts, validation
warnings, token estimates, and artifact ids for recent compactions.

Useful signals:

- frequent admission-proxy retries: lower `threshold`,
- many validation warnings: use a stronger/faster compression model,
- repeated skipped soft compactions: check auxiliary compression provider,
- poor timing: allow a few turns for estimate calibration or lower threshold.

## Auxiliary Model Choice

Compression is one of the highest-leverage auxiliary routes. A weak compression
model can silently damage the live prompt, while a slow or unavailable model can
cause repeated soft-compaction skips. The recommended hierarchy is:

- local long-context model when it is reliable and can fit the compression span,
- Codex or another strong subscribed model when local quality or uptime is poor,
- free aggregator models only for experiments or non-critical sessions.

For the current workstation profile, `auxiliary.compression` is pinned to local
Qwen and the exact compacted spans are archived. See
[`docs/auxiliary-model-routing.md`](auxiliary-model-routing.md) for the full
task-by-task routing matrix.

## Design Decisions

- **Summary is not the source of truth.** It is an index card for the live
  prompt; raw archived messages are the source of truth.
- **Current-lineage recall is separate from cross-session recall.**
  `compaction_search` searches only the current compressed lineage, while
  `session_search` remains for older unrelated sessions.
- **Soft failures should not cause data loss.** Preflight compaction can skip if
  summarization fails.
- **Forced failures need a smaller prompt.** Provider overflow may require
  extractive fallback to make forward progress.
- **Token timing should learn.** Rough estimates are calibrated against actual
  provider usage to improve future timing.
