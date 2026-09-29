"""브리핑 결과에서 전문가별 LoRA 학습 데이터 추출

브리핑 JSON에서 (입력=기사들, 출력=분석결과) 쌍을 추출하고
dominant category 기반으로 전문가별 JSONL로 분리한다.

출력 형식 (unsloth/QLoRA 친화적):
{
  "expert_id": "stocks",
  "system": "...전문가 시스템 프롬프트...",
  "user": "...테마 제목 + 기사들...",
  "assistant": "...분석 결과 JSON 문자열..."
}
"""
import os
import sys
import json
import glob
from collections import Counter, defaultdict
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import Config
from analyzers.experts import get_expert, EXPERT_IDS
from analyzers.experts.prompts import EXPERT_PROMPTS

BRIEFING_DIR = os.path.join(Config.HDD_BASE_PATH, 'briefings')
OUT_DIR = os.path.join(ROOT, 'data', 'training')

# 품질 필터
MIN_IMPORTANCE = 6
MIN_KEY_FACTS = 3
MIN_BACKGROUND_LEN = 50


def extract_input_text(theme):
    """테마를 user 메시지 텍스트로 변환"""
    title = theme.get('title', '').strip()
    articles = theme.get('_articles', []) or []

    lines = [f"테마: {title}", "", "[관련 기사]"]
    for a in articles[:8]:
        src = a.get('source', '')
        ttl = (a.get('title') or '').strip()
        snip = (a.get('content_snippet') or '')[:120]
        if ttl:
            lines.append(f"- [{src}] {ttl}")
            if snip:
                lines.append(f"  {snip}")
    return '\n'.join(lines)


def extract_output_json(theme):
    """테마를 assistant 메시지(분석 결과 JSON)로 변환"""
    out = {
        'title': theme.get('title', ''),
        'background': theme.get('background', ''),
        'current_situation': theme.get('current_situation', ''),
        'flow_analysis': theme.get('flow_analysis', ''),
        'prediction': theme.get('prediction', ''),
        'korea_impact': theme.get('korea_impact', ''),
        'key_facts': theme.get('key_facts', []) or [],
        'importance': theme.get('importance', 0),
        'keywords': theme.get('keywords', []) or [],
    }
    return json.dumps(out, ensure_ascii=False)


def passes_quality(theme):
    """학습 데이터로 쓸만한 품질인지"""
    if theme.get('importance', 0) < MIN_IMPORTANCE:
        return False
    if len(theme.get('key_facts') or []) < MIN_KEY_FACTS:
        return False
    if len(theme.get('background', '') or '') < MIN_BACKGROUND_LEN:
        return False
    if not theme.get('_articles'):
        return False
    return True


def main():
    if not os.path.exists(BRIEFING_DIR):
        print(f"브리핑 디렉토리 없음: {BRIEFING_DIR}")
        sys.exit(1)

    os.makedirs(OUT_DIR, exist_ok=True)

    files = sorted(glob.glob(os.path.join(BRIEFING_DIR, 'briefing_*.json')))
    print(f"브리핑 파일: {len(files)}개")

    # 중복 제거를 위한 (expert, title) 시그니처 추적
    seen_sigs = set()
    stats = defaultdict(int)
    per_expert = defaultdict(list)
    total_themes = 0
    filtered_themes = 0

    for fp in files:
        try:
            with open(fp, encoding='utf-8') as f:
                briefing = json.load(f)
        except Exception as e:
            print(f"로드 실패 {fp}: {e}")
            continue

        for theme in briefing.get('themes', []):
            total_themes += 1

            if not passes_quality(theme):
                filtered_themes += 1
                continue

            articles = theme.get('_articles', []) or []
            cat_counts = Counter(a.get('category', '') for a in articles if a.get('category'))
            dom_cat = cat_counts.most_common(1)[0][0] if cat_counts else ''
            expert_id = get_expert(dom_cat)

            sig = (expert_id, theme.get('title', '').strip()[:60])
            if sig in seen_sigs:
                continue
            seen_sigs.add(sig)

            sample = {
                'expert_id': expert_id,
                'system': EXPERT_PROMPTS.get(expert_id, EXPERT_PROMPTS['general']),
                'user': extract_input_text(theme),
                'assistant': extract_output_json(theme),
                'source_briefing': os.path.basename(fp),
                'dom_category': dom_cat,
            }
            per_expert[expert_id].append(sample)
            stats[expert_id] += 1

    # 전문가별 JSONL 저장
    print(f"\n추출 결과 (전체 {total_themes}개 테마 중 품질 필터 통과 후 중복제거)")
    print(f"   - 품질 미달 스킵: {filtered_themes}개")
    print(f"   - 중복 제거됨: {total_themes - filtered_themes - sum(stats.values())}개")
    print(f"   - 학습 샘플: {sum(stats.values())}개\n")

    for expert_id in EXPERT_IDS:
        samples = per_expert.get(expert_id, [])
        out_path = os.path.join(OUT_DIR, f'expert_{expert_id}.jsonl')
        with open(out_path, 'w', encoding='utf-8') as f:
            for s in samples:
                f.write(json.dumps(s, ensure_ascii=False) + '\n')
        print(f"   {expert_id:>10}: {len(samples):>5}개, {out_path}")

    # 메타 정보 저장
    meta = {
        'generated_at': datetime.now().isoformat(),
        'briefing_dir': BRIEFING_DIR,
        'total_briefings': len(files),
        'total_themes': total_themes,
        'quality_filtered': filtered_themes,
        'samples_per_expert': dict(stats),
        'total_samples': sum(stats.values()),
        'quality_thresholds': {
            'min_importance': MIN_IMPORTANCE,
            'min_key_facts': MIN_KEY_FACTS,
            'min_background_len': MIN_BACKGROUND_LEN,
        },
    }
    with open(os.path.join(OUT_DIR, 'meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"\n메타데이터: {os.path.join(OUT_DIR, 'meta.json')}")


if __name__ == '__main__':
    main()
