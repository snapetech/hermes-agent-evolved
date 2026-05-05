# Split-Card LLM Test Plan - 2026-04-22

Target machine:

- `ROCm1`: RX 7900 XT, 20 GB, preferred primary benchmark GPU.
- `ROCm0`: RX 9070 XT, 16 GB, desktop/display-risk GPU.
- Safe split direction: `ROCm1/ROCm0`.
- Initial split budget: treat 36 GB physical VRAM as about 30-32 GB usable for
  model weights plus KV/cache when the desktop is active. Use explicit fit
  targets rather than filling both cards.

## Matrix Gaps Before Bigger Split Tests

Quality gaps:

- `Kimi-Linear-48B-A3B-Instruct Q4_K_M`: throughput-only split row exists;
  still needs Hermes utility/SLM quality.
- `Kimi-VL-A3B-Thinking Q4_K_M`: throughput-only; needs text utility quality
  and a separate vision eval.
- `Moonlight-16B-A3B Q4_K_M/Q6_K`: throughput-only; needs Hermes quality.
- `Qwen3 14B Q4_K_M`: throughput-only; needs Hermes quality.
- `Qwen3.6 27B Q4_K_M`: file is local; no throughput or quality row yet.
- `Qwen3.6 35B-A3B Q4_K_M`: file is local; no split/quality control row yet.
- `Qwen3.6 35B-A3B TQ3_1S`: file is local; needs runtime compatibility check.
- `Nemotron Nano 9B v2`: download stalled; still needs resume, throughput, and
  quality.

Repeatability gaps:

- Current Hermes quality numbers are mostly one repetition except the Qwen3.6
  baseline. Repeat the best candidates with at least three repetitions before
  changing default routing.
- The scorecard's `2x quality` target is intentionally strict. With the current
  small task set, a model can be operationally useful without clearing 2x if it
  is approval-clean in critical tasks.

Metric gaps:

- Add coding-agent tasks before treating coding models as failed overall.
  Current tasks are utility/routing/approval-heavy.
- Add split/offload-specific latency logging: load time, first token latency,
  steady generation tok/s, prompt eval tok/s, and failure mode.
- Add context-retention tasks for long-running agent use. Several community
  reports for Qwen3-Coder-Next mention stability depending heavily on current
  llama.cpp and context settings.

## New Guidance From 2026-04-23 Qwen3.6 Research

Primary local references:

- `benchmarks/llm/qwen36_27b_tuning_research_20260423.md`
- `benchmarks/llm/qwen36_knob_bench.sh`

Primary upstream sources:

- Qwen upstream repo: <https://github.com/QwenLM/Qwen3.6>
- Qwen 27B model card: <https://huggingface.co/Qwen/Qwen3.6-27B>
- Bartowski 27B GGUF card: <https://huggingface.co/bartowski/Qwen_Qwen3.6-27B-GGUF>
- llama.cpp speculative docs: <https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md>
- llama.cpp token generation tips: <https://raw.githubusercontent.com/ggml-org/llama.cpp/master/docs/development/token_generation_performance_tips.md>
- llama.cpp ROCm flash-attn issue: <https://github.com/ggml-org/llama.cpp/issues/10439>
- llama.cpp large-ubatch regression issue: <https://github.com/ggml-org/llama.cpp/issues/18725>
- llama.cpp cache-reuse regressions: <https://github.com/ggml-org/llama.cpp/issues/15082>
- llama.cpp prompt re-processing regression for hybrid/recurrent families: <https://github.com/ggml-org/llama.cpp/issues/21831>

What changes:

- The highest-value Qwen3.6 work is now the dense `Qwen3.6-27B` lane, not more
  micro-tuning of the current live `35B-A3B IQ4_XS` service.
- `flash-attn`, `batch`, `ubatch`, and KV cache type are the first-pass knobs
  that matter for dense `27B`.
- `--n-cpu-moe` remains a fit fallback for the `35B-A3B` MoE family only. It is
  not a speed knob and should not be part of the dense `27B` ranking sweep.
- `cache-reuse` is a served-path knob, not a direct `llama-bench` knob. Current
  upstream issues suggest it can regress independently of raw model throughput.
- Speculative decoding should only be tested after one strong dense `27B`
  non-spec baseline already exists.

## Split Launch Baseline

Use this family of settings for split-card throughput probes:

```bash
env ROCR_VISIBLE_DEVICES=0,1 HIP_VISIBLE_DEVICES=0,1 HSA_OVERRIDE_GFX_VERSION=11.0.0 \
  llama-bench \
  -m "$MODEL" \
  -dev ROCm1,ROCm0 \
  -sm layer \
  -ts 12,8 \
  -ngl 999 \
  -fa 1 \
  -ctk q4_0 -ctv q4_0 \
  -b 1024 -ub 128 \
  -t 16 -r 1 \
  -n 64 -pg 512,64 \
  -fitt 768,4096 -fitc 8192 \
  -o csv
```

Notes:

- Keep `ROCm1` first. Prior stable rows use the 7900-first direction.
- Reserve at least 4 GB on `ROCm0` while it drives the desktop.
- Prefer `--split-mode layer` first. `row` is worth testing only after a model
  works in layer mode.
- For GLM-4.7-Flash specifically, test `--flash-attn off` because the GGUF card
  recommends it for performance.
- For server quality runs, start at `--ctx-size 8192`; only increase context
  after the model clears correctness and stability.

## Priority Split Candidates

### 1. Kimi-Linear-48B-A3B-Instruct

Already local:

- `Q4_K_M`: 30.06 GB, existing split throughput 31.36 tg64.

Next tests:

- Quality: `Q4_K_M` split, 8K context, Hermes 8-task suite.
- Throughput stretch: `Q5_K_S` 34.01 GB and `Q5_K_M` 35.10 GB only if the
  display GPU has enough reserved headroom; otherwise these are too tight.
- Lower-latency control: `IQ4_XS` 26.46 GB or `Q4_K_S` 28.98 GB if Q4_K_M is
  barely stable.

Reason:

- This is the strongest already-tested split-only Moonshot text candidate.
- It enables a larger model than either card can fit alone.

### 2. GLM-4.7-Flash Higher Quants

Already local:

- `Q6_K_L`: 24.98 GB, 7900 throughput 35.32 tg64, quality 4/4 on small suite.
- `IQ4_XS`: 16.25 GB, approval-clean 5/8 in wave2.

Next tests:

- Split `Q8_0` 31.84 GB with `--flash-attn off`, 8K context.
- Split `Q6_K_L` with `--flash-attn off` as a tuning control against the
  existing 7900-only row.
- Quality: repeat `Q6_K_L` and `Q8_0` on the 8-task suite.

Reason:

- GLM is the best measured local validator family for Hermes utility work.
- Q8_0 may give better quality while still fitting across both cards if KV and
  display headroom are controlled.

### 3. Qwen3.6 35B-A3B Higher Quants

Already local:

- `Q4_K_M`: 21.39 GB local file.
- `TQ3_1S`: 17.58 GB local file.

Next tests:

- Split `Q4_K_M` as the direct quant-quality control for the live IQ4_XS
  baseline.
- Test Unsloth `UD-Q5_K_M` 26.46 GB and `UD-Q6_K` 29.31 GB as the next
  quality controls. These files are now present locally.
- `UD-Q5_K_S` remains worth downloading later if the `Q5_K_M`/`Q6_K` results
  suggest the family is still routing-competitive.
- Treat `Q8_0` 36.90 GB and `UD-Q8_K_XL` 38.45 GB as too tight for the display
  card unless the desktop is moved off the 9070 or context is tiny.

Reason:

- This answers whether Qwen3.6 failures are family limits or current
  IQ4/quantization limits.
- Community signal favors Qwen3-Coder-Next for coding, but the current Hermes
  primary is Qwen3.6, so this is the cleanest production-control test.

### 4. Qwen3.6 27B Dense

Already local:

- `Q4_K_M`: 16.55 GB.
- `Q6_K`: 22.52 GB.
- `Q8_0`: 28.60 GB.
- `BF16`: 53.8 GB split across two files for host-memory/offload work.

Next tests:

- First run a dedicated single-7900 tuning sweep with:
  - `flash-attn on/off`
  - KV cache `q8_0/q8_0` vs `q4_0/q4_0`
  - `batch` `512/1024/2048`
  - `ubatch` `128/256/512/1024`
  - `prompt` `512/4096/8192/32768`
  - `n_cpu_moe=0`
- Use `benchmarks/llm/qwen36_knob_bench.sh` for the first ranking pass.
- Keep `Q4_K_M` as the first speed probe.
- Download `Q5_K_S` as the first serious quality-control quant.
- After the direct-bench sweep, take the top two or three served configs into:
  - `scripts/llama_throughput_compare.py`
  - `benchmarks/llm/run_slm_utility_bench.sh`
- Only then compare the best `27B` served config against the `35B-A3B` rows.
- Split `27B` only after the single-7900 winner is known, or if `Q8_0` needs
  split/offload for useful context.

Reason:

- Upstream Qwen materials position dense `27B` ahead of open `35B-A3B` on
  coding-agent benchmarks.
- Dense `27B` is also the better later target for speculative decoding than
  the `35B-A3B` MoE family.
- The `27B` line is the cleanest way to test whether Hermes should prefer a
  denser, stronger coding/control model instead of continuing to squeeze the
  current `35B-A3B` service.

### 4A. Qwen3.6 27B Dense Tuning Order

Best-first sequence:

1. `Q4_K_M`, `fa=1`, `q8 KV`, `b=1024`, `ub=512`
2. `Q4_K_M`, `fa=1`, `q4 KV`, `b=1024`, `ub=512`
3. `Q4_K_M`, `fa=0`, `q8 KV`, `b=1024`, `ub=512`
4. `Q4_K_M`, `fa=1`, `q8 KV`, `b=2048`, `ub=512`
5. `Q4_K_M`, `fa=1`, best KV, `b=1024`, `ub=128/256/512/1024`
6. `Q5_K_S`, rerun the best one to three `Q4_K_M` settings
7. `Q6_K` and `Q8_0` only after the best served-path `Q4/Q5` config is known

Additional knobs worth testing after the first pass:

- `threads`: upstream llama.cpp performance notes explicitly warn that CPU
  oversubscription can hurt generation even on GPU-backed runs. Add a small
  `-t` sweep such as `8/12/16` if the first 27B winner is still CPU-limited.
- `cache-reuse`: test only under `llama-server` with repeated shared-prefix
  prompts, because upstream issues show regressions that are independent of
  raw single-request speed.
- speculative decoding: only for the best dense `27B` served config, starting
  with `--spec-type ngram-mod` and modest draft windows.
- longer context: once a stable 8K winner exists, rerun at `32K` and `64K`
  before claiming it can replace the live 35B service.

Operational cautions:

- ROCm flash attention has upstream reports of being slower in some concurrent
  loads, so do not assume `fa=1` wins on this box without measuring it.
- Very large `ubatch` has upstream reports of hurting prompt processing on
  Qwen-family models, so treat `ubatch > 512` as suspect until local numbers
  prove otherwise.
- Current upstream cache-reuse issues mean cache behavior should be verified
  with repeated served prompts, not inferred from flags alone.

### 5. Seed-OSS-36B-Instruct

Download targets:

- `Q4_K_M`: 21.76 GB.
- `Q5_K_M`: 25.59 GB.
- `Q6_K`: 29.67 GB.

Next tests:

- Start with `Q4_K_M` or `Q5_K_M` split.
- If stable and quality is promising, try `Q6_K` split.

Reason:

- It is a 36B model with llama.cpp support and quant sizes that fit the split
  envelope. Community chatter is thinner than Qwen/GLM, so this is a research
  lane, not a primary candidate.

### 6. Magistral-Small-2509 / Mistral-Small-3.2 24B

Download targets:

- `Magistral-Small-2509 Q4_K_M`: 14.33 GB.
- `Magistral-Small-2509 Q5_K_M`: 16.76 GB.
- `Magistral-Small-2509 Q8_0`: 25.06 GB.
- Mistral-Small-3.2 equivalent Q4/Q5/Q6 rows if we want the non-reasoning
  control.

Next tests:

- Run single-7900 Q5/Q8 throughput if possible.
- Run split Q8 quality only if the Mistral chat-template path is handled.

Reason:

- Potentially useful reasoning/coding lane, but Mistral explicitly warns that
  the integrated llama.cpp chat template may not guarantee correct behavior for
  Magistral. That makes it a lower-priority Hermes routing candidate until the
  template path is solved.

### 7. Qwen3-Coder-Next 80B-A3B

Download targets:

- `IQ3_XXS`: 31.73 GB.
- `IQ3_XS`: 33.03 GB.
- Avoid `Q3_K_M` 36.66 GB and all Q4+ rows for now; they are too tight for
  20+16 GB with desktop headroom.

Next tests:

- Only after the above candidates, and only with tiny/medium context first.
- Prefer the official Qwen split-file GGUF if using Q5+ on larger memory later;
  for this machine use Bartowski IQ3.

Reason:

- Official card and community posts point to strong agentic coding potential,
  but the practical 36 GB fit is only very low 3-bit or lower once desktop
  headroom is respected. Treat it as an experimental coding-agent lane.

## Not Split Priorities

- `Devstral Small 2`: Q3 quality failed all critical tasks. Higher quants may
  help coding, but this should not consume split-card time until coding-specific
  evals exist.
- `Gemma3 12B`: not approval-clean in wave2.
- `LFM2 24B A2B`: fast helper, but failed mutation guard; use single-7900
  rather than split.
- `Nemotron Nano 9B v2`: finish as a single-card helper once download resumes;
  no split needed.

## Proposed Run Order

1. `Qwen3.6 27B Q4_K_M` single-7900 knob sweep.
2. `Qwen3.6 27B Q5_K_S` top-config quality control, once downloaded.
3. Best `Qwen3.6 27B` served-path comparison against the current live
   `35B-A3B IQ4_XS` service.
4. `Qwen3.6 35B-A3B Q4_K_M` split throughput and quality as the direct
   quant-family control.
5. `Qwen3.6 35B-A3B UD-Q5_K_M` and `UD-Q6_K` offload/split quality controls.
6. `GLM-4.7-Flash Q8_0` split throughput and quality with `--flash-attn off`.
7. `Kimi-Linear-48B-A3B Q4_K_M` split quality.
8. `Seed-OSS-36B Q4_K_M` or `Q5_K_M` split.
9. `Magistral-Small-2509 Q8_0` split after chat-template handling is decided.
10. `Qwen3-Coder-Next IQ3_XXS/IQ3_XS` split as the high-risk coding-agent
    experiment.

Each model that clears about 30 tok/s and all critical Hermes gates should then
get a three-repetition quality run before any routing recommendation changes.

## Concrete Gapfill Checklist

Use this as the actual remaining matrix worklist, not just the aspirational
candidate list.

### Qwen3.6 27B dense

- Complete 7900-only throughput tuning for `Q4_K_M`.
- Download `Q5_K_S`.
- Run served-path throughput and Hermes utility quality for the top `Q4_K_M`
  settings.
- Run the same served-path checks for `Q5_K_S`.
- Compare the best `27B` served config directly against:
  - live `35B-A3B IQ4_XS`
  - `35B-A3B Q4_K_M`
  - `35B-A3B UD-Q5_K_M`
  - `35B-A3B UD-Q6_K`
- Add `32K` and `64K` context checks for the winning `27B` served config.

### Qwen3.6 35B-A3B controls

- Run split throughput and Hermes utility quality for `Q4_K_M`.
- Run offload or maintenance-window split quality for `UD-Q5_K_M`.
- Run offload or maintenance-window split quality for `UD-Q6_K`.
- Treat `TQ3_1S` as blocked until runtime compatibility is demonstrated.

### Expanded split-axis gapfill

The expanded-axis sweep is still largely open. Finish the following groups in
this order:

1. `qwen36_35b_iq4xs`
   - close the blocked `14/6` row cleanly
   - finish the missing reverse-order rows
   - finish all `q8_0` KV rows
   - finish all `32768` context rows
2. `qwen36_35b_q4km`
   - run the same `12/8`, `14/6`, `10/10`, reverse-order, `q4/q8 KV`,
     `8192/32768` matrix
3. `qwen36_35b_q4kl`
   - same axis completion as `q4km`
4. `qwen36_27b_q4km`
   - complete the same axis matrix after the single-7900 winner is known
5. `qwen3_coder_30b_q6k`
   - complete the same axis matrix because the split `12/8` baseline already
     exists
6. `glm47_flash_q6kl`
   - complete the same axis matrix, but always include `flash-attn off` as the
     control row
7. `lfm2_24b_a2b_q4km`
   - complete only if it still looks routing-relevant after the 27B lane is
     ranked; otherwise it remains secondary

### Quality gapfill

- Repeat the strongest local candidates for at least three repetitions.
- Add coding-agent tasks before declaring any coding model broadly weak.
- Add context-retention checks to every model that is still in routing
  contention after throughput ranking.
