"""LoRA 학습용 데이터 포맷 변환

각 전문가별로 실데이터(.jsonl) + 합성(.synthetic.jsonl)을 합쳐
mlx-lm 표준 chat 형식으로 변환 + train/valid 분할.

출력 구조:
  data/lora/<expert_id>/
    train.jsonl
    valid.jsonl
    meta.json
"""
import argparse
import json
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAINING_DIR = os.path.join(ROOT, 'data', 'training')
LORA_DIR = os.path.join(ROOT, 'data', 'lora')

VALID_RATIO = 0.1
MIN_TOTAL = 20  # 이 미만이면 LoRA 학습 불가


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def to_chat_format(sample):
    """샘플을 mlx_lm messages 형식으로 변환"""
    return {
        'messages': [
            {'role': 'system', 'content': sample['system']},
            {'role': 'user', 'content': sample['user']},
            {'role': 'assistant', 'content': sample['assistant']},
        ]
    }


def prepare_expert(expert_id):
    real_path = os.path.join(TRAINING_DIR, f'expert_{expert_id}.jsonl')
    synth_path = os.path.join(TRAINING_DIR, f'expert_{expert_id}_synthetic.jsonl')

    real = load_jsonl(real_path)
    synth = load_jsonl(synth_path)
    samples = real + synth

    out_dir = os.path.join(LORA_DIR, expert_id)
    os.makedirs(out_dir, exist_ok=True)

    if len(samples) < MIN_TOTAL:
        print(f"   {expert_id}: {len(samples)}개 (MIN_TOTAL={MIN_TOTAL} 미달), 스킵")
        return None

    # 셔플 후 train/valid 분할
    random.seed(42)
    random.shuffle(samples)
    n_valid = max(2, int(len(samples) * VALID_RATIO))
    valid = samples[:n_valid]
    train = samples[n_valid:]

    # mlx-lm chat 형식으로 저장
    with open(os.path.join(out_dir, 'train.jsonl'), 'w', encoding='utf-8') as f:
        for s in train:
            f.write(json.dumps(to_chat_format(s), ensure_ascii=False) + '\n')
    with open(os.path.join(out_dir, 'valid.jsonl'), 'w', encoding='utf-8') as f:
        for s in valid:
            f.write(json.dumps(to_chat_format(s), ensure_ascii=False) + '\n')

    meta = {
        'expert_id': expert_id,
        'total': len(samples),
        'real': len(real),
        'synthetic': len(synth),
        'train': len(train),
        'valid': len(valid),
    }
    with open(os.path.join(out_dir, 'meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"   {expert_id}: 총 {len(samples)}개 (실 {len(real)}+합성 {len(synth)}) "
          f", train {len(train)} / valid {len(valid)}")
    return meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expert', help='특정 전문가만 (없으면 전부)')
    args = parser.parse_args()

    experts = [args.expert] if args.expert else [
        'stocks', 'economy', 'tech', 'politics',
        'world', 'society', 'sports', 'culture', 'general',
    ]

    print(f"LoRA 데이터 생성: {LORA_DIR}\n")
    results = []
    for e in experts:
        meta = prepare_expert(e)
        if meta:
            results.append(meta)

    print(f"\n학습 가능 전문가: {len(results)}명")
    if results:
        print(f"\n{'전문가':>10} | {'전체':>6} | {'실':>5} | {'합성':>5} | {'train':>6} | {'valid':>5}")
        print('-' * 60)
        for m in results:
            print(f"{m['expert_id']:>10} | {m['total']:>6} | {m['real']:>5} | "
                  f"{m['synthetic']:>5} | {m['train']:>6} | {m['valid']:>5}")


if __name__ == '__main__':
    main()
