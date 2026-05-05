---
name: hermes-model-benchmark
description: Benchmark local llama.cpp/GGUF models for Hermes roles on the Snapetech deployment. Use when expanding the local model library, comparing Qwen/Gemma/Kimi-family candidates, choosing primary or auxiliary Hermes models, or evaluating 7900/9070 XT llama.cpp services with scripts/hermes_model_benchmark.py.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, benchmark, llama.cpp, gguf, local-models, qwen, gemma, kimi, gpu]
    category: mlops
    related_skills: [llama-cpp, evaluating-llms-harness, research-best-practices]
---

# Hermes Model Benchmark

Use this skill to compare local llama.cpp models for Hermes-specific jobs: primary agent turns, fast auxiliary work, Discord/gateway replies, file/tool workflows, code patches, and synthesis.

## Safety Contract

- Do not replace the live primary model without explicit operator approval.
- Prefer a separate user service name and port for each candidate model.
- Do not download very large weights automatically; propose the disk/VRAM/runtime plan first.
- Keep GPU tests opportunistic. Avoid interrupting games, Steam/gamescope, Plex transcodes, or other protected workloads.
- Before starting any non-primary local GPU service, run the guard check. If it reports busy, stop and report why instead of starting the model.
- Candidate services on the 9070/7900 host must set `GPU_GUARD_PROFILE=amd-node-a`; this adds a systemd `ExecStartPre` check and starts the child under low CPU/IO priority.
- Never run wildcard stops such as `systemctl --user stop 'hermes-llama*.service'`; that can stop the live primary `hermes-llama-qwen36.service` and take Hermes offline.
- Stop candidates only with an explicit `SERVICE_NAME=... deploy/k8s/hermes-llama-qwen36-service.sh stop`. The helper refuses to stop the primary service unless `ALLOW_PRIMARY_STOP=1` is explicitly set.
- Record benchmark outputs under `benchmark_runs/hermes_model_benchmark/`; do not commit those run artifacts unless requested.

## Local Inventory

Start by checking the installed GGUFs:

```bash
find /opt/models/hermes-bench -maxdepth 1 -type f -name '*.gguf' -printf '%f\n' | sort
```

The current baseline lineup and service recommendations live in `references/model-lineup.md`.

## Start A Candidate Service

Use the existing systemd helper with environment overrides. Start candidates on alternate ports first:

```bash
SERVICE_NAME=hermes-llama-gemma4-e4b.service \
SERVICE_PATH="$HOME/.config/systemd/user/hermes-llama-gemma4-e4b.service" \
MODEL_PATH=/opt/models/hermes-bench/google_gemma-4-E4B-it-Q8_0.gguf \
MODEL_ALIAS=gemma4-e4b-it:q8 \
PORT=8012 \
GPU_GUARD_PROFILE=amd-node-a \
CTX_SIZE=32768 \
CACHE_TYPE_K=q8_0 \
CACHE_TYPE_V=q8_0 \
deploy/k8s/hermes-llama-qwen36-service.sh guard-check

SERVICE_NAME=hermes-llama-gemma4-e4b.service \
SERVICE_PATH="$HOME/.config/systemd/user/hermes-llama-gemma4-e4b.service" \
MODEL_PATH=/opt/models/hermes-bench/google_gemma-4-E4B-it-Q8_0.gguf \
MODEL_ALIAS=gemma4-e4b-it:q8 \
PORT=8012 \
GPU_GUARD_PROFILE=amd-node-a \
CTX_SIZE=32768 \
CACHE_TYPE_K=q8_0 \
CACHE_TYPE_V=q8_0 \
deploy/k8s/hermes-llama-qwen36-service.sh apply

SERVICE_NAME=hermes-llama-gemma4-e4b.service \
SERVICE_PATH="$HOME/.config/systemd/user/hermes-llama-gemma4-e4b.service" \
PORT=8012 \
GPU_GUARD_PROFILE=amd-node-a \
deploy/k8s/hermes-llama-qwen36-service.sh restart

PORT=8012 deploy/k8s/hermes-llama-qwen36-service.sh probe
```

Use the same pattern for each candidate, changing `SERVICE_NAME`, `SERVICE_PATH`, `MODEL_PATH`, `MODEL_ALIAS`, and `PORT`.
Use `GPU_GUARD_BYPASS=1` only when the operator explicitly says protected workloads are stopped and the 9070 is free for testing.

Clean up a candidate explicitly:

```bash
SERVICE_NAME=hermes-llama-gemma4-e4b.service \
deploy/k8s/hermes-llama-qwen36-service.sh stop
```

## Run The Hermes Benchmark

Activate the repo venv before running Python:

```bash
source venv/bin/activate
python scripts/hermes_model_benchmark.py --list-tasks
```

Smoke-test one served model:

```bash
python scripts/hermes_model_benchmark.py \
  --base-url http://10.0.0.10:8012/v1 \
  --models gemma4-e4b-it:q8 \
  --tasks logic_number,logic_json_rule,discord_status_reply \
  --repetitions 2
```

Run the default Hermes-focused suite once multiple services are exposed:

```bash
python scripts/hermes_model_benchmark.py \
  --base-url http://10.0.0.10:8002/v1 \
  --models qwen3.5-4b:q8,qwen3.5-9b:q6,qwen3.6-35b-a3b:iq4xs,gemma4-e4b-it:q8,gemma4-26b-a4b-it:q4km \
  --wait-for-models \
  --repetitions 3
```

For utility and routing comparisons, keep the baseline decode deterministic:

```bash
BASE_URL=http://10.0.0.10:8012/v1 \
MODEL=gemma4-e4b-it:q8 \
TEMPERATURE=0.0 \
benchmarks/llm/run_slm_utility_bench.sh
```

Only after a model survives the fixed-preset baseline should you try a narrow
finalist decode sweep:

```bash
BASE_URL=http://10.0.0.10:8012/v1 \
MODEL=gemma4-e4b-it:q8 \
TEMPERATURE=0.1 \
TOP_P=0.95 \
REPEAT_PENALTY=1.05 \
SEED=7 \
DECODE_LABEL=tuned-t0.1-p0.95-rp1.05 \
benchmarks/llm/run_slm_utility_bench.sh
```

Do not sweep sampler knobs across the full runtime matrix. First rank the
service/runtime settings, then tune decode on the short list.

## Interpret Results

- Primary Hermes model: prioritize pass rate, long-context reliability, tool-call behavior, and low tool failures over raw speed.
- Auxiliary summarizer/router: prioritize latency, formatting obedience, and enough reasoning for compression or routing.
- Gateway/Discord model: prioritize concise responses, no unwanted pings/markdown, and recovery/status clarity.
- Coding model: prioritize patch correctness and workspace discipline.

If a model wins only on speed but fails JSON, tool, or gateway-format tasks, keep it as a narrow auxiliary candidate rather than the default primary.
