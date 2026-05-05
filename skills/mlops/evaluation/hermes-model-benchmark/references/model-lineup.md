# Hermes Local Model Lineup

This lineup is based on the installed GGUF files in `/opt/models/hermes-bench/`. Treat aliases as the service `MODEL_ALIAS` values to expose through llama.cpp.

| Alias | GGUF | Initial role | GPU target | Suggested port | Notes |
| --- | --- | --- | --- | --- | --- |
| `qwen3.5-4b:q8` | `Qwen_Qwen3.5-4B-Q8_0.gguf` | fast smoke, routing, small auxiliary work | RX 7900 XT or RX 9070 XT | 8010 | Service installed on 9070; smoke result 1/3, so keep as plumbing/smoke only. |
| `qwen3.5-9b:q6` | `Qwen_Qwen3.5-9B-Q6_K.gguf` | fast general auxiliary model | RX 7900 XT or RX 9070 XT | 8011 | Service installed on 9070; smoke result 1/3, not a default auxiliary candidate yet. |
| `gemma4-e4b-it:q8` | `google_gemma-4-E4B-it-Q8_0.gguf` | fast non-Qwen comparison | RX 7900 XT or RX 9070 XT | 8012 | Service installed on 9070; smoke result 2/3 and passed Discord/tool workflow. |
| `gemma4-26b-a4b-it:q4km` | `google_gemma-4-26B-A4B-it-Q4_K_M.gguf` | big/smart non-Qwen comparison | RX 9070 XT partial offload | 8013 | Service installed with `GPU_LAYERS=20`, `CTX_SIZE=8192`, q4 KV; smoke result 2/3 but slower. Full offload OOMs on 9070. |
| `qwen3.6-35b-a3b:iq4xs` | `Qwen_Qwen3.6-35B-A3B-IQ4_XS.gguf` | current primary baseline | live service | 8001 host / 8002 pod proxy | Default Hermes local model. Keep as the baseline in every comparison. |
| `qwen3.6-35b-a3b:q5km` | `Qwen_Qwen3.6-35B-A3B-Q5_K_M.gguf` | quality candidate | likely two-GPU or reduced context | 8014 | Compare quality uplift against latency and VRAM pressure. |
| `qwen3.6-35b-a3b:q6k` | `Qwen_Qwen3.6-35B-A3B-Q6_K.gguf` | highest-quality local Qwen candidate | likely two-GPU or reduced context | 8015 | Use only when operator confirms GPU headroom. |

## Kimi / Moonshot Watch Lane

Kimi-family open-weight models are worth watching for reasoning and long-context work, but do not auto-download them into this stack. Current Kimi-class releases are generally much larger than the small/fast slots here, and a practical Hermes candidate needs one of:

- a small or distilled Kimi-family model,
- a proven GGUF quant that fits local VRAM with the desired context,
- or a remote/provider route that does not consume the local GPUs.

When a candidate appears, add it to this table only after recording the GGUF path, alias, expected VRAM, context target, and benchmark role.

Starting watch links:

- Official Kimi K2 base model: <https://huggingface.co/moonshotai/Kimi-K2-Base>
- Official Gemma 4 26B-A4B instruction model: <https://huggingface.co/google/gemma-4-26B-A4B-it>
- Gemma 4 26B-A4B GGUF quants: <https://huggingface.co/bartowski/google_gemma-4-26B-A4B-it-GGUF>

## 2026-04-21 External Candidate Scout

The installed lineup is useful but too narrow. It mostly compares variants of
the current Qwen/Gemma path. Add candidates only one at a time, record disk
size, exact GGUF filename, service flags, utility pass rate, full Hermes smoke
pass rate, and throughput.

Current constraints:

- RX 7900 XT has 20 GB VRAM and runs the live primary service.
- RX 9070 XT has 16 GB VRAM and is the safest test card.
- Mixed 9070+7900 HIP split currently fails under this llama.cpp runtime, so
  treat combined-GPU candidates as blocked until Vulkan, ik_llama.cpp, or a
  newer HIP build proves otherwise.
- `/home` has limited headroom; download one candidate at a time and delete
  nonfunctional files after capturing the failure.

Highest-priority candidates:

| Candidate | Why test it | First quant/size target | Expected role | Source |
| --- | --- | --- | --- | --- |
| Qwen3-Coder 30B-A3B Instruct | Coding-specialized MoE with 30.5B total / 3.3B active params, 262K native context, and agentic-coding focus. This is the most obvious non-current-Qwen branch. | Start around 12-15 GB: IQ3/Q3_K_M/UD-Q3. Try IQ4_XS only on the 7900 or after confirming 9070 headroom. | coding sidecar, PR/worktree tasks, agentic code benchmark | <https://huggingface.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF> |
| Devstral Small 2 24B Instruct | Mistral-family coding model; useful diversity against Qwen-family behavior. Expect 16 GB fit to be quant/context sensitive. | IQ3_S/Q3_K_M first at reduced context; Q4_K_M only on the 7900 or after a 9070 fit check. | coding sidecar, alternate patch/review model | <https://huggingface.co/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF> |
| Qwen3 14B | Dense mid-size baseline. Reddit reports useful 16 GB coding performance with Q6_K and quantized KV; official GGUF exists. | Q4_K_M for first smoke; Q6_K if 9070 headroom allows; Q8_0 only on 7900. | dense general/coding baseline between 9B and 30B-A3B | <https://huggingface.co/Qwen/Qwen3-14B-GGUF> |
| Gemma 3 12B / QAT | Non-Qwen general-purpose baseline. QAT/GGUF variants are reported to fit 12-16 GB class GPUs with lower memory than naive quants. | Q4_K_M or QAT-int4. | general summarization, Discord/gateway style, extraction | <https://huggingface.co/bartowski/google_gemma-3-12b-it-GGUF> |
| Phi-4 mini instruct / reasoning | Very small Microsoft-family baseline. Useful for fast reasoning/labels if tokenizer/template bugs are avoided; prefer fixed Unsloth GGUFs. | Q8_0 or Q6_K for mini; use `--jinja` for reasoning variants. | fast utility lane, reasoning labels, cheap smoke | <https://huggingface.co/unsloth/Phi-4-mini-instruct-GGUF> |
| LFM2 2.6B / 2.6B-Exp | True tiny utility lane and different hybrid architecture. Liquid positions LFM2 for on-device speed/memory efficiency; Reddit signal is positive for narrow production tasks. | Find a verified GGUF or convert in a scratch path; do not assume the HF safetensors repo is directly llama.cpp-ready. | pulse condensation, classification, structured extraction, CPU/iGPU fallback tests | <https://huggingface.co/LiquidAI/LFM2-2.6B-Exp> |
| LFM2 24B-A2B | New MoE branch with GGUF quant options. Worth watching after tiny LFM2 and Qwen3-Coder because it may fit the “large total / small active” Hermes pattern. | Q4_K_M first, likely 7900 or CPU-offload; do not auto-download. | experimental MoE sidecar | <https://www.liquid.ai/blog/lfm2-24b-a2b> |

Community signal to preserve:

- Qwen3-Coder 30B-A3B and Devstral Small 2 are both being packaged in
  low-bit GGUFs for consumer cards, but at least one Devstral IQ3_S 32K-context
  report did not fit in 16 GB. Treat 9070 fits as empirical, not guaranteed:
  <https://www.reddit.com/r/LocalLLM/comments/1r9xifw/devstral_small_2_24b_qwen3_coder_30b_quants_for/>
- Devstral Small 2 community signal is positive for coding quality, but users
  still compare it against Qwen3-Coder 30B and larger 16 GB/32 GB tradeoffs:
  <https://www.reddit.com/r/LocalLLaMA/comments/1ry93gz/devstral_small_2_24b_severely_underrated/>
- Phi-4 mini has known tokenizer/template history; prefer fixed GGUFs and
  verify with the Hermes benchmark before trusting it:
  <https://www.reddit.com/r/LocalLLaMA/comments/1j0muz1/phi4mini_bug_fixes_ggufs/>
- LFM2 is worth testing because narrow tuned small models are increasingly
  useful for production side tasks:
  <https://www.reddit.com/r/LocalLLaMA/comments/1rvh74f/we_benchmarked_15_small_language_models_across_9/>

Runtime experiments:

1. Keep production on llama.cpp HIP GGUF serving.
2. Build a separate llama.cpp Vulkan binary and retry 9070+7900 split there;
   Vulkan may avoid the current mixed `gfx1201`/`gfx1100` HIP kernel-image
   failure, though performance may be lower.
3. Build `ik_llama.cpp` in a separate checkout for MoE/CPU-expert-offload
   experiments only. Do not replace the production llama.cpp binary until a
   candidate beats the current service on Hermes tasks and stability.
4. Keep vLLM/SGLang as lower-priority for this workstation because the current
   useful artifacts are GGUF-first and the mixed AMD cards already work better
   as host-side llama.cpp services than as an in-cluster serving stack.

## Initial Benchmark Order

1. Prove script and service plumbing with `qwen3.5-4b:q8` or `gemma4-e4b-it:q8`.
2. Compare fast auxiliary candidates: `qwen3.5-9b:q6` vs `gemma4-e4b-it:q8`.
3. Compare primary candidates against the live baseline: `qwen3.6-35b-a3b:iq4xs` vs `gemma4-26b-a4b-it:q4km`.
4. Test heavier Qwen quantizations only after GPU headroom and service stability are confirmed.

## 9070 Service State From 2026-04-21 Smoke

Installed user services:

- `hermes-llama-qwen35-4b-9070.service` on port 8010
- `hermes-llama-qwen35-9b-9070.service` on port 8011
- `hermes-llama-gemma4-e4b-9070.service` on port 8012
- `hermes-llama-gemma4-26b-9070.service` on port 8013
- `hermes-llama-qwen36-q5-9070.service` on port 8014
- `hermes-llama-qwen36-q6-9070.service` on port 8015

Only one 9070 candidate should normally run at a time. The 7900 live primary service remains `hermes-llama-qwen36.service` on host port 8001.

Do not use wildcard cleanup commands. In particular, never run
`systemctl --user stop 'hermes-llama*.service'`; it can stop the live primary
Qwen service. Stop candidates explicitly:

```bash
SERVICE_NAME=hermes-llama-gemma4-e4b-9070.service \
deploy/k8s/hermes-llama-qwen36-service.sh stop
```

All 9070 candidate services must be rendered with:

```bash
GPU_GUARD_PROFILE=amd-node-a
GPU_GUARD_NICE=19
GPU_GUARD_IONICE=1
```

Run `deploy/k8s/hermes-llama-qwen36-service.sh guard-check` before `apply` or
`restart`. The helper also emits a systemd `ExecStartPre` guard and low-priority
`nice`/`ionice` wrapper when `GPU_GUARD_PROFILE` is set. If Steam/gamescope,
Proton/Wine, Lutris/Heroic, or another protected game runner is active, the
service must not start. Use `GPU_GUARD_BYPASS=1` only when the operator has
explicitly confirmed the GPU is free for testing.

Smoke command:

```bash
source .venv/bin/activate
python scripts/hermes_model_benchmark.py \
  --base-url http://10.0.0.10:<port>/v1 \
  --models <alias> \
  --tasks logic_number,logic_json_rule,discord_status_reply \
  --repetitions 1 \
  --output-dir benchmark_runs/hermes_model_benchmark_9070_smoke
```

Observed pass rates:

- `qwen3.5-4b:q8`: 1/3, failed arithmetic and Discord formatting.
- `qwen3.5-9b:q6`: 1/3, failed arithmetic and Discord formatting.
- `gemma4-e4b-it:q8`: 2/3, passed JSON and Discord/tool workflow.
- `gemma4-26b-a4b-it:q4km`: 2/3, passed JSON and Discord/tool workflow; slower due partial offload.

## 2026-04-21 Throughput Comparison

Measured with `scripts/llama_throughput_compare.py`, 3 repetitions, fixed prompt, `max_tokens=160`, non-streaming OpenAI-compatible llama.cpp API. Values are llama.cpp median timing fields, not wall-clock queue time.

| Model | Host/GPU mode | Prompt tok/s | Generation tok/s | Median wall seconds | Notes |
| --- | --- | ---: | ---: | ---: | --- |
| `qwen3.5-4b:q8` | 9070 full offload | 1408.90 | 80.99 | 2.02 | Fastest generation, but weak smoke quality. |
| `qwen3.6-35b-a3b:iq4xs` | 7900 live primary full offload | 576.99 | 74.82 | 39.31 | Best current primary baseline; wall time includes live-service queue/context effects. |
| `qwen3.5-9b:q6` | 9070 full offload | 877.15 | 62.33 | 2.64 | Fast, but weak smoke quality. |
| `gemma4-e4b-it:q8` | 9070 full offload | 1225.72 | 61.87 | 2.63 | Best small candidate so far: passes tool/Discord smoke. |
| `gemma4-26b-a4b-it:q4km` | 9070 partial offload, `GPU_LAYERS=20` | 178.08 | 26.16 | 6.44 | Functional big Gemma candidate; slower but passed tool/Discord smoke. |
| `qwen3.6-35b-a3b:q5km` | 9070 partial offload, `GPU_LAYERS=20` | 107.55 | 20.02 | 8.49 | Functional quality candidate, slower than Gemma 26B. |
| `qwen3.6-35b-a3b:q6k` | 9070 partial offload, `GPU_LAYERS=20` | 91.31 | 16.23 | 10.50 | Functional but slowest candidate. |

Raw JSON results are under `benchmark_runs/llama_throughput/`.

## 2026-04-21 Small Utility Model Tests

Small local models should be tested against small-model jobs, not full-agent
jobs. Added utility-only benchmark tasks to
`scripts/hermes_model_benchmark.py`:

- `utility_route_message_json`
- `utility_extract_actions_json`
- `utility_approval_risk_json`
- `utility_pulse_condense`

These tasks use no tools and test cheap side work: route labels, log/action
extraction, approval labels for both mutating and read-only commands, restart
cooldown judgment, and pulse condensation.

Command shape:

```bash
source .venv/bin/activate
python scripts/hermes_model_benchmark.py \
  --base-url http://10.0.0.10:<port>/v1 \
  --models <alias> \
  --tasks utility_route_message_json,utility_extract_actions_json,utility_approval_risk_json,utility_pulse_condense,utility_readonly_risk_json,utility_restart_cooldown_json \
  --repetitions 1 \
  --output-dir benchmark_runs/hermes_model_benchmark_small_utility
```

Observed results:

| Model | Utility pass rate | Avg seconds/task | Notes |
| --- | ---: | ---: | --- |
| `qwen3.5-4b:q8` | 3/4 | 0.90 | Passed extraction, explicit approval-risk, and pulse condensation. Failed conditional restart routing by returning `needs_approval: false`. |
| `qwen3.5-9b:q6` | 3/4 | 1.15 | Same pattern as 4B: useful for extraction and condensation, not conservative enough for route approval. |
| `gemma4-e4b-it:q8` | 2/4 | 0.91 | Passed extraction and explicit approval-risk. Failed conditional restart routing and gave a too-vague pulse condensation. |
| `gemma4-26b-a4b-it:q4km` | 4/4 | 2.22 | Best quality utility sidecar, but not a small/fast lane. Use when the 9070 is free and quality matters more than latency. |

Recommendation:

- Use `qwen3.5-4b:q8` or `qwen3.5-9b:q6` only for low-risk utility work:
  pulse condensation, short status summaries, structured extraction, cheap
  labels with deterministic post-rules.
- Do not use the small Qwen/Gemma models as autonomous approval gates. They
  marked a conditional deployment restart as not requiring approval.
- Keep approval-critical routing on Codex/Claude or enforce a deterministic
  post-rule: any deploy/restart/sudo/kubectl-mutating action requires approval
  regardless of the model label.
- Keep `gemma4-26b-a4b-it:q4km` as the quality 9070 sidecar when available.

Raw JSON results are under
`benchmark_runs/hermes_model_benchmark_small_utility/`.

## 2026-04-21 SLM Candidate Lane

Goal: test true small language models against the utility and SLM-specific
Hermes tasks before assigning them any production sidecar role. Treat SLMs as
single-job specialists, not replacement primary agents.

The first-pass candidate manifest lives at
`benchmarks/llm/slm_candidates.tsv`. It intentionally favors GGUF models that
fit many times over on the RX 9070 XT 16 GB and RX 7900 XT 20 GB cards. Most
Q4/Q8 files below are under 1.5 GB, so multiple aliases can be served per card
if llama.cpp service memory, KV cache, and port management are kept separate.

Highest-priority SLMs:

| Candidate | Why test it | First quant | Expected role | Source |
| --- | --- | --- | --- | --- |
| LFM2.5 1.2B Instruct | Current strongest practical SLM candidate: Liquid reports 1.2B params, <1 GB class memory, strong instruction following/tool-use, and GGUF support. | Q4_K_M | default utility SLM: routing, extraction, pulse condensation | <https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF> |
| LFM2.5 1.2B Thinking | Same memory class, but tuned for reasoning-heavy tasks. Test against mutation guards and approval-adjacent labels. | Q4_K_M | reasoning utility, conservative route labels | <https://huggingface.co/LiquidAI/LFM2.5-1.2B-Thinking-GGUF> |
| Qwen3 0.6B | Tiny official Qwen GGUF. It supports Qwen3 thinking/non-thinking mode, 32K context, and 100+ languages, so it is a good lower-bound control. | Q8_0 | tiny CPU/GPU multiplex control | <https://huggingface.co/Qwen/Qwen3-0.6B-GGUF> |
| Qwen3 1.7B | Official Qwen GGUF with the same agent/multilingual family behavior at a more plausible capability point. | Q8_0 | tiny agent/tool-control baseline | <https://huggingface.co/Qwen/Qwen3-1.7B-GGUF> |
| LFM2.5 1.2B JP | Japanese-optimized SLM. Useful to test whether truly localized SLMs can beat general models for platform-specific language lanes. | Q4_K_M | Japanese gateway/research sidecar | <https://huggingface.co/LiquidAI/LFM2.5-1.2B-JP-GGUF> |
| Gemma 3 1B IT | Popular 1B Gemma baseline with many GGUF variants. Use as the Google-family tiny control. | Q4_K_M | extraction/summary control | <https://huggingface.co/ggml-org/gemma-3-1b-it-GGUF> |
| Phi-4 mini instruct | 3.8B is borderline SLM/small-LLM, but Microsoft reports strong instruction following and function calling with 128K context. | Q4_K_M or Q6_K | upper-bound SLM control | <https://huggingface.co/lmstudio-community/Phi-4-mini-instruct-GGUF> |
| SmolLM3 3B | Fully open 3B long-context/reasoning model from Hugging Face. Good independent architecture/control lane. | Q6_K or Q8_0 | open 3B control | <https://huggingface.co/ggml-org/SmolLM3-3B-GGUF> |

SLM-specific benchmark tasks added to `scripts/hermes_model_benchmark.py`:

- `slm_intent_route_json`
- `slm_mutation_guard_json`
- `slm_extract_service_command_json`
- `slm_portuguese_status_summary`
- `slm_spanish_status_summary`

Run shape for one served candidate:

```bash
MODEL=lfm25-12b-instruct:q4km \
BASE_URL=http://10.0.0.10:8016/v1 \
benchmarks/llm/run_slm_utility_bench.sh
```

Recommended comparison set:

```bash
source venv/bin/activate
python scripts/hermes_model_benchmark.py \
  --base-url http://10.0.0.10:<port>/v1 \
  --models <slm-alias>,qwen3.5-4b:q8,qwen3.5-9b:q6,gemma4-e4b-it:q8,qwen3.6-35b-a3b:iq4xs \
  --tasks utility_route_message_json,utility_extract_actions_json,utility_approval_risk_json,utility_pulse_condense,utility_readonly_risk_json,utility_restart_cooldown_json,slm_intent_route_json,slm_mutation_guard_json,slm_extract_service_command_json,slm_portuguese_status_summary,slm_spanish_status_summary \
  --repetitions 3 \
  --output-dir benchmark_runs/hermes_model_benchmark_slm_utility
```

Decode sweep policy for this lane:

- Use `TEMPERATURE=0.0` as the default comparison preset for all SLMs.
- Only tuned finalists get sampler sweeps.
- Keep throughput on `scripts/llama_throughput_compare.py` unchanged and
  deterministic; sampler tuning belongs in the utility harness, not the raw
  tok/s harness.
- When sweeping the same model, set `DECODE_LABEL=...` so result files and
  scorecards keep separate rows per preset while still reusing the base-model
  throughput row.

Acceptance gates:

- Utility SLM: at least 7/8 tasks over 3 repetitions and no failure on
  `utility_approval_risk_json` or `slm_mutation_guard_json`.
- Localized SLM: may fail unrelated English tasks, but must beat general
  baselines on its language-specific lane before it gets routed that traffic.
- Any model that marks deploy/restart/sudo/kubectl-mutating work as not needing
  review is rejected for approval-adjacent routing, regardless of speed.
- Throughput is secondary to valid JSON rate and conservative mutation labels.

Service plan:

1. Download one SLM at a time into `/opt/models/hermes-bench/`.
2. Serve candidates on ports starting at 8016.
3. Use `CTX_SIZE=8192` for first pass to maximize multiplexing. Raise only
   after a candidate passes utility quality.
4. Keep `CACHE_TYPE_K=q4_0 CACHE_TYPE_V=q4_0` for first pass unless a model
   shows quality instability.
5. For 9070 sidecar services, keep `ALLOW_DISPLAY_GPU_9070=1` and
   `GPU_GUARD_PROFILE=amd-node-a`; run guard-check before start.
6. Compare against existing LLM baselines using the same task set before
   assigning a route.

Initial result:

| Model | Hardware | Utility+SLM pass rate | Avg seconds/task | Generation tok/s | Verdict |
| --- | --- | ---: | ---: | ---: | --- |
| `lfm25-12b-instruct:q4km` | RX 9070 XT full offload | 8/24 | 0.26 | 234.18 | Very fast, but rejected for routing/approval: failed `utility_route_message_json`, `slm_intent_route_json`, and `slm_mutation_guard_json`. Still useful to revisit for pure extraction/condensation. |
| `qwen3.6-35b-a3b:iq4xs` | RX 7900 XT live primary | 18/24 | 0.88 | 73.30 | Much stronger quality baseline; passed all SLM English tasks and approval-risk runs. |

Raw results:

- `benchmark_runs/hermes_model_benchmark_slm_utility/results_20260421_095509.json`
- `benchmark_runs/hermes_model_benchmark_slm_utility/results_20260421_095555.json`
- `benchmark_runs/llama_throughput_slm/lfm25-12b-instruct-q4km.json`
- `benchmark_runs/llama_throughput_slm/qwen3.6-35b-a3b-iq4xs.json`
- `benchmark_runs/llama_7900_expanded_20260422T174500Z/summary.tsv`

### 2026-04-22 RX 7900 XT expansion

The later 9070-sidecar set now has a 7900-only `llama-bench` pass for every
candidate that could run without touching the display GPU. The batch stopped the
7900 Qwen service temporarily, ran `ROCm1` only with `--split-mode none`,
`--fit-target 768`, `--fit-ctx 8192`, then restored Qwen and the watchdog.

| Model | RX 7900 XT pp512 / tg64 | Result |
| --- | ---: | --- |
| Devstral Small 2 24B Q3_K_M | 761.45 / 34.29 | Runs; throughput only. |
| Gemma 3 12B IT Q4_K_M | 1251.65 / 39.27 | Runs; throughput only. |
| GLM-4.7-Flash Q6_K_L | 220.59 / 35.32 | Better single-card validator lane than the guarded 9070 endpoint result. |
| LFM2 2.6B Q8_0 | 4686.80 / 135.10 | Very fast small helper candidate. |
| LFM2 24B A2B Q4_K_M | 1109.72 / 103.76 | Runs well on the 7900. |
| Phi-4 mini Q8_0 | failed | HIP llama.cpp abort: `GGML_ASSERT(ggml_is_contiguous(a))`. |
| Qwen3 14B Q4_K_M | 1161.28 / 41.83 | Runs; quality still unscored. |
| Qwen3-Coder 30B A3B Q3_K_M | 941.59 / 72.95 | Runs, but prior Hermes utility score was weak. |
| Qwen3-Coder 30B A3B Q6_K | 249.09 / 41.21 | Runs as partial-fit; faster than the guarded 9070 endpoint result. |

Capability tracking:

- Human-maintained notes: `benchmarks/llm/model_capability_cards.md`
- Generated card output: `benchmarks/llm/model_capability_cards.generated.md`
- Generator: `scripts/model_capability_cards.py`

## 2026-04-21 Dual-GPU Split Findings

Goal: use the combined RX 9070 XT 16 GB + RX 7900 XT 20 GB pool for the large Qwen/Gemma candidates.

llama.cpp exposes the relevant split controls:

- `--device ROCm0,ROCm1`
- `--split-mode layer|row|tensor`
- `--tensor-split <9070 share>,<7900 share>`
- `--main-gpu <index>`

Tested with both llama services stopped so ROCm reported the 9070 and 7900 as free. Candidate attempts:

| Model/config | Split mode | Tensor split | Main GPU | Result |
| --- | --- | ---: | ---: | --- |
| `qwen3.6-35b-a3b:q5km` | `layer` | `16,20` | 1 | Loaded tensors across both GPUs, then aborted during warmup with `ROCm error: no kernel image is available for execution on the device` on ROCm0. |
| `qwen3.6-35b-a3b:q5km` | `row` | `16,20` | 1 | Loaded tensors across both GPUs, then aborted during warmup with the same ROCm0 kernel-image error. |
| `qwen3.6-35b-a3b:q5km` | `row` | `16,20` | 0 | Failed similarly. |
| `qwen3.6-35b-a3b:q6k` | `layer` / `row` | `16,20` | 1 | Failed before usable serving under the same mixed-card ROCm path. |
| `gemma4-26b-a4b-it:q4km` | `layer` | `16,20` | 1 | Failed under the same mixed-card ROCm path. |
| `qwen3.6-35b-a3b:iq4xs` | `layer` | `16,20` | 1 | Failed under the same mixed-card ROCm path. |

Override tests:

- No `HSA_OVERRIDE_GFX_VERSION`: the binary sees real `gfx1201` + `gfx1100`, but mixed execution aborts on ROCm0 with no usable kernel image.
- `HSA_OVERRIDE_GFX_VERSION=11.0.0`: both cards present as `gfx1100`, then the 9070 path raises an HSA hardware exception.
- `HSA_OVERRIDE_GFX_VERSION=12.0.1`: both cards present as `gfx1201`, but the mixed run does not become usable and stalls during model load/probe.

Conclusion: true 9070+7900 split is not currently usable with this HIP llama.cpp runtime, even though the individual cards work. Keep the current practical layout until the HIP/runtime issue is fixed:

- 7900 XT: `qwen3.6-35b-a3b:iq4xs` live primary.
- 9070 XT: `gemma4-26b-a4b-it:q4km` partial offload, or `gemma4-e4b-it:q8` for fast auxiliary work.

Raw failure logs are under `benchmark_runs/llama_split/logs/`.

## Minimum Result Record

For each run, capture:

- model alias,
- GGUF filename,
- host/GPU,
- llama.cpp command or service environment,
- benchmark command,
- pass rate by category,
- average latency,
- tool failures,
- notable formatting or instruction-following failures,
- recommendation: primary, auxiliary, gateway-only, coding-only, watch, or reject.
