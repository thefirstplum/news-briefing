"""stocks 전문가 합성 학습 데이터 생성

벡터DB에서 stocks 카테고리 기사들을 모아 가상 테마를 만들고,
로컬 qwen3.6:35b-a3b 모델에 stocks 전문가 프롬프트로 분석을 요청해
합성 데이터를 만든다.

사용법:
  python scripts/generate_synthetic_stocks.py --target 150 --batch 10

품질 필터:
  - importance >= 7
  - key_facts >= 4
  - 출력 필드 모두 채워짐
"""
import argparse
import json
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from analyzers.ollama_client import OllamaClient
from analyzers.experts.prompts import EXPERT_PROMPTS
from analyzers.flow_analyzer import SYSTEM_PROMPT, THEME_ANALYSIS_PROMPT
from storage.vector_store import VectorStore

OUT_PATH = os.path.join(ROOT, 'data', 'training', 'expert_stocks_synthetic.jsonl')
PROGRESS_PATH = os.path.join(ROOT, 'data', 'training', 'expert_stocks_synthetic.progress.json')

# 가상 테마를 만들기 위한 seed 키워드 (매매 판단에 직결되는 주제들)
SEED_QUERIES = [
    "코스피 상승 외국인 매수",
    "코스피 하락 매도 사이드카",
    "삼성전자 SK하이닉스 반도체 주가",
    "엔비디아 AI 반도체 시가총액",
    "원달러 환율 상승 수출주",
    "FOMC 금리 인하 증시 영향",
    "코스닥 바이오 성장주 급등",
    "2차전지 LG에너지솔루션 SK이노베이션",
    "조선주 HD현대중공업 한화오션 수주",
    "방산주 한화에어로 LIG넥스원 수주",
    "건설주 부동산 재건축 수혜",
    "K-반도체 D램 가격 동향",
    "ETF 자금 유입 패시브 투자",
    "공매도 재개 신용잔고 변동",
    "옵션만기일 변동성 ELS",
    "뉴욕증시 다우 나스닥 사상최고",
    "테슬라 전기차 주가 실적",
    "애플 아이폰 매출 자사주 매입",
    "메타 마이크로소프트 AI 빅테크",
    "한국은행 기준금리 결정 증시",
    "외국인 순매수 기관 매도",
    "배당주 고배당 ETF 시즌",
    "신약 임상 바이오 모멘텀",
    "원전 SMR 한국전력 두산에너빌리티",
    "AI 인프라 SK하이닉스 HBM",
    "코스피 12000 골드만 전망",
    "엔비디아 실적 발표 시장 반응",
    "BOJ 일본 엔화 정책 변화",
    "위안화 약세 중국 경기 우려",
    "원유 OPEC 감산 정유주",
    "리비아 이라크 산유국 정세",
    "FED 점도표 기준금리 전망",
]


def collect_stocks_articles(min_per_query=8, max_per_query=15):
    """벡터DB에서 stocks 카테고리 기사를 시드 쿼리별로 모은다.
    반환: [{title, source, content_snippet, date, category, id}, ...] 그룹 리스트
    """
    vector = VectorStore()
    groups = []

    for query in SEED_QUERIES:
        try:
            results = vector.search(
                query=query,
                n_results=max_per_query,
                category=['stocks'],
            )
        except Exception as e:
            print(f"검색 실패 [{query}]: {e}")
            continue

        if len(results) < min_per_query:
            continue

        # 기사 메타정보만 있으므로 본문은 collection 직접 조회
        ids = [r['id'] for r in results]
        try:
            raw = vector.collection.get(ids=ids, include=['documents', 'metadatas'])
            articles = []
            for i, aid in enumerate(raw.get('ids', [])):
                meta = (raw.get('metadatas') or [{}])[i] or {}
                doc = (raw.get('documents') or [''])[i] or ''
                # doc 형식: "title\nsnippet"
                parts = doc.split('\n', 1)
                title = parts[0] if parts else meta.get('title', '')
                snippet = parts[1] if len(parts) > 1 else ''
                articles.append({
                    'id': aid,
                    'title': title,
                    'content_snippet': snippet,
                    'source': meta.get('source', ''),
                    'category': meta.get('category', 'stocks'),
                    'date': meta.get('date', ''),
                })
            groups.append({
                'seed_query': query,
                'articles': articles[:max_per_query],
            })
        except Exception as e:
            print(f"본문 조회 실패 [{query}]: {e}")

    return groups


def build_theme_from_group(group):
    """검색된 기사 그룹으로 가상 테마를 만든다."""
    articles = group['articles']
    # 가장 최근 날짜의 핵심 기사 제목을 테마 제목으로
    sorted_arts = sorted(articles, key=lambda a: a.get('date', ''), reverse=True)
    theme_title = (sorted_arts[0].get('title') if sorted_arts else group['seed_query'])[:80]

    return {
        'title': theme_title,
        'articles': articles,
        'keywords': [],
        'theme_id': f"synthetic_{hash(group['seed_query']) & 0xfffffff:x}",
    }


def analyze_with_stocks_expert(theme, client):
    """stocks 전문가 system prompt로 단일 테마 분석"""
    articles_text = '\n'.join(
        f"- [{a.get('source', '')}] {a['title']}"
        + (f"\n  {a.get('content_snippet', '')[:120]}" if a.get('content_snippet') else '')
        for a in theme['articles'][:10]
    )

    history_context = "(이 주제에 대한 이전 분석 히스토리가 아직 없습니다. 기사 내용을 기반으로 배경을 작성해주세요.)"
    prompt = THEME_ANALYSIS_PROMPT.format(
        theme_title=theme['title'][:50],
        articles_text=articles_text,
        history_context=history_context,
    )

    system = SYSTEM_PROMPT + '\n\n' + EXPERT_PROMPTS['stocks']
    return client.generate_json(prompt, system=system)


def passes_quality(result):
    if not result:
        return False
    if result.get('importance', 0) < 7:
        return False
    if len(result.get('key_facts') or []) < 4:
        return False
    if len(result.get('background', '') or '') < 50:
        return False
    if len(result.get('current_situation', '') or '') < 50:
        return False
    return True


def load_progress():
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH, encoding='utf-8') as f:
            return json.load(f)
    return {'completed_seeds': [], 'sample_count': 0}


def save_progress(state):
    with open(PROGRESS_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=int, default=150, help='목표 샘플 수')
    parser.add_argument('--max-per-seed', type=int, default=5, help='시드당 최대 샘플 수')
    args = parser.parse_args()

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    print(f"stocks 합성 데이터 생성 (목표 {args.target}개)")
    print(f"출력: {OUT_PATH}\n")

    print("벡터DB에서 stocks 기사 수집 중...")
    groups = collect_stocks_articles()
    print(f"   {len(groups)}개 시드에서 유효 그룹 확보\n")

    if not groups:
        print("시드 그룹 0개. 벡터DB에 stocks 데이터가 부족합니다.")
        sys.exit(1)

    state = load_progress()
    print(f"   기존 진행 상황: {state['sample_count']}개 완료")

    client = OllamaClient()
    if not client.is_available():
        print("Ollama 미연결")
        sys.exit(1)

    out_f = open(OUT_PATH, 'a', encoding='utf-8')
    accepted = state['sample_count']
    rejected = 0
    start_time = time.time()

    try:
        # 시드 그룹 셔플하여 다양성 확보
        random.seed(42)
        random.shuffle(groups)

        for group in groups:
            seed = group['seed_query']
            if accepted >= args.target:
                break

            # 시드당 max-per-seed개씩 다양한 기사 조합으로 합성
            articles = group['articles']
            attempts_per_seed = 0
            for trial in range(args.max_per_seed):
                if accepted >= args.target:
                    break
                if attempts_per_seed >= args.max_per_seed:
                    break

                # 매 시도마다 기사 셔플하고 5~8개 선택
                random.shuffle(articles)
                k = min(random.randint(5, 8), len(articles))
                theme = build_theme_from_group({
                    'seed_query': seed,
                    'articles': articles[:k],
                })

                attempts_per_seed += 1
                print(f"   [{accepted+1}/{args.target}] {seed[:30]:30s} (k={k})... ", end='', flush=True)

                result = analyze_with_stocks_expert(theme, client)
                if not passes_quality(result):
                    print("품질 미달")
                    rejected += 1
                    continue

                # 학습 형식으로 저장
                sample = {
                    'expert_id': 'stocks',
                    'system': EXPERT_PROMPTS['stocks'],
                    'user': '\n'.join([
                        f"테마: {theme['title']}",
                        "",
                        "[관련 기사]",
                    ] + [
                        f"- [{a.get('source','')}] {a['title']}" + (
                            f"\n  {a.get('content_snippet','')[:120]}" if a.get('content_snippet') else ''
                        )
                        for a in theme['articles']
                    ]),
                    'assistant': json.dumps(result, ensure_ascii=False),
                    'seed_query': seed,
                    'synthetic': True,
                }
                out_f.write(json.dumps(sample, ensure_ascii=False) + '\n')
                out_f.flush()
                accepted += 1
                state['sample_count'] = accepted
                save_progress(state)

                elapsed = time.time() - start_time
                rate = accepted / elapsed if elapsed > 0 else 0
                eta = (args.target - accepted) / rate if rate > 0 else 0
                print(f"OK ({rate:.2f}/s, ETA {eta/60:.1f}분)")
    finally:
        out_f.close()

    print(f"\n합성 데이터 생성 완료")
    print(f"   수용: {accepted}개")
    print(f"   거절: {rejected}개")
    print(f"   품질 통과율: {accepted/(accepted+rejected)*100:.1f}%")


if __name__ == '__main__':
    main()
