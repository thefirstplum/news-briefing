#!/bin/bash
# economy, politics, world 순서로 LoRA 학습
# resilient 청크 학습 사용 (각 2000 iters, chunk 100)
set -u

cd "$(dirname "$0")/.."
mkdir -p logs
BATCH_LOG="logs/lora_batch_3experts_$(date +%Y%m%d_%H%M%S).log"

echo "3 전문가 순차 LoRA 배치: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$BATCH_LOG"

for E in economy politics world; do
    echo "" | tee -a "$BATCH_LOG"
    echo "================================================" | tee -a "$BATCH_LOG"
    echo "[$E] 시작: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$BATCH_LOG"
    echo "================================================" | tee -a "$BATCH_LOG"

    if ./scripts/train_lora_resilient.sh "$E" 2000 100; then
        echo "[$E] 완료: $(date '+%H:%M:%S')" | tee -a "$BATCH_LOG"
    else
        rc=$?
        echo "[$E] 실패 rc=$rc, 다음 전문가로 진행" | tee -a "$BATCH_LOG"
    fi
done

echo "" | tee -a "$BATCH_LOG"
echo "배치 완료: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$BATCH_LOG"
