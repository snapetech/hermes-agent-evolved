#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

source venv/bin/activate
export PYTHONUNBUFFERED=1

RUN_ROOT="${RUN_ROOT:-$REPO_ROOT/benchmark_runs/full_matrix_clean_$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_ROOT="$(python - "$RUN_ROOT" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).resolve())
PY
)"
QUALITY_DIR="$RUN_ROOT/quality"
THROUGHPUT_DIR="$RUN_ROOT/throughput"
LOG_DIR="$RUN_ROOT/logs"
MODELS_RUN_FILE="$RUN_ROOT/models_run.txt"

mkdir -p "$QUALITY_DIR" "$THROUGHPUT_DIR" "$LOG_DIR"
: > "$MODELS_RUN_FILE"

BASELINE_MODEL="${BASELINE_MODEL:-qwen3.6-35b-a3b:iq4xs}"
BASELINE_URL="${BASELINE_URL:-http://10.0.0.10:8001/v1}"
BASELINE_UNIT="${BASELINE_UNIT:-hermes-llama-qwen36.service}"
QUALITY_REPETITIONS="${QUALITY_REPETITIONS:-3}"
QUALITY_TIMEOUT="${QUALITY_TIMEOUT:-240}"
THROUGHPUT_REPETITIONS="${THROUGHPUT_REPETITIONS:-3}"
THROUGHPUT_TIMEOUT="${THROUGHPUT_TIMEOUT:-240}"
LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-/workspace/llama.cpp/build-hip/bin/llama-server}"

# Pin ROCm by UUID, then expose the filtered device as HIP index 0. Bare
# HIP_VISIBLE_DEVICES indices are fragile on this host: the 9070 XT is GPU0
# and currently owns the Wayland display.
GPU_7900_UUID="GPU-6bdce6ea1d388c5c"   # AMD Radeon RX 7900 XT, gfx1100
GPU_9070_UUID="GPU-2388c382a826700f"   # AMD Radeon RX 9070 XT, gfx1201

# Default OFF because the 9070 XT is the active display adapter. This gates
# solo/full-load 9070 tests. Guarded split tests are allowed separately: they
# keep the 7900 first and reserve display-card headroom.
ALLOW_DISPLAY_GPU="${ALLOW_DISPLAY_GPU:-0}"
ALLOW_SPLIT_DISPLAY_GPU="${ALLOW_SPLIT_DISPLAY_GPU:-1}"

TEMP_PIDS=()
TEMP_UNITS=()
BASELINE_WAS_ACTIVE=0

cleanup() {
  local status=$?

  for pid in "${TEMP_PIDS[@]:-}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done

  for unit in "${TEMP_UNITS[@]:-}"; do
    if [[ -n "$unit" ]]; then
      systemctl --user stop "$unit" >/dev/null 2>&1 || true
    fi
  done

  if [[ "$BASELINE_WAS_ACTIVE" -eq 1 ]]; then
    systemctl --user start "$BASELINE_UNIT" >/dev/null 2>&1 || true
  fi

  return "$status"
}

trap cleanup EXIT

remember_unit() {
  local unit="$1"
  TEMP_UNITS+=("$unit")
}

forget_unit() {
  local unit="$1"
  local kept=()
  local entry
  for entry in "${TEMP_UNITS[@]:-}"; do
    if [[ "$entry" != "$unit" ]]; then
      kept+=("$entry")
    fi
  done
  TEMP_UNITS=("${kept[@]:-}")
}

remember_pid() {
  local pid="$1"
  TEMP_PIDS+=("$pid")
}

forget_pid() {
  local pid="$1"
  local kept=()
  local entry
  for entry in "${TEMP_PIDS[@]:-}"; do
    if [[ "$entry" != "$pid" ]]; then
      kept+=("$entry")
    fi
  done
  TEMP_PIDS=("${kept[@]:-}")
}

warm_model() {
  local base_url="$1"
  local model="$2"

  python - "$base_url" "$model" <<'PY'
import json
import sys
import time

import requests

base_url = sys.argv[1].rstrip("/")
model = sys.argv[2]

payload = {
    "model": model,
    "messages": [{"role": "user", "content": "ping"}],
    "max_tokens": 1,
    "temperature": 0.0,
}

deadline = time.time() + 180
last_error = None
while time.time() < deadline:
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": "Bearer local"},
            json=payload,
            timeout=60,
        )
        if resp.status_code == 200:
            print("warm ok")
            raise SystemExit(0)
        last_error = f"{resp.status_code}: {resp.text[:200]}"
    except Exception as exc:  # pragma: no cover - best effort shell helper
        last_error = str(exc)
    time.sleep(5)

raise SystemExit(f"failed to warm {model} at {base_url}: {last_error}")
PY
}

run_quality() {
  local base_url="$1"
  local model="$2"
  local log_path="$LOG_DIR/${model//[:\/]/-}.quality.log"

  warm_model "$base_url" "$model" >> "$log_path" 2>&1
  python scripts/hermes_model_benchmark.py \
    --base-url "$base_url" \
    --models "$model" \
    --output-dir "$QUALITY_DIR" \
    --wait-for-models \
    --wait-timeout 900 \
    --repetitions "$QUALITY_REPETITIONS" \
    --task-timeout "$QUALITY_TIMEOUT" \
    --temperature 0.0 \
    >> "$log_path" 2>&1
}

run_throughput() {
  local base_url="$1"
  local model="$2"
  local safe_model="${model//[:\/]/-}"
  local log_path="$LOG_DIR/${safe_model}.throughput.log"

  python scripts/llama_throughput_compare.py \
    --base-url "$base_url" \
    --model "$model" \
    --repetitions "$THROUGHPUT_REPETITIONS" \
    --timeout "$THROUGHPUT_TIMEOUT" \
    --output "$THROUGHPUT_DIR/${safe_model}.json" \
    >> "$log_path" 2>&1
}

run_model() {
  local model="$1"
  local base_url="$2"

  printf '%s %s\n' "$model" "$base_url" >> "$MODELS_RUN_FILE"
  run_quality "$base_url" "$model"
  run_throughput "$base_url" "$model"
}

run_systemd_model() {
  local unit="$1"
  local port="$2"
  local model="$3"
  local base_url="http://10.0.0.10:${port}/v1"

  systemctl --user start "$unit"
  remember_unit "$unit"
  printf '%s %s %s\n' "$model" "$base_url" "$unit" >> "$MODELS_RUN_FILE"
  run_quality "$base_url" "$model"
  run_throughput "$base_url" "$model"
  systemctl --user stop "$unit"
  forget_unit "$unit"
}

run_temp_model() {
  local model="$1"
  local port="$2"
  local gpu_env="$3"
  local model_path="$4"
  local ctx_size="$5"
  local batch_size="$6"
  local ubatch_size="$7"
  shift 7
  local extra_args=("$@")
  local safe_model="${model//[:\/]/-}"
  local server_log="$LOG_DIR/${safe_model}.server.log"
  local base_url="http://10.0.0.10:${port}/v1"

  if [[ ! -x "$LLAMA_SERVER_BIN" ]]; then
    echo "missing llama-server binary: $LLAMA_SERVER_BIN" >&2
    return 1
  fi

  # shellcheck disable=SC2086
  env $gpu_env nohup /usr/bin/ionice -c 3 /usr/bin/nice -n 19 "$LLAMA_SERVER_BIN" \
      --host 10.0.0.10 \
      --port "$port" \
      --model "$model_path" \
      --alias "$model" \
      --ctx-size "$ctx_size" \
      --parallel 1 \
      --batch-size "$batch_size" \
      --ubatch-size "$ubatch_size" \
      --threads 16 \
      --threads-batch 16 \
      --gpu-layers 999 \
      --flash-attn on \
      --cache-type-k q4_0 \
      --cache-type-v q4_0 \
      --cache-ram 0 \
      --reasoning off \
      --jinja \
      "${extra_args[@]}" \
      >"$server_log" 2>&1 &
  local pid=$!
  remember_pid "$pid"

  printf '%s %s temp-pid=%s gpu_env=%s\n' "$model" "$base_url" "$pid" "$gpu_env" >> "$MODELS_RUN_FILE"
  run_quality "$base_url" "$model"
  run_throughput "$base_url" "$model"

  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
  forget_pid "$pid"
}

display_gpu_is_9070() {
  local status card_dir device_path
  for status in /sys/class/drm/card*-*/status; do
    [[ -e "$status" ]] || continue
    [[ "$(cat "$status" 2>/dev/null)" == "connected" ]] || continue
    card_dir="${status%%-*}"
    device_path="$(readlink -f "$card_dir/device" 2>/dev/null || true)"
    [[ "$device_path" == *"0000:03:00.0"* ]] && return 0
  done
  return 1
}

allow_9070_solo_tests() {
  if [[ "$ALLOW_DISPLAY_GPU" == "1" ]]; then
    return 0
  fi
  if display_gpu_is_9070; then
    echo "[full_matrix] skipping 9070 XT solo tests: 9070 owns a connected display. Set ALLOW_DISPLAY_GPU=1 only from a TTY/headless session or after moving Wayland to another GPU." >&2
    return 1
  fi
  return 0
}

allow_split_card_tests() {
  if [[ "$ALLOW_SPLIT_DISPLAY_GPU" != "1" ]]; then
    echo "[full_matrix] skipping split-card tests: ALLOW_SPLIT_DISPLAY_GPU=$ALLOW_SPLIT_DISPLAY_GPU" >&2
    return 1
  fi
  if display_gpu_is_9070; then
    echo "[full_matrix] allowing guarded split-card tests with 7900 main + reserved 9070 headroom" >&2
  fi
  return 0
}

run_model "$BASELINE_MODEL" "$BASELINE_URL"

if systemctl --user is-active --quiet "$BASELINE_UNIT"; then
  BASELINE_WAS_ACTIVE=1
  systemctl --user stop "$BASELINE_UNIT"
fi

run_temp_model \
  qwen3.6-27b:q5ks-7900 \
  8034 \
  "HIP_VISIBLE_DEVICES=0 ROCR_VISIBLE_DEVICES=$GPU_7900_UUID HSA_OVERRIDE_GFX_VERSION=11.0.0" \
  /mnt/disks/gamespool0/hermes-models/bench/Qwen_Qwen3.6-27B-Q5_K_S.gguf \
  4096 \
  512 \
  256

if allow_9070_solo_tests; then
  run_temp_model \
    qwen3.6-27b:q5ks-9070 \
    8035 \
    "HIP_VISIBLE_DEVICES=0 ROCR_VISIBLE_DEVICES=$GPU_9070_UUID HSA_OVERRIDE_GFX_VERSION=12.0.1" \
    /mnt/disks/gamespool0/hermes-models/bench/Qwen_Qwen3.6-27B-Q5_K_S.gguf \
    4096 \
    512 \
    256 \
    --fit on \
    --fit-target 768 \
    --fit-ctx 4096
fi

if allow_split_card_tests; then
  run_temp_model \
    qwen3.6-27b:q4km-split \
    8036 \
    "HIP_VISIBLE_DEVICES=0,1 ROCR_VISIBLE_DEVICES=$GPU_7900_UUID,$GPU_9070_UUID" \
    /mnt/disks/gamespool0/hermes-models/bench/qwen3.6-27b-q4_k_m.gguf \
    8192 \
    1024 \
    128 \
    --device ROCm0,ROCm1 \
    --split-mode layer \
    --tensor-split 12,8 \
    --main-gpu 0 \
    --fit on \
    --fit-target 768,4096 \
    --fit-ctx 8192

  run_temp_model \
    qwen3.6-27b:q5ks-split \
    8037 \
    "HIP_VISIBLE_DEVICES=0,1 ROCR_VISIBLE_DEVICES=$GPU_7900_UUID,$GPU_9070_UUID" \
    /mnt/disks/gamespool0/hermes-models/bench/Qwen_Qwen3.6-27B-Q5_K_S.gguf \
    8192 \
    1024 \
    128 \
    --device ROCm0,ROCm1 \
    --split-mode layer \
    --tensor-split 12,8 \
    --main-gpu 0 \
    --fit on \
    --fit-target 768,4096 \
    --fit-ctx 8192

  run_temp_model \
    qwen3.6-27b:q6k-split \
    8038 \
    "HIP_VISIBLE_DEVICES=0,1 ROCR_VISIBLE_DEVICES=$GPU_7900_UUID,$GPU_9070_UUID" \
    /mnt/disks/gamespool0/hermes-models/bench/Qwen3.6-27B-Q6_K.gguf \
    8192 \
    1024 \
    128 \
    --device ROCm0,ROCm1 \
    --split-mode layer \
    --tensor-split 12,8 \
    --main-gpu 0 \
    --fit on \
    --fit-target 768,4096 \
    --fit-ctx 8192

  run_temp_model \
    qwen3.6-27b:q8-split \
    8039 \
    "HIP_VISIBLE_DEVICES=0,1 ROCR_VISIBLE_DEVICES=$GPU_7900_UUID,$GPU_9070_UUID" \
    /mnt/disks/gamespool0/hermes-models/bench/Qwen3.6-27B-Q8_0.gguf \
    8192 \
    1024 \
    128 \
    --device ROCm0,ROCm1 \
    --split-mode layer \
    --tensor-split 12,8 \
    --main-gpu 0 \
    --fit on \
    --fit-target 768,4096 \
    --fit-ctx 8192
fi

if [[ "$BASELINE_WAS_ACTIVE" -eq 1 ]]; then
  systemctl --user start "$BASELINE_UNIT"
fi

if allow_9070_solo_tests; then
  while read -r unit port model; do
    run_systemd_model "$unit" "$port" "$model"
  done <<'EOF'
hermes-llama-qwen35-4b-9070.service 8010 qwen3.5-4b:q8
hermes-llama-qwen35-9b-9070.service 8011 qwen3.5-9b:q6
hermes-llama-gemma4-e4b-9070.service 8012 gemma4-e4b-it:q8
hermes-llama-gemma4-26b-9070.service 8013 gemma4-26b-a4b-it:q4km
hermes-llama-lfm25-instruct-9070.service 8016 lfm25-12b-instruct:q4km
EOF
fi

python scripts/model_benchmark_scorecard.py \
  --quality "$QUALITY_DIR"/results_*.json \
  --throughput "$THROUGHPUT_DIR"/*.json \
  --baseline "$BASELINE_MODEL" \
  --min-generation-tps 30 \
  --quality-multiplier-target 1.1 \
  --output benchmarks/llm/model_benchmark_scorecard.md

python scripts/model_capability_cards.py \
  "$QUALITY_DIR"/results_*.json \
  --output benchmarks/llm/model_capability_cards.generated.md

echo "$RUN_ROOT"
