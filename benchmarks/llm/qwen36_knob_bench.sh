#!/usr/bin/env bash
set -euo pipefail

LLAMA_BENCH="${LLAMA_BENCH:-/workspace/llama.cpp/build-hip/bin/llama-bench}"
MODEL_PATH="${MODEL_PATH:-/opt/models/hermes-bench/Qwen_Qwen3.6-35B-A3B-IQ4_XS.gguf}"
OUT_DIR="${OUT_DIR:-/workspace/hermes-agent/benchmarks/llm/results}"
GPU_DEVICE="${GPU_DEVICE:-ROCm1}"
GPU_LABEL="${GPU_LABEL:-7900xt}"
REPETITIONS="${REPETITIONS:-2}"
PROMPT_TOKENS_LIST="${PROMPT_TOKENS_LIST:-512 8192}"
GEN_TOKENS="${GEN_TOKENS:-128}"
BATCH_SIZE_LIST="${BATCH_SIZE_LIST:-1024}"
UBATCH_SIZE_LIST="${UBATCH_SIZE_LIST:-256 512}"
THREADS="${THREADS:-16}"
GPU_LAYERS="${GPU_LAYERS:-999}"
FLASH_ATTN_LIST="${FLASH_ATTN_LIST:-1 0}"
CACHE_TYPES="${CACHE_TYPES:-q8_0:q8_0 q4_0:q4_0}"
N_CPU_MOE_LIST="${N_CPU_MOE_LIST:-0}"
FIT_MARGIN_MIB="${FIT_MARGIN_MIB:-768}"
DISPLAY_GPU_FIT_MARGIN_MIB="${DISPLAY_GPU_FIT_MARGIN_MIB:-4096}"
FIT_CTX="${FIT_CTX:-8192}"

mkdir -p "$OUT_DIR"

if [[ ! -x "$LLAMA_BENCH" ]]; then
  echo "llama-bench not executable: $LLAMA_BENCH" >&2
  exit 2
fi

if [[ ! -f "$MODEL_PATH" ]]; then
  echo "model missing: $MODEL_PATH" >&2
  exit 2
fi

if [[ "$GPU_DEVICE" == "ROCm0" && "${ALLOW_DISPLAY_GPU_9070:-0}" != "1" ]]; then
  echo "refusing to benchmark the display GPU (ROCm0 / RX 9070 XT) without ALLOW_DISPLAY_GPU_9070=1" >&2
  exit 2
fi

fit_margin_mib="$FIT_MARGIN_MIB"
if [[ "$GPU_DEVICE" == "ROCm0" ]]; then
  fit_margin_mib="$DISPLAY_GPU_FIT_MARGIN_MIB"
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
summary="$OUT_DIR/qwen36_knob_bench_${timestamp}.summary.tsv"

cat > "$summary" <<'HEADER'
timestamp	gpu	prompt_tokens	gen_tokens	flash_attn	cache_k	cache_v	batch	ubatch	n_cpu_moe	status	csv	log
HEADER

for prompt_tokens in $PROMPT_TOKENS_LIST; do
  for flash_attn in $FLASH_ATTN_LIST; do
    for cache_pair in $CACHE_TYPES; do
      IFS=':' read -r cache_k cache_v <<< "$cache_pair"
      for batch_size in $BATCH_SIZE_LIST; do
        for ubatch_size in $UBATCH_SIZE_LIST; do
          for n_cpu_moe in $N_CPU_MOE_LIST; do
            run_id="${timestamp}_${GPU_LABEL}_p${prompt_tokens}_n${GEN_TOKENS}_fa-${flash_attn}_ctk-${cache_k}_ctv-${cache_v}_b-${batch_size}_ub-${ubatch_size}_ncmoe-${n_cpu_moe}"
            csv_path="$OUT_DIR/${run_id}.csv"
            log_path="$OUT_DIR/${run_id}.log"

            echo "Benchmarking p=$prompt_tokens n=$GEN_TOKENS fa=$flash_attn ctk=$cache_k ctv=$cache_v b=$batch_size ub=$ubatch_size ncmoe=$n_cpu_moe on $GPU_DEVICE, keeping ${fit_margin_mib} MiB VRAM free"
            if "$LLAMA_BENCH" \
              -m "$MODEL_PATH" \
              -dev "$GPU_DEVICE" \
              -ngl "$GPU_LAYERS" \
              -fa "$flash_attn" \
              -p "$prompt_tokens" \
              -n "$GEN_TOKENS" \
              -r "$REPETITIONS" \
              -b "$batch_size" \
              -ub "$ubatch_size" \
              -t "$THREADS" \
              -ctk "$cache_k" \
              -ctv "$cache_v" \
              -ncmoe "$n_cpu_moe" \
              --fit-target "$fit_margin_mib" \
              --fit-ctx "$FIT_CTX" \
              -o csv \
              > "$csv_path" \
              2> "$log_path"; then
              status="ok"
            else
              status="failed:$?"
            fi

            printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
              "$timestamp" "$GPU_DEVICE" "$prompt_tokens" "$GEN_TOKENS" \
              "$flash_attn" "$cache_k" "$cache_v" "$batch_size" "$ubatch_size" \
              "$n_cpu_moe" "$status" "$csv_path" "$log_path" \
              >> "$summary"
          done
        done
      done
    done
  done
done

echo "$summary"
