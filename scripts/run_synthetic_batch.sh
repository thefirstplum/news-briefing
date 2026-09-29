#!/bin/bash
# 전문가 4명 합성 데이터를 차례로 생성 (tech, sports, society, culture)
# 각 30개. 약 6시간 예상.

set -u

cd "$(dirname "$0")/.."
# 가상환경 파이썬을 쓰려면 PYTHON=/path/to/python 으로 넘긴다
PYTHON="${PYTHON:-python3}"
LOG_DIR=logs

mkdir -p "$LOG_DIR"
BATCH_LOG="$LOG_DIR/synthetic_batch_$(date +%Y%m%d_%H%M%S).log"

echo "합성 배치 시작: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$BATCH_LOG"

for EXPERT in tech sports society culture; do
    echo "" | tee -a "$BATCH_LOG"
    echo "================================================" | tee -a "$BATCH_LOG"
    echo "[$EXPERT] 시작: $(date '+%H:%M:%S')" | tee -a "$BATCH_LOG"
    echo "================================================" | tee -a "$BATCH_LOG"
    $PYTHON scripts/generate_synthetic_expert.py --expert "$EXPERT" --target 30 --max-per-seed 3 \
        >> "$BATCH_LOG" 2>&1
    rc=$?
    if [ "$rc" -ne 0 ]; then
        echo "[$EXPERT] 종료 코드 $rc, 다음으로 계속" | tee -a "$BATCH_LOG"
    fi
    echo "[$EXPERT] 종료: $(date '+%H:%M:%S')" | tee -a "$BATCH_LOG"
done

echo "" | tee -a "$BATCH_LOG"
echo "합성 배치 완료: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$BATCH_LOG"

# 끝나면 통합 통계 다시 추출
echo "" | tee -a "$BATCH_LOG"
echo "통합 통계 갱신 중..." | tee -a "$BATCH_LOG"
$PYTHON scripts/extract_training_data.py >> "$BATCH_LOG" 2>&1
