#!/usr/bin/env bash
# Sweep (model x topology x ctx-size) cells, capturing long-context probe and
# short-prompt throughput numbers per cell. Each cell spawns a temporary
# llama-server, runs the probes, and tears the server down before moving on.
#
# Pre-existing systemd llama services on the same ports are stopped at the
# start and restarted on exit so that the sweep does not collide with the
# normal hermes baseline.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

source venv/bin/activate
export PYTHONUNBUFFERED=1

LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-/workspace/llama.cpp/build-hip/bin/llama-server}"
RUN_ROOT="${RUN_ROOT:-$REPO_ROOT/benchmark_runs/ctx_sweep_$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_ROOT="$(python -c 'import sys,pathlib; print(pathlib.Path(sys.argv[1]).resolve())' "$RUN_ROOT")"
LOG_DIR="$RUN_ROOT/logs"
DATA_DIR="$RUN_ROOT/cells"
SUMMARY_CSV="$RUN_ROOT/ctx_sweep.csv"
mkdir -p "$LOG_DIR" "$DATA_DIR"

QWEN36_MODEL_PATH="/opt/models/hermes-bench/Qwen_Qwen3.6-35B-A3B-IQ4_XS.gguf"
QWEN36_ALIAS="qwen3.6-35b-a3b:iq4xs"
GEMMA4_MODEL_PATH="/opt/models/hermes-bench/google_gemma-4-26B-A4B-it-Q4_K_M.gguf"
GEMMA4_ALIAS="gemma4-26b-a4b-it:q4km"

# Pin GPUs by UUID, not by enumeration index. ROCR enumerates the 9070 XT
# (gfx1201, display GPU) at index 0 on this host, and the 7900 XT (gfx1100)
# at index 1. Using bare integers + HSA_OVERRIDE_GFX_VERSION=11.0.0 has
# already crashed Wayland once by loading gfx1100 code on the 9070 XT.
# Mirror the systemd unit pattern: pin ROCR by `GPU-<unique_id>` and
# HIP_VISIBLE_DEVICES=0 (post-ROCR-filter index).
GPU_7900_UUID="GPU-6bdce6ea1d388c5c"   # AMD Radeon RX 7900 XT, gfx1100
GPU_9070_UUID="GPU-2388c382a826700f"   # AMD Radeon RX 9070 XT, gfx1201, drives the desktop

# Default OFF: the 9070 XT is the active display adapter. Compute that
# saturates it (or, worse, hangs it) freezes Wayland and produces a black
# screen. Set ALLOW_DISPLAY_GPU=1 to opt into the split / cpu-moe topologies.
ALLOW_DISPLAY_GPU="${ALLOW_DISPLAY_GPU:-0}"
FLASH_ATTN="${FLASH_ATTN:-on}"
QWEN_CACHE_TYPE_K="${QWEN_CACHE_TYPE_K:-q8_0}"
QWEN_CACHE_TYPE_V="${QWEN_CACHE_TYPE_V:-q8_0}"
GEMMA_CACHE_TYPE_K="${GEMMA_CACHE_TYPE_K:-q4_0}"
GEMMA_CACHE_TYPE_V="${GEMMA_CACHE_TYPE_V:-q4_0}"
QWEN_BATCH_SIZE="${QWEN_BATCH_SIZE:-1024}"
QWEN_UBATCH_SIZE="${QWEN_UBATCH_SIZE:-512}"
QWEN_GPU_LAYERS="${QWEN_GPU_LAYERS:-999}"
GEMMA_BATCH_SIZE="${GEMMA_BATCH_SIZE:-1024}"
GEMMA_UBATCH_SIZE="${GEMMA_UBATCH_SIZE:-256}"
GEMMA_GPU_LAYERS="${GEMMA_GPU_LAYERS:-999}"
FILL_LEVELS_OVERRIDE="${FILL_LEVELS_OVERRIDE:-}"
QWEN_CTXS="${QWEN_CTXS:-65536 98304 124928 131072}"
GEMMA_CTXS="${GEMMA_CTXS:-65536 98304 124928 131072 262144}"

# Services that own the ports we will reuse for temp servers.
BASELINE_UNITS=(
  hermes-llama-qwen36.service
  hermes-llama-qwen36-128k.service
  hermes-llama-gemma4-26b-9070.service
  hermes-llama-qwen3-coder-30b-q6-2gpu.service
  hermes-llama-glm47-flash-q6-2gpu.service
)

# Timers that revive the baseline services or contend for GPUs. Without
# stopping these the qwen watchdog will restart hermes-llama-qwen36 ~30s
# after we stop it and starve the sweep of VRAM.
BASELINE_TIMERS=(
  hermes-qwen-watchdog.timer
  hermes-llm-gaming-guard.timer
)

# Track which units / timers we stopped so we can restart them on exit.
WAS_ACTIVE=()
WAS_ACTIVE_TIMERS=()
TEMP_PIDS=()

cleanup() {
  local status=$?
  for pid in "${TEMP_PIDS[@]:-}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 2
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
  for timer in "${WAS_ACTIVE_TIMERS[@]:-}"; do
    [[ -z "$timer" ]] && continue
    systemctl --user start "$timer" >/dev/null 2>&1 || true
  done
  for unit in "${WAS_ACTIVE[@]:-}"; do
    [[ -z "$unit" ]] && continue
    systemctl --user start "$unit" >/dev/null 2>&1 || true
  done
  echo "[ctx_sweep] cleanup complete; results in $RUN_ROOT" >&2
  return "$status"
}
trap cleanup EXIT

stop_baseline_units() {
  for timer in "${BASELINE_TIMERS[@]}"; do
    if systemctl --user is-active --quiet "$timer"; then
      WAS_ACTIVE_TIMERS+=("$timer")
      echo "[ctx_sweep] stopping $timer" >&2
      systemctl --user stop "$timer" || true
    fi
  done
  for unit in "${BASELINE_UNITS[@]}"; do
    if systemctl --user is-active --quiet "$unit"; then
      WAS_ACTIVE+=("$unit")
      echo "[ctx_sweep] stopping $unit" >&2
      systemctl --user stop "$unit" || true
    fi
  done
}

wait_for_server() {
  local base_url="$1"
  local model="$2"
  local timeout="${3:-300}"
  python - "$base_url" "$model" "$timeout" <<'PY'
import json, sys, time, urllib.request

base_url, model, timeout = sys.argv[1].rstrip("/"), sys.argv[2], int(sys.argv[3])
deadline = time.time() + timeout
last = None
payload = json.dumps({
    "model": model,
    "messages": [{"role": "user", "content": "ping"}],
    "max_tokens": 1,
    "temperature": 0,
}).encode()
while time.time() < deadline:
    try:
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                resp.read()
                print("warm")
                raise SystemExit(0)
    except Exception as exc:  # noqa: BLE001
        last = str(exc)[:200]
    time.sleep(5)
sys.stderr.write(f"server not ready at {base_url}: {last}\n")
raise SystemExit(1)
PY
}

# Quick liveness check used between probe iterations. Returns 0 if the
# server answers a tiny chat/completions request within the timeout.
server_alive() {
  local base_url="$1"
  local model="$2"
  python - "$base_url" "$model" <<'PY' >/dev/null 2>&1
import json, sys, urllib.request
base_url, model = sys.argv[1].rstrip("/"), sys.argv[2]
payload = json.dumps({
    "model": model,
    "messages": [{"role": "user", "content": "ping"}],
    "max_tokens": 1,
    "temperature": 0,
}).encode()
req = urllib.request.Request(
    f"{base_url}/chat/completions",
    data=payload,
    headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        sys.exit(0 if resp.status == 200 else 1)
except Exception:
    sys.exit(1)
PY
}

# fill_levels_for ctx_tokens -> echo comma list of char counts to probe at.
fill_levels_for() {
  local ctx="$1"
  if [[ -n "$FILL_LEVELS_OVERRIDE" ]]; then
    echo "$FILL_LEVELS_OVERRIDE"
    return 0
  fi
  case "$ctx" in
    65536)  echo "32k,128k,240k" ;;
    98304)  echo "32k,128k,240k,360k" ;;
    124928) echo "32k,128k,240k,460k" ;;
    131072) echo "32k,128k,240k,480k" ;;
    262144) echo "32k,256k,480k,960k" ;;
    *) echo "32k,128k" ;;
  esac
}

# Globals owned by run_cell + its server-restart helpers.
_RUN_CELL_PID=""

# Convert a fill spec like "240k" into an integer character count, mirroring
# the parser in llama_longctx_probe.py.
fill_chars() {
  local spec="${1,,}"
  if [[ "$spec" == *k ]]; then
    spec="${spec%k}"
    python -c "import sys;print(int(float(sys.argv[1]) * 1024))" "$spec"
  else
    printf '%s\n' "$spec"
  fi
}

start_cell_server() {
  local server_log="$1"
  local gpu_env="$2"
  local port="$3"
  local model_path="$4"
  local alias="$5"
  local ctx="$6"
  local probe_log="$7"
  local base_url="$8"
  shift 8
  local extra_args=("$@")

  echo "[ctx_sweep] starting llama-server: env $gpu_env ctx=$ctx port=$port" >&2
  # shellcheck disable=SC2086
  env $gpu_env nohup "$LLAMA_SERVER_BIN" \
    --host 10.0.0.10 \
    --port "$port" \
    --model "$model_path" \
    --alias "$alias" \
    --ctx-size "$ctx" \
    --parallel 1 \
    --threads 16 \
    --threads-batch 16 \
    --flash-attn "$FLASH_ATTN" \
    --jinja \
    --reasoning off \
    "${extra_args[@]}" \
    >>"$server_log" 2>&1 &
  _RUN_CELL_PID=$!
  TEMP_PIDS+=("$_RUN_CELL_PID")

  local wait_timeout=600
  if (( ctx >= 131072 )); then wait_timeout=900; fi
  if (( ctx >= 262144 )); then wait_timeout=1500; fi

  wait_for_server "$base_url" "$alias" "$wait_timeout" >>"$probe_log" 2>&1
}

stop_cell_server() {
  local pid="$_RUN_CELL_PID"
  _RUN_CELL_PID=""
  [[ -z "$pid" ]] && return 0
  kill "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8; do
    if ! kill -0 "$pid" 2>/dev/null; then break; fi
    sleep 1
  done
  kill -9 "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}

# run_cell <topology> <ctx_tokens> <port> <gpu_env> <model_path> <alias> <extra-args...>
run_cell() {
  local topology="$1"; shift
  local ctx="$1"; shift
  local port="$1"; shift
  local gpu_env="$1"; shift
  local model_path="$1"; shift
  local alias="$1"; shift
  local extra_args=("$@")

  local cell_id="${alias//[:\/]/-}-${topology}-ctx${ctx}"
  local cell_dir="$DATA_DIR/$cell_id"
  mkdir -p "$cell_dir"
  local server_log="$LOG_DIR/${cell_id}.server.log"
  local probe_log="$LOG_DIR/${cell_id}.probe.log"
  local base_url="http://10.0.0.10:${port}/v1"

  echo "[ctx_sweep] === $cell_id ===" >&2

  if ! start_cell_server \
      "$server_log" "$gpu_env" "$port" "$model_path" "$alias" "$ctx" \
      "$probe_log" "$base_url" "${extra_args[@]}"; then
    echo "[ctx_sweep] FAIL: server did not become ready ($cell_id)" >&2
    stop_cell_server
    printf '%s,%s,%s,start_failed,,,,,,,,\n' \
      "$alias" "$topology" "$ctx" >> "$SUMMARY_CSV"
    return 0
  fi

  local fill_levels
  fill_levels="$(fill_levels_for "$ctx")"
  IFS=',' read -ra FILL_ARR <<< "$fill_levels"

  local probe_timeout=900
  if (( ctx >= 131072 )); then probe_timeout=1800; fi
  if (( ctx >= 262144 )); then probe_timeout=3600; fi

  # Drive each (mode, fill) probe in its own python invocation so a server
  # crash on one row does not poison the rest of the cell. After a crash
  # we restart the server. If a fill of size N crashes, skip every fill
  # >= N for the remainder of the cell — they will almost certainly crash
  # too and each restart costs 30-90s.
  local pair_jsons=()
  local crash_floor=999999999
  local mode fill fill_n pair_id pair_json
  for mode in needle synthesis; do
    for fill in "${FILL_ARR[@]}"; do
      fill_n="$(fill_chars "$fill")"
      if (( fill_n >= crash_floor )); then
        echo "[ctx_sweep] skipping $mode@$fill (>=${crash_floor} char crash floor)" >&2
        continue
      fi

      if ! server_alive "$base_url" "$alias"; then
        echo "[ctx_sweep] server unhealthy before $mode@$fill; restarting" >&2
        stop_cell_server
        if ! start_cell_server \
            "$server_log" "$gpu_env" "$port" "$model_path" "$alias" "$ctx" \
            "$probe_log" "$base_url" "${extra_args[@]}"; then
          echo "[ctx_sweep] restart failed; abandoning remaining probes for $cell_id" >&2
          break 2
        fi
      fi

      pair_id="${mode}_${fill}"
      pair_json="$cell_dir/longctx_${pair_id}.json"
      local probe_failed=0
      if ! python scripts/llama_longctx_probe.py \
          --base-url "$base_url" \
          --model "$alias" \
          --fill-levels "$fill" \
          --modes "$mode" \
          --max-tokens 192 \
          --timeout "$probe_timeout" \
          --output "$pair_json" \
          >>"$probe_log" 2>&1; then
        echo "[ctx_sweep] probe error $mode@$fill ($cell_id)" >&2
        probe_failed=1
      fi

      if [[ -f "$pair_json" ]]; then
        pair_jsons+=("$pair_json")
      fi

      # If the probe failed hard, or if the server died during this probe
      # (process gone or unresponsive), treat this fill size as the crash
      # floor for the rest of the cell. This check intentionally runs even
      # when the probe failed before writing JSON.
      if (( probe_failed != 0 )) || ! server_alive "$base_url" "$alias"; then
        if (( fill_n < crash_floor )); then
          crash_floor="$fill_n"
          echo "[ctx_sweep] crash floor for $cell_id set to ${crash_floor} chars" >&2
        fi
      fi
    done
  done

  # Aggregate per-pair JSONs into one cell-level longctx.json.
  local longctx_json="$cell_dir/longctx.json"
  python - "$longctx_json" "$alias" "${pair_jsons[@]:-}" <<'PY'
import json, sys
from pathlib import Path
out_path, alias, *inputs = sys.argv[1:]
rows = []
for path in inputs:
    if not path:
        continue
    try:
        data = json.loads(Path(path).read_text())
    except Exception:
        continue
    rows.extend(data.get("rows") or [])
Path(out_path).write_text(
    json.dumps({"model": alias, "rows": rows}, indent=2) + "\n"
)
PY

  # Throughput probe — restart once if the server died on the last probe.
  local throughput_json="$cell_dir/throughput.json"
  if ! server_alive "$base_url" "$alias"; then
    echo "[ctx_sweep] restarting server for throughput probe" >&2
    stop_cell_server
    start_cell_server \
      "$server_log" "$gpu_env" "$port" "$model_path" "$alias" "$ctx" \
      "$probe_log" "$base_url" "${extra_args[@]}" \
      || echo "[ctx_sweep] throughput restart failed; skipping throughput" >&2
  fi
  if server_alive "$base_url" "$alias"; then
    python scripts/llama_throughput_compare.py \
      --base-url "$base_url" \
      --model "$alias" \
      --repetitions 3 \
      --max-tokens 160 \
      --timeout 300 \
      --output "$throughput_json" \
      >>"$probe_log" 2>&1 \
      || echo "[ctx_sweep] throughput probe failed for $cell_id" >&2
  fi

  python - "$alias" "$topology" "$ctx" "$longctx_json" "$throughput_json" <<'PY' >> "$SUMMARY_CSV"
import json, sys
from pathlib import Path

alias, topology, ctx, longctx_path, throughput_path = sys.argv[1:6]
longctx = {}
throughput = {}
try:
    longctx = json.loads(Path(longctx_path).read_text())
except Exception:
    pass
try:
    throughput = json.loads(Path(throughput_path).read_text())
except Exception:
    pass

short_prompt_tps = throughput.get("median_completion_tokens_per_second")
short_prompt_eval = throughput.get("median_prompt_tokens_per_second")
rows = longctx.get("rows") or []
for row in rows:
    if row.get("error"):
        outcome = f"error:{row['error'][:40]}"
    else:
        outcome = "correct" if row.get("correct") else "wrong"
    print(",".join(str(x) for x in [
        alias,
        topology,
        ctx,
        row.get("mode") or "",
        row.get("target_chars") or "",
        row.get("prompt_tokens") or "",
        row.get("completion_tokens") or "",
        row.get("prompt_tokens_per_second") or "",
        row.get("completion_tokens_per_second") or "",
        outcome,
        short_prompt_eval or "",
        short_prompt_tps or "",
    ]))
PY

  echo "[ctx_sweep] killing $cell_id" >&2
  stop_cell_server
}

# Build the matrix.
# qwen3.6 single-GPU on 7900: just ctx sweep at 64/96/122/128k.
# gemma4 26B-A4B in three topologies x five ctx levels.

ONLY="${ONLY:-}"   # optional substring filter for cell_id (e.g. ONLY=qwen36 or ONLY=ctx65536)
should_run() {
  local cell_id="$1"
  if [[ -z "$ONLY" ]]; then return 0; fi
  [[ "$cell_id" == *"$ONLY"* ]]
}

stop_baseline_units

# Header
printf 'model,topology,ctx,mode,target_chars,prompt_tokens,completion_tokens,prompt_eval_tps,completion_tps,outcome,short_prompt_eval_tps,short_prompt_completion_tps\n' \
  > "$SUMMARY_CSV"

# ---- qwen3.6 35B-A3B IQ4_XS, single 7900 XT ----
QWEN_GPU_ENV="HIP_VISIBLE_DEVICES=0 ROCR_VISIBLE_DEVICES=$GPU_7900_UUID HSA_OVERRIDE_GFX_VERSION=11.0.0"
QWEN_PORT=8101
QWEN_FLAGS=(--batch-size "$QWEN_BATCH_SIZE" --ubatch-size "$QWEN_UBATCH_SIZE" --gpu-layers "$QWEN_GPU_LAYERS"
            --cache-type-k "$QWEN_CACHE_TYPE_K" --cache-type-v "$QWEN_CACHE_TYPE_V" --cache-ram 0 --cache-reuse 256)

for ctx in $QWEN_CTXS; do
  cell_id="${QWEN36_ALIAS//[:\/]/-}-qwen36_7900-ctx${ctx}"
  if should_run "$cell_id"; then
    run_cell qwen36_7900 "$ctx" "$QWEN_PORT" "$QWEN_GPU_ENV" \
      "$QWEN36_MODEL_PATH" "$QWEN36_ALIAS" "${QWEN_FLAGS[@]}"
  fi
done

# ---- gemma4 26B-A4B Q4_K_M ----

# Single GPU = 7900 XT (20GB fits weights with KV headroom up to ~96k).
GEMMA_SINGLE_ENV="HIP_VISIBLE_DEVICES=0 ROCR_VISIBLE_DEVICES=$GPU_7900_UUID HSA_OVERRIDE_GFX_VERSION=11.0.0"
GEMMA_SINGLE_PORT=8102
GEMMA_SINGLE_FLAGS=(--batch-size "$GEMMA_BATCH_SIZE" --ubatch-size "$GEMMA_UBATCH_SIZE" --gpu-layers "$GEMMA_GPU_LAYERS"
                    --cache-type-k "$GEMMA_CACHE_TYPE_K" --cache-type-v "$GEMMA_CACHE_TYPE_V" --cache-ram 0)

for ctx in $GEMMA_CTXS; do
  cell_id="${GEMMA4_ALIAS//[:\/]/-}-gemma4_7900-ctx${ctx}"
  if should_run "$cell_id"; then
    run_cell gemma4_7900 "$ctx" "$GEMMA_SINGLE_PORT" "$GEMMA_SINGLE_ENV" \
      "$GEMMA4_MODEL_PATH" "$GEMMA4_ALIAS" "${GEMMA_SINGLE_FLAGS[@]}"
  fi
done

# Split GPU = 7900 + 9070. Order ROCR with the 7900 XT first so HIP index 0
# resolves to gfx1100 (matches the existing 2gpu service convention).
GEMMA_SPLIT_ENV="HIP_VISIBLE_DEVICES=0,1 ROCR_VISIBLE_DEVICES=$GPU_7900_UUID,$GPU_9070_UUID HSA_OVERRIDE_GFX_VERSION=11.0.0"
GEMMA_SPLIT_PORT=8103
GEMMA_SPLIT_FLAGS=(--batch-size 1024 --ubatch-size 128 --gpu-layers 999
                   --device ROCm0,ROCm1 --split-mode layer --tensor-split 10,8 --main-gpu 0
                   --cache-type-k q4_0 --cache-type-v q4_0 --cache-ram 0)

# CPU-MoE: experts in RAM, attention/dense on 9070 (faster RDNA4 compute).
# Use --cache-ram 1 so KV cache can spill to RAM at very long ctx.
GEMMA_CPUMOE_ENV="HIP_VISIBLE_DEVICES=0 ROCR_VISIBLE_DEVICES=$GPU_9070_UUID HSA_OVERRIDE_GFX_VERSION=12.0.1"
GEMMA_CPUMOE_PORT=8104
GEMMA_CPUMOE_FLAGS=(--batch-size 512 --ubatch-size 128 --gpu-layers 999 --cpu-moe
                    --cache-type-k q4_0 --cache-type-v q4_0 --cache-ram -1)

if [[ "$ALLOW_DISPLAY_GPU" == "1" ]]; then
  for ctx in 65536 98304 124928 131072 262144; do
    cell_id="${GEMMA4_ALIAS//[:\/]/-}-gemma4_split-ctx${ctx}"
    if should_run "$cell_id"; then
      run_cell gemma4_split "$ctx" "$GEMMA_SPLIT_PORT" "$GEMMA_SPLIT_ENV" \
        "$GEMMA4_MODEL_PATH" "$GEMMA4_ALIAS" "${GEMMA_SPLIT_FLAGS[@]}"
    fi
  done

  for ctx in 65536 98304 124928 131072 262144; do
    cell_id="${GEMMA4_ALIAS//[:\/]/-}-gemma4_cpumoe-ctx${ctx}"
    if should_run "$cell_id"; then
      run_cell gemma4_cpumoe "$ctx" "$GEMMA_CPUMOE_PORT" "$GEMMA_CPUMOE_ENV" \
        "$GEMMA4_MODEL_PATH" "$GEMMA4_ALIAS" "${GEMMA_CPUMOE_FLAGS[@]}"
    fi
  done
else
  echo "[ctx_sweep] skipping gemma4_split + gemma4_cpumoe cells (9070 XT is the display GPU). Set ALLOW_DISPLAY_GPU=1 from a TTY/headless session to enable." >&2
fi

echo "[ctx_sweep] sweep complete; CSV at $SUMMARY_CSV" >&2
echo "$RUN_ROOT"
