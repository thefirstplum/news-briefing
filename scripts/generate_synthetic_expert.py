"""전문가별 합성 학습 데이터 일반 생성기

사용법:
  python scripts/generate_synthetic_expert.py --expert tech --target 50
  python scripts/generate_synthetic_expert.py --expert sports --target 50
  python scripts/generate_synthetic_expert.py --expert society --target 50
  python scripts/generate_synthetic_expert.py --expert culture --target 50
  python scripts/generate_synthetic_expert.py --expert stocks --target 100  # 추가 보강용
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
from analyzers.experts.router import CATEGORY_TO_EXPERT
from analyzers.flow_analyzer import SYSTEM_PROMPT, THEME_ANALYSIS_PROMPT
from storage.vector_store import VectorStore

# 각 전문가별 (시드 쿼리들, 검색 카테고리 목록)
EXPERT_CONFIG = {
    'stocks': {
        'categories': ['stocks'],
        'seeds': [
            "코스피 상승 외국인 매수", "코스피 하락 매도 사이드카",
            "삼성전자 SK하이닉스 반도체 주가", "엔비디아 AI 반도체 시가총액",
            "원달러 환율 상승 수출주", "FOMC 금리 인하 증시 영향",
            "코스닥 바이오 성장주 급등", "2차전지 LG에너지솔루션 SK이노베이션",
            "조선주 HD현대중공업 한화오션 수주", "방산주 한화에어로 LIG넥스원 수주",
            "건설주 부동산 재건축 수혜", "K-반도체 D램 가격 동향",
            "ETF 자금 유입 패시브 투자", "공매도 재개 신용잔고 변동",
            "옵션만기일 변동성 ELS", "뉴욕증시 다우 나스닥 사상최고",
            "테슬라 전기차 주가 실적", "애플 아이폰 매출 자사주 매입",
            "메타 마이크로소프트 AI 빅테크", "한국은행 기준금리 결정 증시",
            "외국인 순매수 기관 매도", "배당주 고배당 ETF 시즌",
            "신약 임상 바이오 모멘텀", "원전 SMR 한국전력 두산에너빌리티",
            "AI 인프라 SK하이닉스 HBM", "코스피 12000 골드만 전망",
            "엔비디아 실적 발표 시장 반응", "BOJ 일본 엔화 정책 변화",
            "위안화 약세 중국 경기 우려", "원유 OPEC 감산 정유주",
            "리비아 이라크 산유국 정세", "FED 점도표 기준금리 전망",
        ],
    },
    'tech': {
        'categories': ['tech', 'general'],
        'seeds': [
            "엔비디아 H200 차세대 GPU", "오픈AI GPT-5 신모델 출시",
            "앤트로픽 클로드 새 버전 성능", "구글 제미나이 멀티모달",
            "메타 라마4 오픈소스 LLM", "마이크로소프트 코파일럿 윈도우",
            "삼성 갤럭시 AI 기능 출시", "애플 인텔리전스 시리 강화",
            "쿠팡 네이버 카카오 플랫폼 경쟁", "토스 카카오뱅크 인터넷은행",
            "한국 AI 반도체 스타트업 투자", "데이터센터 전력 인프라 확장",
            "퀄컴 스냅드래곤 모바일 칩", "TSMC 파운드리 첨단공정 3nm",
            "AMD 인텔 CPU 시장 경쟁", "양자컴퓨터 IBM 구글 연구",
            "자율주행 테슬라 웨이모 비교", "전기차 배터리 LFP NCM 기술",
            "휴머노이드 로봇 옵티머스 피규어", "AI 영상 생성 소라 베오",
            "Soundraw Suno AI 음악 생성", "엣지 AI 온디바이스 추론",
            "오픈AI 코드인터프리터 데이터 분석", "AI 의료 영상 진단",
            "딥페이크 가짜뉴스 탐지 기술", "사이버보안 AI 침해 대응",
        ],
    },
    'sports': {
        'categories': ['sports'],
        'seeds': [
            "손흥민 토트넘 EPL 골", "이강인 PSG 리그앙",
            "김민재 바이에른 분데스리가", "메시 인터마이애미 MLS",
            "호날두 알나스르 사우디 리그", "KBO 한화 LG 두산 우승",
            "키움 히어로즈 류현진 박찬호", "MLB 김하성 이정후 활약",
            "박찬호 야구 명예의 전당", "PGA 김주형 임성재 우승",
            "LPGA 김효주 박성현 우승", "테니스 그랜드슬램 정현 권순우",
            "NBA 르브론 커리 평균", "올림픽 양궁 김우진 안산",
            "축구 국가대표 손흥민 부상", "K리그 울산 전북 우승",
            "아시안컵 한국 일본 결승", "월드컵 예선 한국 본선",
            "F1 페라리 메르세데스 그랑프리", "복싱 김지훈 챔피언",
            "UFC 김광식 정찬성 옥타곤", "골프 마스터즈 그린재킷",
            "수영 황선우 우상혁 메달", "스피드스케이팅 이상화 후예",
            "양궁 컴파운드 리커브 결승", "농구 KBL 챔피언 결정전",
        ],
    },
    'society': {
        'categories': ['society', 'general'],
        'seeds': [
            "노동 임금협상 파업 노조", "최저임금 인상 자영업자 반발",
            "교육 수능 대입 정시 수시", "의대 정원 증원 의료 파업",
            "공무원 연금 개혁 국민연금", "건강보험 보장률 본인부담",
            "출산율 저출생 인구절벽", "고령화 노인 빈곤 복지",
            "청년 실업 비정규직 일자리", "외국인 노동자 비자 E-9",
            "기후 변화 폭염 한파 미세먼지", "산업 재해 중대재해처벌법",
            "사건사고 화재 폭발 추락", "음주운전 윤창호법 음주측정",
            "성폭력 성희롱 미투 처벌", "아동학대 보호 시설 입소",
            "검찰 경찰 수사권 조정 갈등", "재판 판결 항소심 대법원",
            "마약 단속 펜타닐 케타민", "범죄 보이스피싱 스미싱 사기",
            "다문화 가정 차별 통합", "장애인 차별 접근권 권리",
            "주거 임대차 3법 전세사기", "교통 사고 자전거 킥보드",
            "동물복지 학대 유기견 입양", "공교육 사교육비 입시경쟁",
        ],
    },
    'culture': {
        'categories': ['culture', 'general'],
        'seeds': [
            "한국 영화 개봉 흥행 박스오피스", "넷플릭스 오리지널 드라마",
            "디즈니플러스 한국 콘텐츠", "쿠팡플레이 OTT 경쟁",
            "K-팝 BTS 블랙핑크 뉴진스", "K-팝 빌보드 차트 진입",
            "JYP SM YG 하이브 엔터", "뮤지컬 공연 라이센스 창작",
            "오페라 발레 클래식 공연", "미술 전시 갤러리 미디어아트",
            "베니스 비엔날레 한국관", "칸 영화제 한국 영화 수상",
            "베를린 토론토 영화제 참가", "한국 드라마 한류 해외수출",
            "도서 베스트셀러 출판 트렌드", "노벨문학상 한국 작가 후보",
            "건축상 프리츠커상 한국 건축가", "패션 컬렉션 서울 패션위크",
            "트로트 가요 시장 부활", "인디 밴드 페스티벌 록 페스티벌",
            "예능 프로그램 시청률 화제성", "유튜브 콘텐츠 크리에이터",
            "웹툰 망가 글로벌 시장", "게임 e스포츠 리그오브레전드",
            "전통 문화 한복 한식 K-푸드", "방송 드라마 OST 음원 차트",
        ],
    },
    'economy': {
        'categories': ['economy', 'industry', 'realestate'],
        'seeds': [
            "한국은행 기준금리 인상 동결", "원달러 환율 변동 외환시장",
            "소비자물가 상승 인플레이션", "GDP 성장률 전망 한국 미국",
            "수출 반도체 자동차 무역수지", "한미 통상 관세 협상",
            "한중 무역 디스플레이 화장품", "정부 추경 세수 재정정책",
            "기재부 부총리 경제 정책 방향", "금감원 금융위 규제 정책",
            "은행 대출 신용대출 주담대", "삼성 현대차 LG 영업이익",
            "조선 수주 잔량 컨테이너선", "건설 수주 토목 건축",
            "부동산 매매가 전세가 변동", "분양 청약 경쟁률 미분양",
            "재건축 재개발 입주권 거래", "공공임대 주거복지 무주택",
            "물가 식료품 농산물 가공식품", "전기요금 가스요금 공공요금",
            "유가 OPEC 휘발유 경유 가격", "환율 강달러 약달러 영향",
        ],
    },
    'politics': {
        'categories': ['politics', 'general'],
        'seeds': [
            "대통령 청와대 지시 방향", "총리 부총리 임명 청문회",
            "여당 국민의힘 당대표 원내대표", "민주당 당대표 최고위원",
            "국회 본회의 법안 표결 통과", "상임위 국정감사 청문회",
            "선거 출마 후보 공약 유세", "지방선거 보궐선거 결과",
            "검찰 수사 기소 영장 청구", "특검 국정조사 진상규명",
            "탄핵 발의 가결 부결 표결", "헌법재판소 위헌 판결",
            "외교 정상회담 한미 한일 한중", "안보 북핵 미사일 ICBM",
            "통일 남북관계 대화 제재", "국방 한미동맹 연합훈련",
            "예산 편성 국회 심의 의결", "세법 개정 양도세 종부세",
            "행정 부처 개편 장관 인사", "공무원 인사 청와대 비서관",
        ],
    },
    'world': {
        'categories': ['world'],
        'seeds': [
            "미국 트럼프 백악관 정책", "바이든 행정부 외교 안보",
            "중국 시진핑 정치국 상무위", "일본 기시다 자민당 총재",
            "러시아 푸틴 우크라이나 전쟁", "젤렌스키 우크라이나 대통령",
            "이스라엘 가자지구 휴전 협상", "이란 핵협상 제재 해제",
            "북한 김정은 미사일 발사", "사우디 OPEC 산유국 회의",
            "유럽 EU 정상회담 의제", "독일 메르츠 총리 정책",
            "프랑스 마크롱 대통령 개혁", "영국 노동당 총리 정책",
            "NATO 정상회담 우크라이나 지원", "G7 G20 정상회의 합의",
            "아세안 정상회의 동남아", "인도 모디 정부 경제정책",
            "남미 브라질 멕시코 정세", "아프리카 분쟁 평화 협정",
            "중동 정세 시리아 예멘", "대만 양안관계 차이잉원",
        ],
    },
    'general': {
        'categories': ['general'],
        'seeds': [
            "사회 이슈 화제 토론", "정책 사회적 영향 평가",
            "기획 시리즈 깊이 있는 분석", "특집 보도 심층 취재",
            "날씨 기상 예보 한파 폭염", "환경 미세먼지 황사 오존",
        ],
    },
}


def collect_articles(expert_id, max_per_query=15):
    """벡터DB에서 expert_id의 카테고리 기사 시드별 수집"""
    config = EXPERT_CONFIG[expert_id]
    vector = VectorStore()
    groups = []

    for query in config['seeds']:
        try:
            results = vector.search(
                query=query, n_results=max_per_query,
                category=config['categories'],
            )
        except Exception as e:
            print(f"검색 실패 [{query}]: {e}")
            continue

        if len(results) < 5:
            continue

        ids = [r['id'] for r in results]
        try:
            raw = vector.collection.get(ids=ids, include=['documents', 'metadatas'])
            articles = []
            for i, aid in enumerate(raw.get('ids', [])):
                meta = (raw.get('metadatas') or [{}])[i] or {}
                doc = (raw.get('documents') or [''])[i] or ''
                parts = doc.split('\n', 1)
                title = parts[0] if parts else meta.get('title', '')
                snippet = parts[1] if len(parts) > 1 else ''
                articles.append({
                    'id': aid,
                    'title': title,
                    'content_snippet': snippet,
                    'source': meta.get('source', ''),
                    'category': meta.get('category', ''),
                    'date': meta.get('date', ''),
                })
            groups.append({'seed_query': query, 'articles': articles[:max_per_query]})
        except Exception as e:
            print(f"본문 조회 실패: {e}")

    return groups


def analyze_with_expert(theme, expert_id, client):
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
    system = SYSTEM_PROMPT + '\n\n' + EXPERT_PROMPTS[expert_id]
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expert', required=True, choices=list(EXPERT_CONFIG.keys()))
    parser.add_argument('--target', type=int, default=50)
    parser.add_argument('--max-per-seed', type=int, default=3)
    args = parser.parse_args()

    expert_id = args.expert
    out_path = os.path.join(ROOT, 'data', 'training', f'expert_{expert_id}_synthetic.jsonl')
    progress_path = out_path + '.progress.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    print(f"[{expert_id}] 합성 데이터 생성 (목표 {args.target}개)")
    print(f"출력: {out_path}\n")

    # 기존 진행 상황 로드
    accepted = 0
    if os.path.exists(out_path):
        with open(out_path, encoding='utf-8') as f:
            accepted = sum(1 for _ in f)
    print(f"   기존 누적: {accepted}개\n")

    print("벡터DB에서 기사 수집 중...")
    groups = collect_articles(expert_id)
    print(f"   {len(groups)}개 시드 유효 그룹 확보\n")

    if not groups:
        print(f"{expert_id} 카테고리 데이터 부족")
        sys.exit(1)

    client = OllamaClient()
    if not client.is_available():
        print("Ollama 미연결")
        sys.exit(1)

    out_f = open(out_path, 'a', encoding='utf-8')
    rejected = 0
    start_time = time.time()
    random.seed(42)
    random.shuffle(groups)

    try:
        for group in groups:
            if accepted >= args.target:
                break
            articles = group['articles']
            for trial in range(args.max_per_seed):
                if accepted >= args.target:
                    break
                random.shuffle(articles)
                k = min(random.randint(5, 8), len(articles))
                sorted_arts = sorted(articles[:k], key=lambda a: a.get('date', ''), reverse=True)
                theme_title = (sorted_arts[0].get('title') if sorted_arts else group['seed_query'])[:80]
                theme = {'title': theme_title, 'articles': articles[:k]}

                print(f"   [{accepted+1}/{args.target}] {group['seed_query'][:30]:30s} (k={k})... ", end='', flush=True)
                result = analyze_with_expert(theme, expert_id, client)
                if not passes_quality(result):
                    print("품질 미달")
                    rejected += 1
                    continue

                sample = {
                    'expert_id': expert_id,
                    'system': EXPERT_PROMPTS[expert_id],
                    'user': '\n'.join([
                        f"테마: {theme['title']}", "", "[관련 기사]"
                    ] + [
                        f"- [{a.get('source','')}] {a['title']}" + (
                            f"\n  {a.get('content_snippet','')[:120]}" if a.get('content_snippet') else ''
                        )
                        for a in theme['articles']
                    ]),
                    'assistant': json.dumps(result, ensure_ascii=False),
                    'seed_query': group['seed_query'],
                    'synthetic': True,
                }
                out_f.write(json.dumps(sample, ensure_ascii=False) + '\n')
                out_f.flush()
                accepted += 1
                elapsed = time.time() - start_time
                rate = accepted / elapsed if elapsed > 0 else 0
                eta = (args.target - accepted) / rate if rate > 0 else 0
                print(f"OK ({rate:.2f}/s, ETA {eta/60:.1f}분)")
    finally:
        out_f.close()

    print(f"\n[{expert_id}] 완료")
    print(f"   수용: {accepted}개 / 거절: {rejected}개")
    print(f"   통과율: {accepted/(accepted+rejected)*100:.1f}%" if (accepted+rejected) else "")


if __name__ == '__main__':
    main()
