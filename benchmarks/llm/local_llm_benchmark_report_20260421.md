# Local LLM Benchmark Report - 2026-04-21

This report summarizes the local LLM benchmark work on Keith's dual-GPU AMD
workstation:

- `ROCm0`: AMD Radeon RX 9070 XT, 16 GB, display-risk GPU.
- `ROCm1`: AMD Radeon RX 7900 XT, 20 GB, primary safe benchmark/service GPU.
- Split runs use `ROCm1/ROCm0` with `--tensor-split 12/10`, putting the
  7900 XT first.

All safe display-GPU runs used `--fit-target 4096 --fit-ctx 8192` to leave
headroom on the 9070 XT. The old comma form, `ROCm0,ROCm1`, is not treated as
a valid split result here because the resulting CSVs showed only one active
device at a time. True split runs use slash syntax, `ROCm1/ROCm0`.

## Safety Findings

The desktop video loss risk was tied to the earlier benchmark paths targeting
the display GPU (`ROCm0`, RX 9070 XT) directly and to split experiments that
used the display card without enough guardrails.

Current policy:

- The default benchmark path avoids `ROCm0`.
- `ROCm0` requires explicit opt-in through `ALLOW_DISPLAY_GPU_9070=1`.
- Display-GPU runs reserve 4096 MiB with `--fit-target 4096`.
- Opportunistic service startup on the 9070 XT is blocked when protected
  desktop workloads are present. In the latest run, Steam/steamwebhelper was
  detected, so `hermes-llama-lfm25-instruct-9070.service` was left inactive.
- The primary qwen service on the 7900 XT was restored after benchmark batches.

Do not bypass the guard for long runs while the 9070 XT is driving the desktop.

## Throughput Matrix

Numbers are from `llama-bench` with `pp512` prompt throughput and `tg64`
generation throughput, in tokens per second.

| Model | 9070 XT `ROCm0` | 7900 XT `ROCm1` | True split `ROCm1/ROCm0` | Notes |
|---|---:|---:|---:|---|
| Qwen3.5 4B Q8 | 2567.40 / 72.72 | 3845.36 / 80.32 | 3928.28 / 58.80 | Split improves prompt eval but hurts generation. |
| Gemma4 26B A4B Q4_K_M | 1074.38 / 34.23 | 1594.22 / 60.82 | 1937.96 / 48.04 | Split helps prompt eval, generation remains best on 7900 alone. |
| Moonlight 16B A3B Q4_K_M | 2093.56 / 85.50 | 2453.59 / 99.74 | 2535.20 / 60.74 | Best generation on 7900 alone. |
| Moonlight 16B A3B Q6_K | 908.53 / 37.34 | 137.60 / 18.23 | failed | Reverse split aborted with ROCm error. |
| GLM-4.7-Flash IQ4_XS | 621.72 / 24.99 | 104.13 / 14.26 | failed | Reverse split aborted with ROCm error. |
| Kimi-VL A3B Thinking Q4_K_M | 2094.40 / 85.45 | 2565.27 / 100.74 | 2131.04 / 85.35 | Good single-card vision/text lane. |
| Kimi-Linear 48B A3B Q4_K_M | does not fit | does not fit | 116.47 / 31.36 | Split-only practical Moonshot text model. |

Result locations:

- `benchmark_runs/llama_split_safe_20260421T155258Z/summary.tsv`
- `benchmark_runs/llama_split_safe_20260421T171952Z/summary.tsv`
- `benchmark_runs/llama_kimi_safe_20260421T183931Z/summary.tsv`
- `benchmark_runs/llama_7900_expanded_20260422T174500Z/summary.tsv`

## 7900 XT Expanded Matrix

On 2026-04-22 the later 9070-sidecar candidate set was rerun on the RX 7900 XT
where possible. These are `llama-bench` rows using `ROCm1`, `--split-mode none`,
`--fit-target 768`, `--fit-ctx 8192`, `pp512`, and `tg64`. The 9070 was not used.

| Model | 7900 XT `ROCm1` pp512 / tg64 | Prior 9070 sidecar completion tok/s | Read |
|---|---:|---:|---|
| Devstral Small 2 24B Q3_K_M | 761.45 / 34.29 | 34.30 | Similar generation; 7900 prompt eval is faster in direct bench. |
| Gemma 3 12B IT Q4_K_M | 1251.65 / 39.27 | 40.90 | Similar generation; 9070 slightly ahead on generation in the endpoint run. |
| GLM-4.7-Flash Q6_K_L | 220.59 / 35.32 | 26.95 | 7900 is the better single-card validator lane for this quant. |
| LFM2 2.6B Q8_0 | 4686.80 / 135.10 | 126.11 | 7900 is faster and still tiny. |
| LFM2 24B A2B Q4_K_M | 1109.72 / 103.76 | 109.58 | Very close; 9070 endpoint generation was slightly higher. |
| Phi-4 mini Q8_0 | failed | not recorded | Aborted with `GGML_ASSERT(ggml_is_contiguous(a))` under this HIP llama.cpp path. |
| Qwen3 14B Q4_K_M | 1161.28 / 41.83 | 45.04 | 9070 endpoint generation was slightly higher; 7900 prompt eval is strong. |
| Qwen3-Coder 30B A3B Q3_K_M | 941.59 / 72.95 | 69.72 | 7900 is slightly faster on generation. |
| Qwen3-Coder 30B A3B Q6_K | 249.09 / 41.21 | 21.27 | 7900 is much better for this partial-fit case. |

The "prior 9070 sidecar" column comes from OpenAI-compatible endpoint throughput
artifacts, while the 7900 column comes from direct `llama-bench`. Treat the
comparison as operational direction, not a strict apples-to-apples microbench.

The later quality pass found one important fit boundary: `Qwen3-Coder 30B A3B
Q6_K` failed to load as a temporary full-GPU 7900 server, trying to allocate
about 23.1 GiB on the 20 GB card. Keep that row as a partial/offload benchmark,
not a clean single-card service candidate. `Qwen3-Coder 30B A3B Q3_K_M` is the
realistic single-7900 quality-test quant.

## Qwen 3.6 Research Follow-Up

Research on 2026-04-22 suggests the local matrix should branch out beyond the
current `qwen3.6-35b-a3b:iq4xs` baseline.

The comparison graphic that showed `Qwen3.6-27B` close to Claude 4.5 Opus is
not comparing a smaller sibling of our exact model. It is comparing a dense 27B
model against the open-weight 35B-A3B MoE model. In Qwen's public model cards,
the 35B-A3B model has about 35B total parameters but only about 3B activated
per token, while the 27B model is dense. The dense model can therefore be
slower or harder to fit, but still much stronger on coding-agent quality.

Official Qwen benchmark numbers make `Qwen3.6-27B` the first priority to test:

| Benchmark | Qwen3.6 35B-A3B | Qwen3.6 27B | Read |
|---|---:|---:|---|
| Terminal-Bench 2.0 | 51.5 | 59.3 | 27B dense matches Claude 4.5 Opus in the published chart. |
| SWE-bench Pro | 49.5 | 53.5 | 27B is closer to Claude 4.5 than the 35B-A3B baseline. |
| SWE-bench Verified | 73.4 | 77.2 | 27B closes much of the gap to Claude 4.5 Opus at 80.9. |
| SWE-bench Multilingual | 67.2 | 71.3 | 27B is the better multilingual coding candidate. |
| SkillsBench | 28.7 | 48.2 | Large gap; likely relevant to Hermes tool-use and agent-control tasks. |
| NL2Repo | 29.4 | 36.2 | 27B is meaningfully stronger for repo synthesis. |
| QwenWebBench Elo | 1397 | 1487 | 27B improves web-agent behavior. |
| QwenClawBench | 52.6 | 53.4 | Narrower gap, but still favors 27B. |

Recommended to-test order:

1. `qwen3.6-27b:q4km`
   - Run `llama-bench` on the 7900 XT first with `--fit-target 768` and the
     same `pp512/tg64` shape used in this report.
   - If it fits and clears roughly 30 tok/s generation, run the 24-task Hermes
     utility suite against the current `qwen3.6-35b-a3b:iq4xs` baseline.
   - If it does not fit cleanly, test IQ4_XS or another high-quality 4-bit
     dense quant before trying split mode.

2. `qwen3.6-35b-a3b:q4km`
   - This is the direct quant-quality control for the live IQ4_XS baseline.
   - The goal is to determine whether the current approval/routing misses are
     model-family limits or low-precision quantization artifacts.

3. `qwen3.6-35b-a3b:q4kl`
   - Test only after Q4_K_M, or if Q4_K_M is close but still flaky on JSON,
     approval, or routing tasks.
   - This variant keeps higher precision for embeddings and output weights, so
     it is a plausible formatting and boundary-token improvement probe.

4. `qwen3.6-35b-a3b:tq3_1s`
   - Experimental only. The third-party TurboQuant file may need a
     TQ-capable llama.cpp build.
   - Test because its card claims Q4_K_M-like quality at materially smaller
     size, but do not mix it with standard GGUF conclusions until the runtime
     path is confirmed.

5. Hosted `qwen3.6-plus`, `qwen3.6-flash`, and `qwen3.6-max-preview`
   - Treat these as remote API reference lanes, not local replacement models.
   - `plus` and `flash` expose 1M context, function calling, structured output,
     built-in tools, and Coding Plan support in Alibaba Model Studio docs.
   - `max-preview` is described as stronger than Plus for agentic coding, but
     the model table marks built-in tools and Coding Plan as unsupported; use
     it as a quality reference only and record the exact test date.

Prompt and serving knobs worth testing across the Qwen3.6 rows:

- Default thinking versus explicit non-thinking mode.
- Preserved historical thinking versus stripped historical thinking if the
  serving path exposes `preserve_thinking`.
- KV cache `q8_0:q8_0` versus `q4_0:q4_0`.
- `-ncmoe` only for 35B-A3B MoE variants; it is irrelevant to the dense 27B.
- Same Hermes utility prompts as the current baseline, including the failing
  condensation and Portuguese/status tasks.

Sources used for this update:

- Qwen3.6 GitHub release/model table:
  `https://github.com/QwenLM/Qwen3.6`
- Qwen3.6 27B model card and benchmark table:
  `https://huggingface.co/Qwen/Qwen3.6-27B`
- Qwen3.6 35B-A3B FP8/open-weight model card:
  `https://huggingface.co/Qwen/Qwen3.6-35B-A3B-FP8`
- Bartowski Qwen3.6 35B-A3B GGUF quant card:
  `https://huggingface.co/bartowski/Qwen_Qwen3.6-35B-A3B-GGUF`
- mad-lab-ai TurboQuant Qwen3.6 35B-A3B GGUF card:
  `https://huggingface.co/mad-lab-ai/Qwen3.6-35B-A3B-tq-gguf`
- Alibaba Model Studio text-generation model table:
  `https://help.aliyun.com/zh/model-studio/text-generation-model`
- Alibaba Cloud Qwen3.6 Max Preview announcement:
  `https://www.alibabacloud.com/blog/qwen3-6-max-preview-smarter-sharper-still-evolving_603055`

## Utility And Output Quality

Throughput is not quality. The output-quality evidence currently comes from
Hermes utility/task benchmarks, not from `llama-bench`.

| Model | Utility/task score | Quality read | Caveat |
|---|---:|---|---|
| GLM-4.7-Flash Q6_K_L | 4/4 | Best measured utility accuracy. Strong structured output reliability. | Measured quality is for Q6_K_L, not IQ4_XS. Slower than qwen baseline. |
| Gemma4 26B A4B Q4_K_M | 4/4 | Strong on the small utility suite. | Less broad coverage than Qwen3.6 SLM benchmark. |
| Qwen3.6 35B A3B IQ4_XS | 17/24 then 18/24 | Best measured always-on balance. Good routing, extraction, mutation guard, and approval-risk behavior. | Still weak on some condensation and Portuguese/status tasks. |
| GLM-4.7-Flash IQ4_XS | 5/8 | Approval-clean utility validator. Passed all utility tasks and all critical tasks in the wave2 suite. | Failed several SLM/localized tasks; measured 14.26 tg64 on 7900 and 24.99 tg64 on guarded 9070, below the 30 tok/s target. |
| LFM2 24B A2B Q4_K_M | 6/8 | Best fast side-model result in the expanded 7900 wave. Very strong latency and broad utility coverage. | Failed mutation guard, so it cannot be trusted for approval/routing authority. |
| Gemma3 12B IT Q4_K_M | 5/8 | Usable small structured helper. | Failed route-message and mutation guard; not approval-clean. |
| Devstral Small 2 24B Q3_K_M | 4/8 | Coding-family candidate did not transfer well to Hermes utility work. | Failed all critical tasks in the wave2 suite. |
| Qwen3.5 4B Q8 | 3/4 | Fast and competent for simple extraction/utility work. | Failed route-message JSON; not suitable as final decision-maker. |
| Qwen3-Coder 30B A3B Q3/Q6 | 5/8 for Q3 in wave2; earlier Q3/Q6 rows were 2/4 or 2/6 | Q3 is useful for SLM-ish extraction and mutation checks. | Still failed utility routing, condensation, and localized status; Q6 is not a clean full-7900 service fit. |
| Kimi-VL A3B Q4_K_M | not task-scored | Likely useful as the local vision lane; throughput is excellent. | Needs the same utility/quality suite before being trusted for routing. |
| Kimi-Linear 48B A3B Q4_K_M | not task-scored | Promising split-only large Moonshot text model. | Throughput-only so far; quality is inferred, not measured. |
| Moonlight 16B A3B Q4/Q6 | not task-scored | Plausible Moonshot text lane, good Q4 throughput. | Needs utility and task scoring. |

Task benchmark evidence:

- `qwen3.5-4b:q8`: 3/4, avg 0.90s/task.
- `gemma4-26b-a4b-it:q4km`: 4/4, avg 2.22s/task.
- `glm-4.7-flash:q6kl`: 4/4, avg 5.38s/task.
- `qwen3.6-35b-a3b:iq4xs`: 17/24 then 18/24, avg 0.78s and
  0.88s/task in the SLM utility runs.
- `glm-4.7-flash:iq4xs`: 5/8, avg 0.77s/task; 3/3 critical.
- `lfm2-24b-a2b:q4km`: 6/8, avg 0.55s/task; failed mutation guard.
- `gemma3-12b-it:q4km`: 5/8, avg 1.38s/task; failed route and mutation guard.
- `devstral-small2-24b:q3km`: 4/8, avg 1.39s/task; failed critical tasks.
- `qwen3-coder-30b-a3b:q3km`: 5/8 in wave2; earlier rows were 2/4 and
  2/6 in the first expanded runs.
- `qwen3-coder-30b-a3b:q6k`: 2/4.

## Quality Ranking

This ranking combines measured task accuracy, observed stability, and model
fit on this hardware. Items marked "unmeasured" need the utility suite before
they should be treated as quality winners.

1. `glm-4.7-flash:q6kl`
   - Best measured utility result: 4/4.
   - Best when correctness matters more than latency.
   - Niche: careful structured utility work, JSON extraction, final validation.

2. `glm-4.7-flash:iq4xs`
   - Best measured approval-clean single-card validator candidate: 5/8 and
     3/3 critical.
   - Niche: secondary validator for utility routing, approval-risk checks, and
     structured JSON review.
   - Not a primary local model: SLM/localized behavior was weak and direct
     generation throughput did not clear 30 tok/s in the existing 7900/9070
     direct rows.

3. `qwen3.6-35b-a3b:iq4xs`
   - Best measured always-on balance: 17/24 then 18/24.
   - Niche: default Hermes utility/router model on the 7900 XT.
   - Strong on approval-risk, mutation guard, intent routing, and service
     command extraction.

4. `lfm2-24b-a2b:q4km`
   - Best fast expanded-wave helper: 6/8 and 103.76 tg64 on the 7900.
   - Niche: fast extraction, status, and low-risk helper work.
   - Failed mutation guard, so do not use as an approval authority.

5. `gemma4-26b-a4b-it:q4km`
   - Strong small-suite result: 4/4.
   - Niche: quality fallback for small utility tasks.
   - Needs broader repeated testing before displacing Qwen3.6.

6. `qwen3-coder-30b-a3b:q3km`
   - Q3 fits as a single-7900 service and passed SLM mutation/routing checks.
   - Niche: coding-oriented helper or extraction tests.
   - Failed utility routing, condensation, and localized status.

7. `kimi-linear-48b-a3b:q4km` split
   - Split-only on this box.
   - Throughput: 116.47 pp512 / 31.36 tg64.
   - Niche: strongest practical Moonshot pure-text candidate by size.
   - Quality is not measured yet; run the utility suite before trusting it.

8. `kimi-vl-a3b-thinking:q4km`
   - Best practical Kimi/Moonshot vision lane.
   - 7900 XT alone: 2565.27 pp512 / 100.74 tg64.
   - Niche: local vision and multimodal experiments.
   - Text utility quality is not measured yet.

9. `moonlight-16b-a3b:q4km`
   - Good generation speed on the 7900 XT: 99.74 tg64.
   - Niche: fast Moonshot text experiments.
   - Quality is not measured yet.

10. `qwen3.5-4b:q8`
   - Very fast and small.
   - Niche: cheap prefilter, extraction helper, low-risk short tasks.
   - Do not use as the final approval/routing authority.

11. `devstral-small2-24b:q3km`
   - Poor measured Hermes utility performance despite acceptable throughput.
   - Niche: possible coding-specific experimentation only.
   - Do not route Hermes utility, mutation, or approval decisions to it.

## Pros, Cons, And Niches

### Qwen3.6 35B A3B IQ4_XS

Pros:

- Best current production balance.
- Runs on the 7900 XT service.
- Strong measured SLM/utility behavior.
- Fast enough for interactive use.

Cons:

- Not the highest measured accuracy.
- Some condensation and language-specific status tasks fail.
- Still occupies most of the 7900 XT VRAM.

Use for:

- Default Hermes utility/routing baseline.
- Intent routing.
- Mutation guard.
- Approval-risk classification.
- Service command extraction.

### GLM-4.7-Flash

Pros:

- Best measured structured utility accuracy at Q6_K_L.
- Good "Big Pickle-adjacent" local candidate.
- Strong candidate for final check/validation work.
- Q6_K_L runs better on the 7900 XT than on the guarded 9070 sidecar in the
  expanded pass: 35.32 tg64 direct bench on the 7900 versus 26.95 completion
  tok/s in the 9070 endpoint run.
- IQ4_XS passed all utility and critical tasks in the broader 8-task wave2
  suite, making it the best measured secondary validator fit.

Cons:

- Q6_K_L is slower.
- IQ4_XS failed SLM/localized tasks and did not clear the 30 tok/s target in
  direct single-card rows.
- IQ4_XS split failed with ROCm error.

Use for:

- Accuracy-first local text tasks.
- Structured JSON tasks.
- Validation and second-pass review.
- Secondary approval/routing validation, not broad primary local chat.

### LFM2 24B A2B Q4_K_M

Pros:

- Fastest useful expanded-wave helper: 103.76 tg64 on the 7900.
- Best broader-wave pass count after the earlier primary baseline: 6/8.
- Good for extraction, condensation, and low-risk utility summaries.

Cons:

- Failed mutation guard.
- Not approval-clean despite speed.

Use for:

- Fast helper model.
- Low-risk extraction or condensation.
- Candidate for non-authoritative sidecar work.

### Kimi-Linear 48B A3B Q4_K_M

Pros:

- Largest practical Moonshot text model tested on this hardware.
- Runs across both GPUs with true split.
- Gives access to a stronger class of model than either card can fit alone.

Cons:

- Split-only.
- Generation throughput is modest: 31.36 tg64.
- Quality not yet measured with Hermes tasks.
- Uses the display GPU, so it must stay guarded.

Use for:

- Quality experiments where latency is acceptable.
- Moonshot/Kimi pure-text testing.
- Candidate for broad reasoning or long-context tests after quality evals.

### Kimi-VL A3B Thinking Q4_K_M

Pros:

- Fits and runs well on either GPU.
- Excellent 7900 XT throughput: 100.74 tg64.
- True split also works.
- Best practical local Moonshot/Kimi vision lane.

Cons:

- Text utility quality not scored yet.
- Vision projector behavior was not benchmarked in this pass; `llama-bench`
  measured the language model path.

Use for:

- Vision and multimodal local experiments.
- Image-question routing once a vision-specific eval exists.
- Fast Moonshot-family text smoke tests.

### Moonlight 16B A3B

Pros:

- Q4_K_M is fast on the 7900 XT.
- Single-card friendly.
- Q4_K_M true split works.

Cons:

- Q6_K behaves poorly on the 7900 XT in this run and split aborted.
- No task-quality score yet.

Use for:

- Single-card Moonshot-family text experiments.
- Fast non-critical generation.

### Qwen3.5 4B Q8

Pros:

- Very fast.
- 4B Q8 is easy to fit.
- Good enough for simple extraction and small utility tasks.

Cons:

- Failed route-message JSON.
- Not reliable enough for approval, mutation, or final routing decisions.

Use for:

- Cheap prefilter.
- Low-risk extraction.
- Smoke tests.

### Gemma4 26B A4B Q4_K_M

Pros:

- 4/4 on the small utility benchmark.
- Good candidate quality fallback.
- True split improves prompt throughput.

Cons:

- 7900 alone still has better generation throughput than split.
- Broader quality evidence is limited.

Use for:

- Small structured utility tasks.
- Quality comparison baseline against GLM and Qwen3.6.

### Qwen3-Coder 30B A3B

Pros:

- Coding-oriented model family.
- Some extraction and approval-risk tests passed.
- Q3_K_M runs as a realistic single-7900 service and scored 5/8 in wave2.
- Q6_K is a partial/offload benchmark only; it failed to load as a full 7900
  temporary server because it attempted a roughly 23.1 GiB allocation.

Cons:

- Failed routing, condensation, and localized status tasks.
- Q6_K is not a clean single-card service candidate.

Use for:

- Coding-specific tests only, not Hermes utility routing.

## Split Mode Interpretation

Split mode is a capacity tool, not a quality tool. Running the same model and
quant split across two GPUs should not materially improve answer quality by
itself. The quality improvement comes when split mode enables a larger model or
higher quant that cannot fit on one card.

Observed split behavior:

- `ROCm1/ROCm0` is the stable split direction.
- `ROCm0/ROCm1` and some larger reverse split cases aborted in ROCm.
- Prompt throughput often improves with split.
- Generation throughput often gets worse versus the 7900 XT alone for models
  that already fit on one card.
- Split is worthwhile for models that otherwise do not fit, especially
  `Kimi-Linear 48B Q4_K_M`.

## Current Recommendations

Default practical model:

- `qwen3.6-35b-a3b:iq4xs` on the 7900 XT.

Accuracy-first local model:

- `glm-4.7-flash:q6kl`, pending latency tolerance.

Secondary validator:

- `glm-4.7-flash:iq4xs` for approval/routing validation. It is approval-clean
  in the 8-task wave2 run, but it is not broad enough to replace the primary.

Fast side helper:

- `lfm2-24b-a2b:q4km` for non-authoritative utility/extraction work.

Best split-only Moonshot text candidate:

- `Kimi-Linear 48B A3B Q4_K_M`.

Best Moonshot/Kimi vision candidate:

- `Kimi-VL A3B Thinking Q4_K_M`.

Fast local helper:

- `qwen3.5-4b:q8`.

Avoid for Hermes utility routing:

- `devstral-small2-24b:q3km`.
- `gemma3-12b-it:q4km`.
- `qwen3-coder-30b-a3b:q3/q6` as a final router; Q3 can still be tested for
  coding helper niches.

## Needed Follow-Up Benchmarks

Run the same Hermes utility/quality suite against:

- `Kimi-Linear 48B A3B Q4_K_M` split.
- `Kimi-VL A3B Thinking Q4_K_M` on the 7900 XT.
- `Moonlight 16B A3B Q4_K_M`.
- `Qwen3 14B Q4_K_M`.
- `Nemotron Nano 9B v2 Q4_K_M` once the Hugging Face download resumes; the
  2026-04-22 unauthenticated transfer stalled with only a partial cache file.

Then repeat the best candidates with at least three repetitions so quality
rankings are based on task accuracy rather than throughput and model size.
