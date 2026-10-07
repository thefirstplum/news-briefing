#!/bin/bash
# Metal watchdog에 걸리지 않게 작은 청크로 나눠 학습하고, 죽으면 저장된 어댑터에서 재개
# 사용: ./scripts/train_lora_resilient.sh <expert_id> [total_iters] [chunk_iters]
set -e

EXPERT="${1:-stocks}"
TOTAL_ITERS="${2:-1680}"
CHUNK="${3:-100}"

cd "$(dirname "$0")/.."

# 가상환경 파이썬을 쓰려면 PYTHON=/path/to/python 으로 넘긴다
PYTHON="${PYTHON:-python3}"
BASE_MODEL="mlx-community/gemma-3-4b-it-qat-4bit"
DATA_DIR="data/lora/$EXPERT"
ADAPTER_DIR="data/lora/$EXPERT/adapters"
ADAPTER_FILE="$ADAPTER_DIR/adapters.safetensors"

mkdir -p "$ADAPTER_DIR"
LOG_FILE="logs/lora_resilient_${EXPERT}_$(date +%Y%m%d_%H%M%S).log"

echo "[resilient] expert=$EXPERT total=$TOTAL_ITERS chunk=$CHUNK base=$BASE_MODEL" | tee "$LOG_FILE"

done_iters=0
attempt=0
while [ "$done_iters" -lt "$TOTAL_ITERS" ]; do
    attempt=$((attempt + 1))
    remaining=$((TOTAL_ITERS - done_iters))
    iters=$CHUNK
    if [ "$remaining" -lt "$iters" ]; then iters="$remaining"; fi

    resume_args=""
    if [ -f "$ADAPTER_FILE" ]; then
        resume_args="--resume-adapter-file $ADAPTER_FILE"
    fi

    echo "" | tee -a "$LOG_FILE"
    echo "===== chunk $attempt | iters $iters | done $done_iters / $TOTAL_ITERS =====" | tee -a "$LOG_FILE"
    date | tee -a "$LOG_FILE"

    set +e
    $PYTHON -m mlx_lm lora \
        --model "$BASE_MODEL" \
        --train \
        --data "$DATA_DIR" \
        --adapter-path "$ADAPTER_DIR" \
        $resume_args \
        --iters "$iters" \
        --batch-size 1 \
        --num-layers 8 \
        --max-seq-length 1600 \
        --grad-checkpoint \
        --learning-rate 0.00001 \
        --steps-per-report 10 \
        --steps-per-eval "$iters" \
        --save-every 25 \
        2>&1 | tee -a "$LOG_FILE"
    rc=$?
    set -e

    if [ "$rc" -eq 0 ]; then
        done_iters=$((done_iters + iters))
        echo "[chunk $attempt] OK, total done=$done_iters" | tee -a "$LOG_FILE"
    else
        # 죽었으면 실제로 저장된 iter는 부분일 수 있음.
        # 보수적으로 chunk의 1/4만 진행했다고 가정 (save-every 25 기준).
        partial=$((iters / 4))
        done_iters=$((done_iters + partial))
        echo "[chunk $attempt] CRASHED rc=$rc, partial estimate +$partial, total~$done_iters" | tee -a "$LOG_FILE"
        # GPU 식히는 시간
        sleep 10
    fi
done

echo "" | tee -a "$LOG_FILE"
echo "[resilient] 완료 done=$done_iters attempts=$attempt" | tee -a "$LOG_FILE"
date | tee -a "$LOG_FILE"
