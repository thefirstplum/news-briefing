"""학습된 LoRA 어댑터 추론 테스트. 베이스 모델과 나란히 비교한다."""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expert', default='stocks')
    parser.add_argument('--base-model', default='mlx-community/gemma-3-4b-it-qat-4bit')
    parser.add_argument('--sample-idx', type=int, default=0, help='valid.jsonl에서 몇 번째 샘플')
    parser.add_argument('--max-tokens', type=int, default=800)
    args = parser.parse_args()

    valid_path = os.path.join(ROOT, 'data', 'lora', args.expert, 'valid.jsonl')
    if not os.path.exists(valid_path):
        print(f"{valid_path} 없음")
        sys.exit(1)

    with open(valid_path, encoding='utf-8') as f:
        samples = [json.loads(l) for l in f if l.strip()]

    if args.sample_idx >= len(samples):
        print(f"valid 샘플 {len(samples)}개. idx={args.sample_idx} 초과")
        sys.exit(1)

    sample = samples[args.sample_idx]
    messages = sample['messages']

    print(f"=== 입력 (system / user) ===")
    print(f"[system] {messages[0]['content'][:200]}...")
    print()
    print(f"[user] {messages[1]['content'][:400]}...")
    print()
    print(f"=== 기대 출력 (참고용) ===")
    expected = messages[2]['content']
    try:
        expected_obj = json.loads(expected)
        print(f"제목: {expected_obj.get('title', '')}")
        print(f"중요도: {expected_obj.get('importance', '')}")
        print(f"배경: {expected_obj.get('background', '')[:120]}...")
    except Exception:
        print(expected[:300])
    print()
    print("=" * 60)

    from mlx_lm import load, generate

    adapter_path = os.path.join(ROOT, 'data', 'lora', args.expert, 'adapters')

    for label, ap in [('BASE  (LoRA 없음)', None), ('LoRA  (학습 후)', adapter_path)]:
        print(f"\n=== {label} ===")
        model, tokenizer = load(args.base_model, adapter_path=ap)
        # gemma chat template 사용
        prompt = tokenizer.apply_chat_template(
            messages[:2],  # system + user (assistant 빼고)
            add_generation_prompt=True,
            tokenize=False,
        )
        text = generate(model, tokenizer, prompt=prompt, max_tokens=args.max_tokens, verbose=False)
        print(text)
        print("-" * 60)


if __name__ == '__main__':
    main()
