# Qwen 3.6 27B Tuning Research - 2026-04-23

This note compares the current live Hermes `llama.cpp` setup against the most
promising tuning lanes for `Qwen3.6-27B`, with a focus on practical throughput
and agent utility on Keith's AMD workstation.

## Current Live Baseline

Confirmed live host service on 2026-04-23:

- Service: `hermes-llama-qwen36.service`
- Build: `llama.cpp` `b8840-9e5647aff`
- Model: `qwen3.6-35b-a3b:iq4xs`
- Actual flags:
  - `--ctx-size 65536`
  - `--parallel 1`
  - `--batch-size 1024`
  - `--ubatch-size 512`
  - `--gpu-layers 999`
  - `--flash-attn on`
  - `--cache-type-k q8_0`
  - `--cache-type-v q8_0`
  - `--cache-reuse 256`
  - `--reasoning off`
  - `--jinja`

Current repo evidence for the live 35B baseline:

- Hermes utility benchmark scorecard keeps `qwen3.6-35b-a3b:iq4xs` as the
  operational baseline, but it still misses approval/routing quality gates in
  the scorecard summary.
- Direct `llama-bench` rows on the RX 7900 XT show about `75.8 tg128` for the
  35B `IQ4_XS` baseline with `n_cpu_moe=0`.
- Existing local sweeps show:
  - `q8_0` KV and `q4_0` KV were nearly identical for single-request generation
    speed on the 35B baseline.
  - `--n-cpu-moe` sharply reduced throughput on this machine, so CPU expert
    offload should be treated as a fit fallback, not a speed knob.
  - The old batch/ubatch matrix was not a valid comparison because those cells
    failed at model load time.

## What External Sources Suggest

### 1. The 27B dense model is the better quality candidate

Official Qwen sources position `Qwen3.6-27B` as stronger than the open 35B-A3B
MoE sibling for coding-agent benchmarks.

- Qwen GitHub repo: <https://github.com/QwenLM/Qwen3.6>
- Qwen 27B model card: <https://huggingface.co/Qwen/Qwen3.6-27B>

Operational takeaway:

- If `27B` lands near the same local speed band as the current `35B IQ4_XS`
  service, it is the highest-value candidate to test because the likely upside
  is quality, not just throughput.

### 2. For llama.cpp, dense 27B should be tested differently from the 35B-A3B MoE

`llama.cpp` speculative decoding docs explicitly note:

- MoEs require longer drafts.
- Dense models can reduce `--draft-min` and `--draft-max`.

Source:

- <https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md>

Operational takeaway:

- The `27B` dense model is a better target than `35B-A3B` for speculative
  decoding experiments.
- Start without speculation, then test `ngram-mod` only after a stable baseline
  exists.

### 3. Quant choice matters more than the current 35B q8-vs-q4 KV result

Bartowski's GGUF card for `Qwen3.6-27B` marks `Q5_K_S` as the recommended
high-quality quant.

Source:

- <https://huggingface.co/bartowski/Qwen_Qwen3.6-27B-GGUF>

Operational takeaway:

- If only one new quant is worth downloading after `Q4_K_M`, make it `Q5_K_S`.
- `Q4_K_M` is the first speed probe; `Q5_K_S` is the first serious quality
  control.

### 4. ROCm-specific knob folklore is mixed enough that it must be measured

Relevant `llama.cpp` issues and docs:

- Flash attention on ROCm has had reports of worse throughput under some loads:
  <https://github.com/ggml-org/llama.cpp/issues/10439>
- Larger `ubatch` can reduce prompt performance on Qwen-family models in some
  backends:
  <https://github.com/ggml-org/llama.cpp/issues/18725>
- `--cache-reuse` behavior has had regressions:
  <https://github.com/ggml-org/llama.cpp/issues/15082>
- Hybrid/recurrent-family cache reuse is still a live area of instability:
  <https://github.com/ggml-org/llama.cpp/issues/21831>

Operational takeaway:

- Treat `flash-attn`, `ubatch`, and cache reuse as measurement targets, not
  assumptions.
- Avoid over-weighting old general llama.cpp folklore when the current live
  stack is `HIP + Qwen + single-slot server + 64K context`.

### 4A. CPU thread count is still a real GPU-side tuning knob

The upstream llama.cpp token-generation troubleshooting note explicitly warns
that CPU oversubscription can hurt generation speed even when the model is
mostly GPU-backed, and suggests reducing `--threads` if generation is slow.

Source:

- <https://raw.githubusercontent.com/ggml-org/llama.cpp/master/docs/development/token_generation_performance_tips.md>

Operational takeaway:

- If the first `27B` winner still looks CPU-limited or inconsistent under
  serving, add a small `threads` sweep such as `8/12/16`.
- Do not assume the current `-t 16` live default is already optimal for the
  dense `27B` lane.

### 5. Community-reported 27B speeds are wide enough that your target band is realistic

Recent community reports are noisy because the hardware varies a lot, but they
do establish rough expectations:

- A LocalLLaMA thread reported `Qwen3.6-27B Q4_K_M` around `40 tok/s`.
- Another thread reported `~34 tok/s` generation with TurboQuant `TQ3_4S` on
  dual 3090s.
- Another report described no meaningful speculative-decoding gain until a very
  recent llama.cpp update, implying this area is build-sensitive.

Sources:

- <https://www.reddit.com/r/LocalLLaMA/comments/1sss5og/what_speed_is_everyone_getting_on_qwen36_27b/>
- <https://www.reddit.com/r/LocalLLaMA/comments/1ssp9kq/best_config_for_qwen36_27b_llamacpp_opencode/>
- <https://www.reddit.com/r/LocalLLaMA/comments/1stcer1/qwen3627b_llamacpp_speculative_decoding/>

Operational takeaway:

- On this box, a realistic success band is not "beat the 35B `llama-bench`
  number". It is:
  - clear `~30 tok/s` endpoint generation under a real served config
  - preserve or improve Hermes utility quality
  - avoid regressions in long-turn latency and stability

## Best-First Hypotheses

Ordered by expected value:

1. `Qwen3.6-27B Q4_K_M` on the 7900 XT will likely be the first viable local
   speed/quality comparison against the live 35B `IQ4_XS` service.
2. `Qwen3.6-27B Q5_K_S` is the most likely "best possible" quality/speed
   follow-up if `Q4_K_M` is fast enough.
3. `flash-attn on` will probably remain the best default for the single-slot
   live service, but it is still worth testing `off` once because ROCm results
   have been inconsistent across versions.
4. `q4_0` KV may help context headroom more than raw generation speed. For the
   27B dense model it is a memory knob first, not a speed knob first.
5. Speculative decoding is worth testing on the dense 27B only after a stable
   non-spec baseline exists. It should not be part of the first ranking pass.

## Recommended Test Order

### Phase A: Direct Bench, single 7900 XT

Goal: find stable throughput candidates cheaply.

Use the updated sweep script:

```bash
MODEL_PATH=/path/to/Qwen_Qwen3.6-27B-Q4_K_M.gguf \
GPU_DEVICE=ROCm1 \
GPU_LABEL=7900xt_qwen27 \
PROMPT_TOKENS_LIST="512 4096 8192 32768" \
GEN_TOKENS=128 \
BATCH_SIZE_LIST="512 1024 2048" \
UBATCH_SIZE_LIST="128 256 512 1024" \
FLASH_ATTN_LIST="1 0" \
CACHE_TYPES="q8_0:q8_0 q4_0:q4_0" \
N_CPU_MOE_LIST="0" \
benchmarks/llm/qwen36_knob_bench.sh
```

If `Q5_K_S` is downloaded, rerun the same sweep with the top two or three
`Q4_K_M` settings only.

Primary metrics:

- `tg128` generation speed
- `pp512`, `pp4096`, `pp8192`, `pp32768`
- load success/failure

Drop any config that:

- fails to load
- loses more than about 10% generation speed with no clear prompt-eval benefit
- requires `n_cpu_moe` or any offload trick that does not apply to dense 27B

### Phase B: Served endpoint comparison

Goal: rank the top direct-bench configs under real API serving conditions.

For each finalist, render and apply a candidate service:

```bash
MODEL_PATH=/path/to/Qwen_Qwen3.6-27B-Q4_K_M.gguf \
MODEL_ALIAS=qwen3.6-27b:q4km \
CTX_SIZE=65536 \
BATCH_SIZE=1024 \
UBATCH_SIZE=512 \
FLASH_ATTN=on \
CACHE_TYPE_K=q8_0 \
CACHE_TYPE_V=q8_0 \
deploy/k8s/hermes-llama-qwen36-service.sh render
```

Then measure:

```bash
python scripts/llama_throughput_compare.py \
  --base-url http://10.0.0.10:8001/v1 \
  --model qwen3.6-27b:q4km \
  --repetitions 5 \
  --timeout 180
```

And run Hermes utility quality:

```bash
BASE_URL=http://10.0.0.10:8001/v1 \
MODEL=qwen3.6-27b:q4km \
REPETITIONS=3 \
benchmarks/llm/run_slm_utility_bench.sh
```

Then run one finalist-only decode check before making a routing call:

```bash
BASE_URL=http://10.0.0.10:8001/v1 \
MODEL=qwen3.6-27b:q4km \
REPETITIONS=3 \
TEMPERATURE=0.1 \
TOP_P=0.95 \
REPEAT_PENALTY=1.05 \
SEED=7 \
DECODE_LABEL=tuned-t0.1-p0.95-rp1.05 \
benchmarks/llm/run_slm_utility_bench.sh
```
Also add a repeated-prefix served-path check with the same finalist configs so
`--cache-reuse` is validated against current llama.cpp behavior rather than
assumed from flags alone.

Promote only if both are true:

- endpoint completion throughput is at least competitive with the current live
  model for single-slot use
- Hermes utility quality matches or beats the live `35B IQ4_XS` baseline on the
  fixed preset, or the tuned preset clearly improves utility without regressing
  safety or reliability

### Phase C: Speculative decoding, only for the winner

After one winning non-spec config exists, try:

```bash
--spec-type ngram-mod --spec-ngram-size-n 24 --draft-min 32 --draft-max 48
```

Then:

```bash
--spec-type ngram-mod --spec-ngram-size-n 24 --draft-min 48 --draft-max 64
```

Use repetitive coding/edit prompts for this pass. If gains do not appear there,
do not expect them in normal Hermes traffic.

## What To Change First

If time is limited, do only these five runs:

1. `27B Q4_K_M`, `fa=1`, `q8 KV`, `b=1024`, `ub=512`
2. `27B Q4_K_M`, `fa=1`, `q4 KV`, `b=1024`, `ub=512`
3. `27B Q4_K_M`, `fa=0`, `q8 KV`, `b=1024`, `ub=512`
4. `27B Q4_K_M`, `fa=1`, `q8 KV`, `b=2048`, `ub=512`
5. `27B Q5_K_S`, same as run 1, if the quant is available

That is the shortest path to finding whether the dense 27B has a real chance to
replace or augment the current 35B service.

## Bottom Line

The current repo evidence does not show an obvious speed win left inside the
live 35B `IQ4_XS` configuration. The stronger opportunity is to move sideways:
test `Qwen3.6-27B` dense, where official quality numbers are better and the
serving knobs are simpler because there is no MoE offload question.

If the 27B dense model clears about `30+ tok/s` in served generation while
matching or beating the Hermes utility suite, that is the most credible upgrade
path. If it does not, the next best move is not more 35B micro-tuning; it is
`27B Q5_K_S` or a speculation pass on the best 27B non-spec baseline.
