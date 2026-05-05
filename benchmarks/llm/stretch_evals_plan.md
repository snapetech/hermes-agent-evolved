# Stretch eval plan

Captured 2026-04-28 during the ctx-sweep refactor. These are evals we have
*decided to run next time* — not in the current sweep. Per-eval the doc
records: why we picked it, how it slots into the existing scorecard axes,
the dataset/source we will use, an estimated wallclock on the 7900 XT, and
any infra or prep we need to stage before kickoff.

## Decision

| Eval | Status | Bench axis | Notes |
|---|---|---|---|
| GPQA Diamond | **Adopt next run** | model | 198 MCQ items, no tools, ~30 min/model on 7900 XT. Pairs with the existing rubric. |
| MMLU-Pro | **Adopt next run, optional** | model | ~12k items but cheap; gives a wide-coverage knowledge ranking that the rubric does not cover. |
| MuSR | **Adopt next run, optional** | model | Multi-step reasoning, longer prompts (~3-8k tokens) — dovetails with the ctx sweep so we get reasoning-vs-context curves cheaply. |
| MCP Atlas Public | **Adopt next run, separate scorecard** | system | Tests the whole Hermes loop (router + MCP servers), not the model. Must live in its own scorecard so model regressions don't get blamed on harness changes. |
| HLE (with or without tools) | Reject | model | Floor effect; sub-70B local models score 3-8%, signal swamped by noise. |
| Terminal Bench 2.0 | Defer | system | Heavy infra (containers, real shell). Reconsider once the agent loop is the variable we want to test. |
| SWE Bench Pro / SWE Pro | Reject for general models | system | Local sub-70B scores 1-3%, runtime in days. Maybe a 50-task subset for Qwen3-Coder 30B only. |
| BrowseComp | Reject | system | Needs live web + browser tools, nondeterministic, off-mission for the local-model bench. |

## Per-eval prep notes

### GPQA Diamond

- Dataset: HuggingFace `Idavidrein/gpqa`, `gpqa_diamond.csv` split (198 rows).
- Format: 4-choice MCQ. Score = exact letter match.
- Prompt protocol: zero-shot, system message "Answer with a single letter A/B/C/D." Use `temperature=0`, `max_tokens=8`.
- Runtime: ~10-15 min/model on 7900 XT for 35B-A3B at ctx=8k.
- Integration: add a new task type to `benchmarks/llm/run_full_matrix_refresh.sh`. Score belongs under a new `Knowledge` axis in `model_benchmark_rubric.md` (separate from existing `Logic`).
- Pre-req: nothing — runs over the existing `chat/completions` endpoint at any ctx.

### MMLU-Pro (optional)

- Dataset: HuggingFace `TIGER-Lab/MMLU-Pro` (12,032 rows, 14 subject buckets).
- Format: 10-choice MCQ. Score = exact letter match.
- Prompt protocol: zero-shot CoT with `Final answer: <letter>` extraction. `temperature=0`, `max_tokens=512` for CoT, parse trailing letter.
- Runtime: ~3-4 hr/model on 7900 XT — gate behind `RUN_MMLU_PRO=1`.
- Integration: bucket-level scoring (mean over subjects) into the existing scorecard's `Knowledge` axis as a tier-2 row.

### MuSR (optional)

- Dataset: HuggingFace `TAUR-Lab/MuSR` (~750 multi-step reasoning items: murder mystery, object placement, team allocation).
- Format: free-form answer, scored by exact-string match against the canonical answer.
- Prompt protocol: zero-shot CoT, `max_tokens=1024`, `temperature=0`.
- Runtime: ~30 min/model on 7900 XT.
- Why it's interesting *here*: prompts are 3-8k tokens — gives a midcontext reasoning signal that complements the existing 32k/128k/240k throughput probes.

### MCP Atlas Public

- Dataset: Anthropic's public MCP Atlas split (TBD — confirm exact source before running).
- Format: agentic — model is given a task and a constellation of MCP tools, scored on whether it completes the task.
- Prompt protocol: must run through the full Hermes agent loop (gateway + tool router + MCP servers).
- Runtime: hard to estimate without infra. Plan to run the smallest 25-task subset first.
- Integration: **new scorecard file** (`mcp_atlas_scorecard.md`) — do *not* mix into `model_benchmark_scorecard.md`. The numbers measure the harness, not the model.
- Pre-req: stand up the public MCP servers used by the bench under our gateway. Likely gated behind a separate `benchmarks/agent/run_mcp_atlas.sh` script.

## Open issues to resolve before next run

### Long-context probe data quality

Discovered while running the ctx sweep on 2026-04-28: at ctx ≥ 98k the
flash-attention scratch buffer plus KV cache exhausts the 20 GB on the
7900 XT once the prompt clears ~60k tokens. The llama-server crashes
mid-probe (HIP `cudaMalloc failed` inside `launch_fattn`), and every
remaining row in the cell errors with ECONNREFUSED. Repro cells in
`benchmark_runs/ctx_sweep_20260428T154552Z/`.

Follow-up: `benchmarks/llm/run_ctx_sweep.sh` now implements option 2. Each
`(mode, fill)` probe runs in its own `llama_longctx_probe.py` invocation,
the server is health-checked before the next pair, and a crash at fill `N`
sets a per-cell crash floor that skips later fills `>= N`.

Remaining options for future cleanup:

1. **Trim `fill_levels_for`** so the largest fill never exceeds ~60k tokens
   regardless of ctx — gives clean data but loses the "fill-to-capacity"
   signal we wanted at ctx=128k+.
2. **Drop KV cache to q4_0 for qwen3.6 too** (currently q8_0) — frees
   ~1 GB but still crashes at ctx=131k + 245k-char fill in our gemma4
   cells, so this alone is insufficient.

Likely answer: keep the restart-per-pair behavior, then test q4_0 KV for
qwen3.6 in a short smoke before the next full sweep.

#### 2026-04-28 Qwen 3.6 follow-up results

Target: find a Hermes context setting with real margin above the 65k minimum
window while keeping the 9070 XT disabled.

- `ctx=98304`, all layers on 7900, `q4_0/q4_0` KV, flash-attn on:
  failed at 286,720 chars before token accounting; 245,760 chars was still
  safe (~57.4k prompt tokens). Not enough margin.
- `ctx=73728`, all layers on 7900, `q4_0/q4_0` KV, flash-attn on:
  266,240 chars passed (~62.2k prompt tokens), 286,720 chars crashed. Still
  below the 65k target.
- `ctx=98304`, `q4_0/q4_0` KV, flash-attn on, `--gpu-layers 36`:
  passed needle at 76.5k prompt tokens and synthesis at 67.0k prompt tokens.
  This is the first tested config with acceptable context margin, but it is
  much slower: prompt eval ~640-700 tok/s at long fills, decode ~25-32 tok/s.
  The 7900 XT junction reached ~100-106 C during the long rows, so do not
  run this route continuously without fan/thermal tuning.

### Display-GPU topologies (`gemma4_split`, `gemma4_cpumoe`)

These are now gated behind `ALLOW_DISPLAY_GPU=1`. To run them safely:

- Switch to a TTY (`Ctrl+Alt+F3`), log in, then `ALLOW_DISPLAY_GPU=1
  ONLY=gemma4_split bash benchmarks/llm/run_ctx_sweep.sh` — Wayland is not
  active so a 9070 XT hang only kills the framebuffer, not a session with
  open work.
- Or run from SSH after stopping the desktop session.
- Never run these from inside a Hyprland/Wayland session you care about.
