# Nous Edge Watch Local Results - 2026-04-22

Local smoke tests for model alerts captured from Hermes Edge Watch. These are
operator checks on the local ROCm bench host, not leaderboard claims.

## Environment

- GPU used: AMD Radeon RX 9070 XT (`ROCm0`)
- Live primary service on the RX 7900 XT was left alone.
- Launch guard: `GPU_GUARD_PROFILE=amd-node-a deploy/k8s/hermes-llama-qwen36-service.sh guard-check`
- Server: local `llama-server` on `127.0.0.1:8030`
- Common server settings: `--ctx-size 8192 --gpu-layers 999 --flash-attn on --fit on --fit-target 4096 --fit-ctx 4096 --cache-type-k q8_0 --cache-type-v q8_0 --jinja`

## Results

| Candidate | GGUF Tested | Fit / pp512 | Fit / tg64 | Endpoint gen tok/s | JSON Smoke | Verdict |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `moe-10b-a1b:q4km` | `mradermacher/moe-10b-a1b-8k-wsd-lr3e4-1t-GGUF` | 5472.10 | 127.18 | 128.52 | 0/3 | Fast, but not usable for Hermes utility routing. It repeated prompt text and failed JSON-only instructions. |
| `hermes-4-14b:q4km` | `bartowski/NousResearch_Hermes-4-14B-GGUF` | 1897.54 | 47.73 | 45.58 | 3/3 | Best current candidate from this alert batch for Hermes utility/JSON tasks. |
| `nouscoder-14b:q4km` | `bigatuna/NousCoder-14B-GGUF` | 2013.52 | 46.27 | 46.42 | 0/3 default, 3/3 with `/no_think` | Usable only if the prompt/runtime reliably disables thinking. Failed approval-risk judgment even with `/no_think`, so do not use for approval-adjacent routing yet. |

## Candidate Notes

- `NousResearch/Kimi-K2-Thinking-Alternate-Tokenizer` is tokenizer-only and is
  not a runnable local model candidate.
- `NousResearch/nomos-1` did not have an obvious GGUF candidate in the checked
  Hugging Face search results; it would need conversion/quantization or a
  trustworthy community GGUF.
- `NousResearch/Hermes-4.3-36B` has GGUFs, but the useful quants are much larger
  and should be tested separately. The 9070 lane is not the right first target
  while the 7900 is hosting the live primary model.

## Artifacts

- `benchmark_runs/nous_edge_watch_20260422T175037Z/summary.tsv`
- `benchmark_runs/nous_edge_watch_hermes14b_20260422T182347Z/summary.tsv`
- `benchmark_runs/nous_edge_watch_nouscoder14b_20260422T183243Z/summary.tsv`
- `benchmark_runs/llama_throughput_nous_edge_watch/`
- `benchmark_runs/nous_edge_watch_smoke/`

## Recommendation

Keep `hermes-4-14b:q4km` as the only promotion candidate from this batch for
Hermes utility JSON work. Use `nouscoder-14b:q4km` only for separate coding
experiments after adding an explicit no-thinking configuration and approval-risk
tests. Reject the 10B MoE checkpoint for routing/utility use despite its speed.
