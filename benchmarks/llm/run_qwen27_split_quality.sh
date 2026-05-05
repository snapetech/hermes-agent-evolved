#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/workspace/hermes-agent}"
LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-/workspace/llama.cpp/build-hip/bin/llama-server}"
HOST="${HOST:-10.0.0.10}"
BASELINE_UNIT="${BASELINE_UNIT:-hermes-llama-qwen36.service}"
RUN_ROOT="${RUN_ROOT:-$REPO_ROOT/benchmark_runs/qwen27_split_quality_$(date -u +%Y%m%dT%H%M%SZ)}"
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${REPO_ROOT}/venv/bin/python"
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

GPU_7900_UUID="${GPU_7900_UUID:-GPU-6bdce6ea1d388c5c}"
GPU_9070_UUID="${GPU_9070_UUID:-GPU-2388c382a826700f}"

REPETITIONS="${REPETITIONS:-3}"
TEMPERATURE="${TEMPERATURE:-0.0}"
TASK_TIMEOUT="${TASK_TIMEOUT:-240}"
TASK_DELAY="${TASK_DELAY:-5}"

mkdir -p "$RUN_ROOT/quality" "$RUN_ROOT/logs"

BASELINE_WAS_ACTIVE=0
WATCHDOG_WAS_ACTIVE=0
SERVER_PID=""

cleanup() {
  local rc=$?
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  if [[ "$BASELINE_WAS_ACTIVE" -eq 1 ]]; then
    systemctl --user start "$BASELINE_UNIT" >/dev/null 2>&1 || true
  fi
  if [[ "$WATCHDOG_WAS_ACTIVE" -eq 1 ]]; then
    systemctl --user start hermes-qwen-watchdog.timer >/dev/null 2>&1 || true
  fi
  echo "$RUN_ROOT"
  exit "$rc"
}
trap cleanup EXIT INT TERM

wait_ready() {
  local url="$1"
  local alias="$2"
  python - "$url" "$alias" <<'PY'
import json
import sys
import time
import urllib.request

base, alias = sys.argv[1].rstrip("/"), sys.argv[2]
deadline = time.time() + 900
last = None
while time.time() < deadline:
    try:
        with urllib.request.urlopen(f"{base}/models", timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        ids = [m.get("id") for m in body.get("data", [])]
        if alias in ids:
            print("ready")
            raise SystemExit(0)
        last = f"models={ids}"
    except Exception as exc:
        last = str(exc)
    time.sleep(5)
raise SystemExit(f"not ready: {last}")
PY
}

run_one() {
  local alias="$1"
  local port="$2"
  local model_path="$3"
  local log="$RUN_ROOT/logs/${alias//[:\/]/-}"

  echo "RUN $alias port=$port temperature=$TEMPERATURE repetitions=$REPETITIONS" | tee -a "$RUN_ROOT/run.log"

  env \
    "ROCR_VISIBLE_DEVICES=$GPU_7900_UUID,$GPU_9070_UUID" \
    HIP_VISIBLE_DEVICES=0,1 \
    /usr/bin/ionice -c 3 /usr/bin/nice -n 19 \
    "$LLAMA_SERVER_BIN" \
      --host "$HOST" \
      --port "$port" \
      --model "$model_path" \
      --alias "$alias" \
      --ctx-size 8192 \
      --parallel 1 \
      --batch-size 1024 \
      --ubatch-size 128 \
      --threads 16 \
      --threads-batch 16 \
      --gpu-layers 999 \
      --flash-attn on \
      --cache-type-k q4_0 \
      --cache-type-v q4_0 \
      --cache-ram 0 \
      --no-cache-prompt \
      --ctx-checkpoints 0 \
      --checkpoint-every-n-tokens -1 \
      --slot-prompt-similarity 0.0 \
      --no-context-shift \
      --device ROCm0,ROCm1 \
      --split-mode layer \
      --tensor-split 12,8 \
      --main-gpu 0 \
      --fit on \
      --fit-target 768,4096 \
      --fit-ctx 8192 \
      --reasoning off \
      --jinja \
      >"$log.server" 2>&1 &
  SERVER_PID=$!

  wait_ready "http://$HOST:$port/v1" "$alias" >>"$log.ready" 2>&1

  (
    cd "$REPO_ROOT"
    "$PYTHON_BIN" scripts/hermes_model_benchmark.py \
      --base-url "http://$HOST:$port/v1" \
      --models "$alias" \
      --output-dir "$RUN_ROOT/quality" \
      --repetitions "$REPETITIONS" \
      --task-timeout "$TASK_TIMEOUT" \
      --task-delay "$TASK_DELAY" \
      --temperature "$TEMPERATURE"
  ) >>"$log.quality" 2>&1

  local rc=$?
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
  SERVER_PID=""
  echo "$alias rc=$rc" | tee -a "$RUN_ROOT/run.log"
  return "$rc"
}

if systemctl --user is-active --quiet hermes-qwen-watchdog.timer; then
  WATCHDOG_WAS_ACTIVE=1
  systemctl --user stop hermes-qwen-watchdog.timer hermes-qwen-watchdog.service
fi

if systemctl --user is-active --quiet "$BASELINE_UNIT"; then
  BASELINE_WAS_ACTIVE=1
  systemctl --user stop "$BASELINE_UNIT"
  sleep 5
fi

should_run() {
  local alias="$1"
  [[ -z "${RUN_ONLY:-}" || ",$RUN_ONLY," == *",$alias,"* ]]
}

if should_run qwen3.6-27b:q4km-split; then
  run_one qwen3.6-27b:q4km-split 8040 /mnt/disks/gamespool0/hermes-models/bench/qwen3.6-27b-q4_k_m.gguf
fi
if should_run qwen3.6-27b:q5ks-split; then
  run_one qwen3.6-27b:q5ks-split 8041 /mnt/disks/gamespool0/hermes-models/bench/Qwen_Qwen3.6-27B-Q5_K_S.gguf
fi
if should_run qwen3.6-27b:q6k-split; then
  run_one qwen3.6-27b:q6k-split 8042 /mnt/disks/gamespool0/hermes-models/bench/Qwen3.6-27B-Q6_K.gguf
fi
if should_run qwen3.6-27b:q8-split; then
  run_one qwen3.6-27b:q8-split 8043 /mnt/disks/gamespool0/hermes-models/bench/Qwen3.6-27B-Q8_0.gguf
fi
