# Local Model Benchmark Scorecard

Consolidated rerun scorecard from clean runs on 2026-04-23, with split-card
Qwen3.6 27B throughput backfill from 2026-04-29. Primary quality source is
`benchmark_runs/full_matrix_clean_20260423T2350Z`; these are local Hermes
task-suite scores, not community benchmarks. Three earlier clean
small-model rows come from `benchmark_runs/full_matrix_clean_20260423T2315Z`
because those lanes were already complete there. This file is the canonical
scorecard; the older dated scorecard has been merged here and removed.

Baseline: `qwen3.6-35b-a3b:iq4xs`
Target generation speed for offload/split experiments: `30` tok/s
Quality uplift target: `2x` baseline pass-rate ratio

Routing decision as of 2026-04-29: use `gemma4-26b-a4b-it:q4km` as the local
primary workhorse. Keep `qwen3.6-35b-a3b:iq4xs` as the fast utility fallback.
Keep Qwen3.6 27B split-card rows experimental until Hermes quality scores exist.

## How To Read This

- [Pass](../../scripts/hermes_model_benchmark.py#L79): total Hermes task-suite passes. A full quality row is `81 = 27 tasks x 3 repetitions`.
- [Safety](../../scripts/model_benchmark_scorecard.py#L21): approval, routing, mutation-guard, admission/compaction, failover, and read-only risk tasks. Failures here block approval-adjacent routing.
- [Logic](../../scripts/model_benchmark_scorecard.py#L68): small deterministic reasoning and JSON-rule tasks.
- [Utility](../../scripts/model_benchmark_scorecard.py#L38): operator routing, JSON extraction, status summaries, queue/fallback decisions, and service-command extraction.
- [Agentic](../../scripts/model_benchmark_scorecard.py#L55): file truth, code edits, synthesis, and gateway-style operator reply tasks.
- [Reliability](../../scripts/model_benchmark_scorecard.py#L92): stability score after penalizing flaky tasks, timeouts, runner errors, tool failures, and validation failures.
- [Validator](../../scripts/model_benchmark_scorecard.py#L141): post-edit cleanliness score from syntax, formatter, lint, and task-specific file validators.
- `Quality x`: pass-rate ratio versus the baseline `qwen3.6-35b-a3b:iq4xs`.
- `Speed x`: generation throughput ratio versus the same baseline.

Model suffixes describe where the row ran:

- `-7900`: single-card run pinned to the RX 7900 XT.
- `-9070`: single-card or guarded candidate run pinned to the RX 9070 XT, which is also the display GPU on this workstation.
- `-split`: two-card llama.cpp layer split with the 7900 XT first/main and the 9070 XT as sidecar.
- `bf16-7900-offload`: BF16 diagnostic using partial 7900 XT offload; it is not an operational route.

## Runtime Build / Tuning

llama.cpp was rebuilt from the adjacent `llama.cpp` checkout into `build-hip`
at commit `9e5647aff` with ROCm/HIP enabled for both local AMD GPU targets:

```bash
HIPCXX="$(hipconfig -l)/clang" HIP_PATH="$(hipconfig -R)" \
cmake -S . -B build-hip \
  -DGGML_HIP=ON \
  -DAMDGPU_TARGETS="gfx1100;gfx1201" \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=ON \
  -DGGML_HIP_GRAPHS=OFF \
  -DGGML_HIP_NO_VMM=ON \
  -DGGML_HIP_ROCWMMA_FATTN=OFF \
  -DGGML_HIP_MMQ_MFMA=ON \
  -DGGML_HIP_RCCL=OFF \
  -DGGML_HIP_EXPORT_METRICS=OFF
cmake --build build-hip --config Release -- -j 32
```

`gfx1100` covers the RX 7900 XT. `gfx1201` covers the RX 9070 XT. ROCm reports
the display 9070 XT before the 7900 XT by default, so split tests explicitly
pin device visibility by UUID and present the 7900 XT as `ROCm0`:

```bash
ROCR_VISIBLE_DEVICES=GPU-6bdce6ea1d388c5c,GPU-2388c382a826700f
HIP_VISIBLE_DEVICES=0,1
```

Split-card Qwen rows use a guarded llama-server launch:

```bash
ionice -c 3 nice -n 19 llama-server \
  --ctx-size 8192 \
  --parallel 1 \
  --batch-size 1024 \
  --ubatch-size 128 \
  --gpu-layers 999 \
  --flash-attn on \
  --cache-type-k q4_0 \
  --cache-type-v q4_0 \
  --cache-ram 0 \
  --device ROCm0,ROCm1 \
  --split-mode layer \
  --tensor-split 12,8 \
  --main-gpu 0 \
  --fit on \
  --fit-target 768,4096 \
  --fit-ctx 8192 \
  --reasoning off \
  --jinja
```

The split quality backfill disables llama.cpp slot/prompt reuse and context
checkpointing because the earlier fault happened on that path during split-card
quality runs:

```bash
--no-cache-prompt \
--ctx-checkpoints 0 \
--checkpoint-every-n-tokens -1 \
--slot-prompt-similarity 0.0 \
--no-context-shift
```

The split runner also stops `hermes-llama-qwen36.service` and
`hermes-qwen-watchdog.timer` before the run, then restores them on exit. This
keeps the primary service from restarting onto the same GPUs mid-benchmark.

Rows are sorted by scored quality first, descending by `Pass`. For full quality
rows, `Logic + Utility + Agentic = Pass`. `Safety` is a cross-cutting gate
bucket and overlaps other tasks, so it should not be added to the total.
Throughput-only diagnostic rows are kept in the same table but marked `n/a`;
they are not quality-ranked.

The `Mode` column identifies the tested hardware or artifact source, not a
model family. `9070 candidate` rows ran on the RX 9070 XT candidate service.
`A380 backup candidate` rows ran on the separate Intel A380 backup host.

| Model | Mode | Gen tok/s | [Pass](../../scripts/hermes_model_benchmark.py#L79) | [Safety](../../scripts/model_benchmark_scorecard.py#L21) | [Logic](../../scripts/model_benchmark_scorecard.py#L68) | [Utility](../../scripts/model_benchmark_scorecard.py#L38) | [Agentic](../../scripts/model_benchmark_scorecard.py#L55) | [Reliability](../../scripts/model_benchmark_scorecard.py#L92) | [Validator](../../scripts/model_benchmark_scorecard.py#L141) | Prompt tok/s | Quality x | Speed x | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `gemma4-26b-a4b-it:q4km` | 7900 primary candidate | 26.14 | 67/81 | 17/24 | 4/9 | 34/42 | 29/30 | 0.65 | 1.00 | 189.05 | 1.20 | 0.36 | primary workhorse |
| `qwen3.6-27b:q5ks-9070` | 9070 guarded candidate | 4.46 | 60/81 | 18/24 | 3/9 | 32/42 | 25/30 | 0.66 | 1.00 | n/a | 1.07 | 0.06 | backup only; display GPU |
| `qwen3.6-27b:q4km-split` | 7900+9070 split | 17.78 | 58/81 | 18/24 | 0/9 | 34/42 | 24/30 | 0.68 | 1.00 | 758.33 | 1.04 | 0.24 | quality backfilled; below 30 tok/s |
| `qwen3.6-27b:q5ks-split` | 7900+9070 split | 18.52 | 58/81 | 18/24 | 3/9 | 30/42 | 25/30 | 0.55 | 1.00 | 751.74 | 1.04 | 0.25 | quality backfilled; below 30 tok/s |
| `qwen3.6-27b:q5ks-7900` | 7900 dense Qwen | 24.23 | 56/81 | 18/24 | 3/9 | 30/42 | 23/30 | 0.57 | 1.00 | n/a | 1.00 | 0.33 | Qwen-family fallback |
| `qwen3.6-35b-a3b:iq4xs` | 7900 baseline | 73.30 | 56/81 | 15/24 | 3/9 | 33/42 | 20/30 | 0.42 | 1.00 | n/a | 1.00 | 1.00 | fast utility fallback |
| `qwen3.5-9b:q6` | 9070 candidate | 60.33 | 54/81 | 15/24 | 3/9 | 31/42 | 20/30 | 0.58 | 1.00 | n/a | 0.96 | 0.82 | reject approval/routing |
| `gemma4-e4b-it:q8` | 9070 candidate | 60.79 | 45/81 | 15/24 | 3/9 | 27/42 | 15/30 | 0.34 | 1.00 | n/a | 0.80 | 0.83 | reject approval/routing |
| `qwen3.6-27b:q8-split` | 7900+9070 split | 17.15 | 42/81 | 18/24 | 3/9 | 31/42 | 8/30 | 0.39 | 1.00 | 926.53 | 0.75 | 0.23 | quality backfilled; below 30 tok/s |
| `qwen3.6-27b:q6k-split` | 7900+9070 split | 17.53 | 39/81 | 18/24 | 3/9 | 28/42 | 8/30 | 0.33 | 1.00 | 591.52 | 0.70 | 0.24 | quality backfilled; below 30 tok/s |
| `qwen3.5-4b:q8` | 9070 candidate | 78.59 | 36/81 | 7/24 | 3/9 | 19/42 | 14/30 | 0.36 | 1.00 | n/a | 0.64 | 1.07 | reject approval/routing |
| `qwen3-4b-instruct-2507:q4km` | A380 backup candidate | 17.00 | 36/81 | 7/24 | 3/9 | 16/42 | 17/30 | 0.21 | 1.00 | n/a | 0.64 | 0.23 | reject approval/routing |
| `smollm3:q4km` | A380 backup candidate | 19.80 | 22/81 | 10/24 | 4/9 | 18/42 | 0/30 | 0.00 | 1.00 | n/a | 0.39 | 0.27 | reject approval/routing |
| `lfm25-12b-instruct:q4km` | 9070 candidate | 235.85 | 20/81 | 6/24 | 6/9 | 14/42 | 0/30 | 0.18 | 1.00 | n/a | 0.36 | 3.22 | reject; short/no-tool outputs inflated speed |
| `ministral3-3b-instruct:q4km` | A380 backup candidate | 16.37 | 9/81 | 3/24 | 0/9 | 7/42 | 2/30 | 0.00 | 1.00 | n/a | 0.16 | 0.22 | reject approval/routing |
| `qwen3.6-27b:bf16-7900-offload` | 7900 partial offload | 1.34 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 26.25 | n/a | 0.02 | not scored; diagnostic only |

Open gaps / caveats:

- The Qwen3.6 27B split quality backfill is complete through Q8_0.
- BF16 has a throughput row only and is intentionally not quality-scored because generation is 1.34 tok/s on the partial-offload diagnostic path.
- Split-card Qwen3.6 27B throughput is now backfilled through Q8_0. These split rows used the guarded display-GPU recipe: 7900 XT first/main, 9070 XT sidecar, `--split-mode layer`, `--tensor-split 12/8`, `--gpu-layers 999`, `--ubatch 128`, `--cache-type-k q4_0`, `--cache-type-v q4_0`, and `--fit-target 768,4096`.
- BF16 was probed as a 7900-only partial-offload diagnostic. It loads and runs, but generation throughput is too low for an operational lane.
- The scorecard is still a local routing scorecard, not a public benchmark. The strict validators penalize verbose-but-semantically-close answers and any missed tool/file write.
- `lfm25-12b-instruct:q4km` reports very high throughput because the model mostly produced short/no-tool answers; quality and agentic scores should dominate routing decisions for that lane.
- `qwen3.6-27b:q5ks-9070` quality is strong, but throughput is only 4.46 tok/s on the tested 9070 path.

Operational routing:

- Primary 7900 XT workhorse: `gemma4-26b-a4b-it:q4km`.
- Fast local utility fallback: `qwen3.6-35b-a3b:iq4xs`.
- Qwen-family dense fallback: `qwen3.6-27b:q5ks-7900`.
- Split-card lane: `qwen3.6-27b:q5ks-split` remains explicit/provisional because it has throughput-only data and uses the display GPU.

Split/offload candidates should clear about 30 tok/s and show a quality gain
before they are worth production complexity. Throughput-only rows use direct
`llama-bench` `pp512/tg64` runs and should not be compared as quality
substitutes for OpenAI-compatible endpoint evaluations.

Category breakdown:

- `Pass`: `81 = 27 tasks x 3 reps`.
- `Safety`: `24 = 8 gate task types x 3 reps`.
- `Logic`: `9 = 3 task types x 3 reps`.
- `Utility`: `42 = 14 task types x 3 reps`.
- `Agentic`: `30 = 10 task types x 3 reps`.

Source artifacts:

- [`benchmark_runs/full_matrix_clean_20260423T2350Z/quality/results_20260423_180129.json`](../../benchmark_runs/full_matrix_clean_20260423T2350Z/quality/results_20260423_180129.json)
- [`benchmark_runs/full_matrix_clean_20260423T2350Z/quality/results_20260423_184507.json`](../../benchmark_runs/full_matrix_clean_20260423T2350Z/quality/results_20260423_184507.json)
- [`benchmark_runs/full_matrix_clean_20260423T2350Z/parallel_9070/quality/results_20260423_203141.json`](../../benchmark_runs/full_matrix_clean_20260423T2350Z/parallel_9070/quality/results_20260423_203141.json)
- [`benchmark_runs/full_matrix_clean_20260423T2315Z/quality/results_20260423_172010.json`](../../benchmark_runs/full_matrix_clean_20260423T2315Z/quality/results_20260423_172010.json)
- [`benchmark_runs/full_matrix_clean_20260423T2315Z/quality/results_20260423_173512.json`](../../benchmark_runs/full_matrix_clean_20260423T2315Z/quality/results_20260423_173512.json)
- [`benchmark_runs/full_matrix_clean_20260423T2315Z/quality/results_20260423_175805.json`](../../benchmark_runs/full_matrix_clean_20260423T2315Z/quality/results_20260423_175805.json)
- [`benchmark_runs/full_matrix_clean_20260423T2350Z/quality/results_20260423_214627.json`](../../benchmark_runs/full_matrix_clean_20260423T2350Z/quality/results_20260423_214627.json)
- [`benchmark_runs/full_matrix_clean_20260423T2350Z/quality/results_20260423_215157.json`](../../benchmark_runs/full_matrix_clean_20260423T2350Z/quality/results_20260423_215157.json)
- [`benchmark_runs/full_matrix_clean_20260423T2350Z/parallel_a380/quality/results_20260423_203200.json`](../../benchmark_runs/full_matrix_clean_20260423T2350Z/parallel_a380/quality/results_20260423_203200.json)
- [`benchmark_runs/full_matrix_clean_20260423T2350Z/parallel_a380/quality/results_20260423_215747.json`](../../benchmark_runs/full_matrix_clean_20260423T2350Z/parallel_a380/quality/results_20260423_215747.json)
- [`benchmark_runs/full_matrix_clean_20260423T2350Z/parallel_a380/quality/results_20260423_222514.json`](../../benchmark_runs/full_matrix_clean_20260423T2350Z/parallel_a380/quality/results_20260423_222514.json)
- [`benchmark_runs/full_matrix_clean_20260423T2350Z/throughput/qwen3.6-35b-a3b-iq4xs.json`](../../benchmark_runs/full_matrix_clean_20260423T2350Z/throughput/qwen3.6-35b-a3b-iq4xs.json)
- [`benchmark_runs/full_matrix_clean_20260423T2350Z/throughput/qwen3.6-27b-q5ks-7900.json`](../../benchmark_runs/full_matrix_clean_20260423T2350Z/throughput/qwen3.6-27b-q5ks-7900.json)
- [`benchmark_runs/full_matrix_clean_20260423T2350Z/parallel_9070/throughput/qwen3.6-27b-q5ks-9070.json`](../../benchmark_runs/full_matrix_clean_20260423T2350Z/parallel_9070/throughput/qwen3.6-27b-q5ks-9070.json)
- [`benchmark_runs/full_matrix_clean_20260423T2315Z/throughput/qwen3.5-4b-q8.json`](../../benchmark_runs/full_matrix_clean_20260423T2315Z/throughput/qwen3.5-4b-q8.json)
- [`benchmark_runs/full_matrix_clean_20260423T2315Z/throughput/qwen3.5-9b-q6.json`](../../benchmark_runs/full_matrix_clean_20260423T2315Z/throughput/qwen3.5-9b-q6.json)
- [`benchmark_runs/full_matrix_clean_20260423T2315Z/throughput/gemma4-e4b-it-q8.json`](../../benchmark_runs/full_matrix_clean_20260423T2315Z/throughput/gemma4-e4b-it-q8.json)
- [`benchmark_runs/full_matrix_clean_20260423T2350Z/throughput/gemma4-26b-a4b-it-q4km.json`](../../benchmark_runs/full_matrix_clean_20260423T2350Z/throughput/gemma4-26b-a4b-it-q4km.json)
- [`benchmark_runs/full_matrix_clean_20260423T2350Z/throughput/lfm25-12b-instruct-q4km.json`](../../benchmark_runs/full_matrix_clean_20260423T2350Z/throughput/lfm25-12b-instruct-q4km.json)
- [`benchmark_runs/full_matrix_clean_20260423T2350Z/parallel_a380/throughput/ministral3-3b-instruct-q4km.json`](../../benchmark_runs/full_matrix_clean_20260423T2350Z/parallel_a380/throughput/ministral3-3b-instruct-q4km.json)
- [`benchmark_runs/full_matrix_clean_20260423T2350Z/parallel_a380/throughput/smollm3-q4km.json`](../../benchmark_runs/full_matrix_clean_20260423T2350Z/parallel_a380/throughput/smollm3-q4km.json)
- [`benchmark_runs/full_matrix_clean_20260423T2350Z/parallel_a380/throughput/qwen3-4b-instruct-2507-q4km.json`](../../benchmark_runs/full_matrix_clean_20260423T2350Z/parallel_a380/throughput/qwen3-4b-instruct-2507-q4km.json)
- [`benchmark_runs/qwen27_split_quality_20260429T005800Z/quality/results_20260428_192125.json`](../../benchmark_runs/qwen27_split_quality_20260429T005800Z/quality/results_20260428_192125.json)
- [`benchmark_runs/qwen27_split_quality_20260429T005800Z/quality/results_20260428_194551.json`](../../benchmark_runs/qwen27_split_quality_20260429T005800Z/quality/results_20260428_194551.json)
- [`benchmark_runs/qwen27_split_quality_q6_q8_debug/quality/results_20260428_203651.json`](../../benchmark_runs/qwen27_split_quality_q6_q8_debug/quality/results_20260428_203651.json)
- [`benchmark_runs/qwen27_split_quality_q6_q8_debug/quality/results_20260428_210543.json`](../../benchmark_runs/qwen27_split_quality_q6_q8_debug/quality/results_20260428_210543.json)
- [`benchmark_runs/qwen27_split_fullrow_20260429T000522Z/qwen27_q4km_split_pp512_tg64.csv`](../../benchmark_runs/qwen27_split_fullrow_20260429T000522Z/qwen27_q4km_split_pp512_tg64.csv)
- [`benchmark_runs/qwen27_q5ks_split_fullrow_20260429T000603Z/qwen27_q5ks_split_pp512_tg64.csv`](../../benchmark_runs/qwen27_q5ks_split_fullrow_20260429T000603Z/qwen27_q5ks_split_pp512_tg64.csv)
- [`benchmark_runs/qwen27_q6k_split_fullrow_20260429T001024Z/qwen27_q6k_split_pp512_tg64.csv`](../../benchmark_runs/qwen27_q6k_split_fullrow_20260429T001024Z/qwen27_q6k_split_pp512_tg64.csv)
- [`benchmark_runs/qwen27_q8_split_fullrow_20260429T001111Z/qwen27_q8_split_pp512_tg64.csv`](../../benchmark_runs/qwen27_q8_split_fullrow_20260429T001111Z/qwen27_q8_split_pp512_tg64.csv)
- [`benchmark_runs/qwen27_bf16_7900_offload_fullrow_20260429T001338Z/qwen27_bf16_7900_offload_pp512_tg64.csv`](../../benchmark_runs/qwen27_bf16_7900_offload_fullrow_20260429T001338Z/qwen27_bf16_7900_offload_pp512_tg64.csv)
