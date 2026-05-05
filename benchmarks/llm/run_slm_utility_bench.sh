#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://10.0.0.10:8016/v1}"
MODEL="${MODEL:?set MODEL to the served llama.cpp alias, e.g. lfm25-12b-instruct:q4km}"
REPETITIONS="${REPETITIONS:-3}"
OUT_DIR="${OUT_DIR:-benchmark_runs/hermes_model_benchmark_slm_utility}"
THROUGHPUT_OUT_DIR="${THROUGHPUT_OUT_DIR:-benchmark_runs/llama_throughput_slm}"
TIMEOUT="${TIMEOUT:-180}"
TEMPERATURE="${TEMPERATURE:-0.0}"
TOP_P="${TOP_P:-}"
TOP_K="${TOP_K:-}"
MIN_P="${MIN_P:-}"
TYPICAL_P="${TYPICAL_P:-}"
REPEAT_PENALTY="${REPEAT_PENALTY:-}"
PRESENCE_PENALTY="${PRESENCE_PENALTY:-}"
FREQUENCY_PENALTY="${FREQUENCY_PENALTY:-}"
SEED="${SEED:-}"
MIROSTAT="${MIROSTAT:-}"
MIROSTAT_TAU="${MIROSTAT_TAU:-}"
MIROSTAT_ETA="${MIROSTAT_ETA:-}"
DECODE_LABEL="${DECODE_LABEL:-}"

TASKS="${TASKS:-utility_route_message_json,utility_extract_actions_json,utility_approval_risk_json,utility_pulse_condense,utility_admission_compaction_json,utility_failover_lane_json,utility_readonly_risk_json,utility_restart_cooldown_json,slm_intent_route_json,slm_queue_wait_or_fallback_json,slm_mutation_guard_json,slm_extract_service_command_json,slm_portuguese_status_summary,slm_spanish_status_summary}"

if [[ -f venv/bin/activate ]]; then
  source venv/bin/activate
elif [[ -f .venv/bin/activate ]]; then
  source .venv/bin/activate
else
  echo "missing Python virtualenv: expected venv/ or .venv/" >&2
  exit 2
fi

benchmark_args=(
  --base-url "$BASE_URL"
  --models "$MODEL"
  --tasks "$TASKS"
  --repetitions "$REPETITIONS"
  --output-dir "$OUT_DIR"
  --wait-for-models
  --temperature "$TEMPERATURE"
)

[[ -n "$TOP_P" ]] && benchmark_args+=(--top-p "$TOP_P")
[[ -n "$TOP_K" ]] && benchmark_args+=(--top-k "$TOP_K")
[[ -n "$MIN_P" ]] && benchmark_args+=(--min-p "$MIN_P")
[[ -n "$TYPICAL_P" ]] && benchmark_args+=(--typical-p "$TYPICAL_P")
[[ -n "$REPEAT_PENALTY" ]] && benchmark_args+=(--repeat-penalty "$REPEAT_PENALTY")
[[ -n "$PRESENCE_PENALTY" ]] && benchmark_args+=(--presence-penalty "$PRESENCE_PENALTY")
[[ -n "$FREQUENCY_PENALTY" ]] && benchmark_args+=(--frequency-penalty "$FREQUENCY_PENALTY")
[[ -n "$SEED" ]] && benchmark_args+=(--seed "$SEED")
[[ -n "$MIROSTAT" ]] && benchmark_args+=(--mirostat "$MIROSTAT")
[[ -n "$MIROSTAT_TAU" ]] && benchmark_args+=(--mirostat-tau "$MIROSTAT_TAU")
[[ -n "$MIROSTAT_ETA" ]] && benchmark_args+=(--mirostat-eta "$MIROSTAT_ETA")
[[ -n "$DECODE_LABEL" ]] && benchmark_args+=(--decode-label "$DECODE_LABEL")

python scripts/hermes_model_benchmark.py "${benchmark_args[@]}"

mkdir -p "$THROUGHPUT_OUT_DIR"
safe_model="${MODEL//[^A-Za-z0-9_.-]/-}"
python scripts/llama_throughput_compare.py \
  --base-url "$BASE_URL" \
  --model "$MODEL" \
  --repetitions "$REPETITIONS" \
  --timeout "$TIMEOUT" \
  --output "$THROUGHPUT_OUT_DIR/${safe_model}.json"
