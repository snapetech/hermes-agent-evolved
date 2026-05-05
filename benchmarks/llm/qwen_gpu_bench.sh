#!/usr/bin/env bash
set -u

LLAMA_BENCH="${LLAMA_BENCH:-/workspace/llama.cpp/build-hip/bin/llama-bench}"
MODEL_DIR="${MODEL_DIR:-/opt/models/hermes-bench}"
OUT_DIR="${OUT_DIR:-/workspace/hermes-agent/benchmarks/llm/results}"

PROMPT_TOKENS="${PROMPT_TOKENS:-512}"
GEN_TOKENS="${GEN_TOKENS:-128}"
REPETITIONS="${REPETITIONS:-3}"
GPU_LAYERS="${GPU_LAYERS:-999}"
FIT_MARGIN_MIB="${FIT_MARGIN_MIB:-768}"
DISPLAY_GPU_FIT_MARGIN_MIB="${DISPLAY_GPU_FIT_MARGIN_MIB:-4096}"
FIT_CTX="${FIT_CTX:-4096}"

mkdir -p "$OUT_DIR"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
summary="$OUT_DIR/qwen_gpu_bench_${timestamp}.summary.tsv"

cat > "$summary" <<'HEADER'
timestamp	gpu_id	gpu_name	model	status	csv	log
HEADER

models=(
  "qwen3.5-9b-q4km|Qwen_Qwen3.5-9B-Q4_K_M.gguf"
  "qwen3.6-35b-a3b-iq3m|Qwen_Qwen3.6-35B-A3B-IQ3_M.gguf"
  "qwen3.6-35b-a3b-iq4xs|Qwen_Qwen3.6-35B-A3B-IQ4_XS.gguf"
  "qwen3.5-27b-q4km|Qwen_Qwen3.5-27B-Q4_K_M.gguf"
  "qwen3.5-35b-a3b-iq3m|Qwen3.5-35B-A3B-IQ3_M.gguf"
  "qwen3-coder-next-tq1|Qwen3-Coder-Next-UD-TQ1_0.gguf"
)

gpus=(
  "ROCm1|7900xt"
)

if [[ "${INCLUDE_DISPLAY_GPU_9070:-0}" == "1" ]]; then
  if [[ "${ALLOW_DISPLAY_GPU_9070:-0}" != "1" ]]; then
    echo "refusing to benchmark the display GPU (ROCm0 / RX 9070 XT) without ALLOW_DISPLAY_GPU_9070=1" >&2
    exit 2
  fi
  gpus=(
    "ROCm1|7900xt"
    "ROCm0|9070xt"
  )
fi

if [[ ! -x "$LLAMA_BENCH" ]]; then
  echo "llama-bench not executable: $LLAMA_BENCH" >&2
  exit 2
fi

for gpu in "${gpus[@]}"; do
  IFS='|' read -r gpu_id gpu_name <<< "$gpu"
  fit_margin_mib="$FIT_MARGIN_MIB"
  if [[ "$gpu_id" == "ROCm0" ]]; then
    fit_margin_mib="$DISPLAY_GPU_FIT_MARGIN_MIB"
  fi
  for model in "${models[@]}"; do
    IFS='|' read -r model_name model_file <<< "$model"
    model_path="$MODEL_DIR/$model_file"
    run_id="${timestamp}_${gpu_name}_${model_name}"
    csv_path="$OUT_DIR/${run_id}.csv"
    log_path="$OUT_DIR/${run_id}.log"

    if [[ ! -f "$model_path" ]]; then
      printf '%s\t%s\t%s\t%s\tmissing\t\t%s\n' \
        "$timestamp" "$gpu_id" "$gpu_name" "$model_name" "$log_path" >> "$summary"
      echo "missing model: $model_path" > "$log_path"
      continue
    fi

    echo "Benchmarking $model_name on $gpu_id ($gpu_name), keeping ${fit_margin_mib} MiB VRAM free"
    "$LLAMA_BENCH" \
      -m "$model_path" \
      -dev "$gpu_id" \
      -ngl "$GPU_LAYERS" \
      -fa 1 \
      -p "$PROMPT_TOKENS" \
      -n "$GEN_TOKENS" \
      -r "$REPETITIONS" \
      --fit-target "$fit_margin_mib" \
      --fit-ctx "$FIT_CTX" \
      -o csv \
      > "$csv_path" \
      2> "$log_path"
    rc=$?

    if [[ "$rc" -eq 0 ]]; then
      status="ok"
    else
      status="failed:$rc"
    fi

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$timestamp" "$gpu_id" "$gpu_name" "$model_name" "$status" "$csv_path" "$log_path" >> "$summary"
  done
done

echo "$summary"
