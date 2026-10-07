#!/bin/bash
# mini-MoE LoRA 학습 (mlx_lm.lora)
# 사용: ./scripts/train_lora.sh <expert_id>
set -e

EXPERT="${1:-stocks}"
cd "$(dirname "$0")/.."

# 가상환경 파이썬을 쓰려면 PYTHON=/path/to/python 으로 넘긴다
PYTHON="${PYTHON:-python3}"
BASE_MODEL="mlx-community/gemma-3-4b-it-qat-4bit"
DATA_DIR="data/lora/$EXPERT"
ADAPTER_DIR="data/lora/$EXPERT/adapters"

if [ ! -d "$DATA_DIR" ]; then
    echo "ERROR: $DATA_DIR not found"
    exit 1
fi

mkdir -p "$ADAPTER_DIR"

TRAIN_LINES=$(wc -l < "$DATA_DIR/train.jsonl" | tr -d ' ')
ITERS=$((TRAIN_LINES * 30))
if [ "$ITERS" -lt 200 ]; then ITERS=200; fi
if [ "$ITERS" -gt 2000 ]; then ITERS=2000; fi

LOG_FILE="logs/lora_${EXPERT}_$(date +%Y%m%d_%H%M%S).log"

echo "expert: $EXPERT"
echo "base:   $BASE_MODEL"
echo "train:  $TRAIN_LINES samples, iters $ITERS"
echo "log:    $LOG_FILE"

exec $PYTHON -m mlx_lm lora \
    --model "$BASE_MODEL" \
    --train \
    --data "$DATA_DIR" \
    --adapter-path "$ADAPTER_DIR" \
    --iters "$ITERS" \
    --batch-size 1 \
    --num-layers 8 \
    --learning-rate 0.00001 \
    --max-seq-length 1600 \
    --grad-checkpoint \
    --steps-per-report 20 \
    --steps-per-eval 200 \
    --save-every 200 \
    2>&1 | tee "$LOG_FILE"
