import hashlib
import re
from collections import defaultdict, Counter
from datetime import datetime
from .ollama_client import OllamaClient
from .theme_index import ThemeIndex
from .experts import get_expert, get_expert_smart, build_expert_system
from config import Config
import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 한국 주요 일간지의 베테랑 신문기자입니다.
팩트를 정확히 전달하고, 독자가 핵심을 빠르게 파악할 수 있도록 기사를 작성합니다.
추측이나 일반론이 아닌, 취재한 사실에 근거해서만 씁니다.

[문체 규칙]
- 반드시 한국어 존댓말(합쇼체)로 작성하세요. (예: ~입니다, ~했습니다, ~될 전망입니다)
- 영어/일본어/중국어 기사도 반드시 한국어로 작성하세요.
- 절대 중국어(한자 포함)를 출력하지 마세요. 모든 출력은 100% 한국어여야 합니다.
- 외국 고유명사는 반드시 완전한 한글로 표기하세요. 한글과 영어를 섞지 마세요.
  예: Beirut → 베이루트, Six Nations → 식스 네이션스, Hezbollah → 헤즈볼라, Trump → 트럼프
  ❌ 금지: '베irut', 'Ber린', '스??스' 같은 깨진 표기
- 전문 용어는 괄호 안에 쉬운 설명을 넣으세요. (예: "호르무즈 해협(전 세계 원유 20%가 통과하는 핵심 수송로)")
- 반드시 유효한 JSON만 출력하세요. 설명이나 마크다운 없이 JSON만.

[정보 규칙]
- 당신의 학습 데이터는 오래되었을 수 있습니다.
- 인물의 직함, 현재 상황, 사건의 맥락은 반드시 주어진 기사 내용에서 파악하세요.
- 기사에서 누군가를 "대통령"이라고 지칭하면 그 사람이 현직 대통령입니다.
- 당신이 알고 있는 과거 정보와 기사 내용이 충돌하면 기사 내용이 맞습니다.
- 절대 당신의 배경지식으로 기사 내용을 수정하거나 반박하지 마세요.
- 누가 누구에게 한 발언/행동인지 주어와 목적어를 정확히 구분하세요.
  ❌ "A가 B를 비난했다" vs ✅ "B가 A를 비난했다" — 기사 원문에서 주어를 반드시 확인하세요.
  특히 비난, 반대, 요구, 배신 등의 표현에서 방향이 뒤집히지 않도록 주의하세요."""

THEME_ANALYSIS_PROMPT = """다음은 "{theme_title}" 관련 기사들입니다:

{articles_text}

{history_context}

신문 기자처럼 팩트 중심으로 정확하게 분석하세요.
모든 내용은 존댓말(합쇼체: ~입니다, ~했습니다)로 작성하세요.

[핵심 원칙]
- 기사에 나온 사실만 쓰세요. 일반론이나 교과서적 설명 금지.
- "~로 인해 우려를 샀습니다", "~에 영향을 미칠 수 있습니다", "~될 전망입니다" 같은 뻔한 마무리 금지.
- "만약 ~할 경우 ~될 가능성이 있습니다" 패턴 사용 금지. 구체적 근거와 숫자로 서술하세요.
- 구체적 숫자, 인물명, 발언, 날짜를 반드시 포함하세요.
- 전문 용어는 괄호 안에 쉬운 설명을 넣으세요.
- 각 필드는 서로 다른 내용이어야 합니다. 중복 금지.

[각 필드 작성법]
background (배경): 이 이슈가 왜 생겼는지 핵심 원인만. 과거형. 2~3문장. 최대 150자.
current_situation (현황): 오늘 확인된 가장 중요한 사실 1~2개만. 숫자/인물/발언 필수. 현재형. 2~3문장. 최대 200자.
flow_analysis (흐름): 이전과 비교해 무엇이 어떻게 달라졌는지. "A→B" 변화 중심. 1~2문장. 최대 100자.
prediction (전망): 기사 속 근거를 바탕으로, 다음에 벌어질 구체적 상황을 짚어주세요. 1~2문장. 최대 100자.

⚠️ 절대 기사 목록에 있는 모든 내용을 나열하지 마세요. 가장 핵심적인 팩트만 선별하세요.
⚠️ 테마 제목과 무관한 기사 내용은 무시하세요.

[주제 분리 규칙]
- 기사 목록에 테마의 핵심 주제와 무관한 기사가 섞여 있으면 무시하세요.
- 예: "BTS 공연 연차 강요 논란" 테마에 날씨 예보 기사가 섞여 있으면, 날씨 내용은 분석에 포함하지 마세요.
- 배경/현황/흐름/전망 모두 하나의 핵심 주제에만 집중하세요.

[전망 작성법]
❌ 금지: "만약 ~할 경우 ~될 전망입니다" (뻔한 조건문)
❌ 금지: "추가적인 조치가 필요할 것으로 보입니다" (아무 내용 없음)
❌ 금지: 다른 테마의 전망과 같은 내용 반복 (각 테마별로 고유한 전망 필수)
✅ 방법: 이 테마의 기사에서 나온 구체적 숫자, 일정, 인물 발언을 근거로 다음에 벌어질 일을 서술하세요.
✅ 핵심: 기사에 없는 내용을 지어내지 마세요. 기사 속 팩트만으로 전망하세요.

[korea_impact 작성법]
- 해외 뉴스(미국, 중국, 일본, 유럽, 중동 등)일 때만 작성하세요.
- 한국 경제/외교/산업/시장에 미칠 구체적 영향을 1~2문장으로 서술하세요.
- 예: "중국 금리 동결은 한국 수출 기업의 위안화 결제 수익성에 영향을 미칠 수 있으며, 한은의 금리 정책 결정에도 참고 변수가 됩니다."
- 국내 뉴스면 빈 문자열("")로 두세요.

중요도: 9~10 전쟁/위기, 7~8 주요정책/외교, 5~6 사회이슈, 3~4 일반, 1~2 단순보도

{{
  "title": "핵심 제목 (15자 이내, 명사형)",
  "background": "핵심 원인 (2~3문장, 존댓말, 과거형)",
  "current_situation": "오늘의 팩트 (2~3문장, 존댓말, 숫자/인물/발언 필수)",
  "flow_analysis": "변화의 방향 (1~2문장, 존댓말, A→B 비교)",
  "prediction": "조건부 전망 (1~2문장, 존댓말)",
  "korea_impact": "한국에 미치는 영향 (해외 뉴스인 경우만 작성, 국내 뉴스면 빈 문자열)",
  "key_facts": ["기사에서 확인된 핵심 팩트 5개 (숫자/인물/날짜 포함)"],
  "importance": 1~10,
  "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"]
}}"""

THEME_MERGE_PROMPT = """다음은 오늘 뉴스에서 추출한 테마 목록입니다.
같은 사건/이슈를 다루는 테마끼리 묶어주세요.

{themes_list}

[규칙]
- 같은 사건의 다른 측면(원인, 결과, 반응, 파급효과)은 하나로 묶으세요.
  예: "이란 전쟁", "IEA 비축유 방출", "호르무즈 해협 피격", "유가 급등" → 같은 이야기
- 단순히 키워드가 겹치는 것만으로 묶지 마세요. 인과관계가 있어야 합니다.
- 관련 없는 테마는 독립 그룹으로 남겨주세요.
- 반드시 모든 테마 번호가 결과에 포함되어야 합니다.

JSON 배열로 출력하세요. 각 원소는 같은 그룹의 테마 번호 배열입니다.
예: [[1, 3, 5], [2], [4, 6]]

출력:"""

SELF_EVAL_PROMPT = """다음은 {today} 기준 뉴스 브리핑 테마 분석 결과입니다.
**서술 품질만** 평가하세요.

[참고할 원본 기사 제목]
{source_titles}

{themes_json}

⚠️ 절대 금지 사항:
- 사실 여부를 의심하거나 검증하지 마세요. 위 원본 기사가 실제로 보도된 내용입니다.
- "현재 시점이 아니다", "사실관계 부재", "○○가 존재하지 않는다" 같은 평가 금지.
- 당신의 학습 데이터는 오래되어 최신 사건/인물을 모를 수 있습니다.
- 인물의 직함(대통령, 교황, 장관 등), 사건의 발생 여부, 날짜는 무조건 기사대로 신뢰하세요.

[평가 기준 — 서술 품질만]
1. current_situation이 비어있거나 너무 짧은가? (50자 미만이면 불량)
2. prediction이 비어있거나 뻔한 일반론인가? ("~될 전망입니다" 같은 클리셰)
3. 깨진 글자나 한자/일본어 문장이 섞여있는가?
4. title이 분석 내용을 제대로 대표하는가?
5. 한 테마 안에 서로 무관한 주제가 합쳐져 있는가? (예: 정치 + 스포츠, 사건 + 날씨)
   → 합쳐져 있으면 score 3 이하로 평가하세요.
6. background/current_situation/flow_analysis/prediction이 서로 중복되거나 비슷한가?

JSON으로 출력하세요:
{{
  "evaluations": [
    {{"theme_index": 0, "score": 8, "issues": []}},
    {{"theme_index": 1, "score": 4, "issues": ["현황 너무 짧음", "전망이 일반론"]}}
  ],
  "overall_score": 7
}}

- score: 1~10 (7 이상이면 통과, 6 이하면 재생성 필요)
- issues: 서술/형식 관련 문제만. 사실 검증 관련 문제는 적지 마세요."""

OVERALL_BRIEFING_PROMPT = """다음은 {datetime} 기준 주요 뉴스 테마 분석입니다:

{themes_text}

베테랑 기자의 시각으로 오늘의 종합 브리핑을 작성하세요.
존댓말(합쇼체)로 작성하세요.

[규칙]
- 팩트 중심. 일반론/교과서적 마무리 금지.
- headline: 오늘 가장 중요한 사실을 한 줄로 (25자 이내)
- executive_summary: 주요 이슈 간 연결고리와 큰 그림 (3~5문장, 구체적 사실 포함)
- watch_list: 향후 48시간 내 주목할 구체적 이벤트/일정
- risk_factors: 악화 시나리오 (구체적 조건 명시)
- opportunities: 긍정 요인 (구체적 근거 포함)

{{
  "headline": "핵심 헤드라인 (25자 이내)",
  "executive_summary": "종합 요약 (3~5문장, 존댓말, 팩트 중심)",
  "watch_list": ["주목 이벤트1", "주목 이벤트2", "주목 이벤트3"],
  "risk_factors": ["리스크1", "리스크2"],
  "opportunities": ["기회1", "기회2"]
}}"""


class FlowAnalyzer:
    TITLE_SIMILARITY = 0.45

    # 카테고리별 중요도 가중치
    CATEGORY_WEIGHT = {
        'politics': 5,   # 정치
        'economy': 5,     # 경제
        'world': 5,       # 세계
        'society': 4,     # 사회
        'tech': 4,        # IT/과학
        'culture': 1,     # 생활/문화/연예
        'sports': 1,      # 스포츠
        'general': 2,     # 종합
    }

    def __init__(self, store, vector=None):
        self.store = store
        self.vector = vector
        self.client = OllamaClient()
        self.theme_index = ThemeIndex(store)

    def _load_feedback_context(self):
        """최근 7일 사용자 피드백으로 프롬프트 힌트를 만든다."""
        import os, json
        from datetime import timedelta
        feedback_dir = os.path.join(self.store.base_path, 'feedback')
        if not os.path.exists(feedback_dir):
            return ''

        good, bad = [], []
        for i in range(7):
            date_str = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            path = os.path.join(feedback_dir, f'feedback_{date_str}.json')
            if not os.path.exists(path):
                continue
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for fb in data.get('feedbacks', []):
                title = fb.get('title', '')[:40]
                if fb['rating'] == 'good':
                    good.append(title)
                else:
                    bad.append(title)

        if not good and not bad:
            return ''

        lines = ['\n[사용자 피드백 반영]']
        if good:
            lines.append(f'좋은 평가를 받은 분석 유형: {", ".join(good[:5])}')
            lines.append('→ 이런 스타일로 분석하세요.')
        if bad:
            lines.append(f'개선 요청된 분석 유형: {", ".join(bad[:5])}')
            lines.append('→ 이런 유형의 분석은 더 구체적이고 팩트 중심으로 개선하세요.')
        return '\n'.join(lines)

    def analyze(self, articles, incremental=False):
        """전체 흐름 분석 파이프라인
        incremental=True: 이전 브리핑 테마를 재활용하고 새 기사만 그룹핑
        """
        if not articles:
            return None

        prev_briefing = self._load_latest_briefing()

        # 증분 모드: 이전 브리핑 + 새 기사만 처리
        if incremental and prev_briefing and prev_briefing.get('themes'):
            return self._analyze_incremental(articles, prev_briefing)

        return self._analyze_full(articles, prev_briefing)

    def _analyze_incremental(self, new_articles, prev_briefing):
        """증분 분석: 테마 인덱스로 새 기사를 기존 테마에 매칭 (O(n) 수준)"""
        # 테마 인덱스 로드 (없으면 이전 브리핑에서 생성)
        if not self.theme_index.load():
            self.theme_index.register_themes(prev_briefing.get('themes', []), self._STOPWORDS)

        new_articles = self.theme_index.get_unclassified(new_articles)
        if not new_articles:
            logger.info("증분 분석: 신규 기사 없음")
            return None

        logger.info(f"증분 분석 시작: 새 기사 {len(new_articles)}건, 기존 테마 {len(self.theme_index._themes)}개")

        # 이전 테마의 기사들을 미리 매핑 (기존 기사 복구 용도)
        prev_article_map = {
            t.get('theme_id'): t.get('_articles', [])
            for t in prev_briefing.get('themes', [])
        }

        # 1. 새 기사를 기존 테마에 매칭 (엔티티 인덱스, O(n))
        matched, unmatched = self.theme_index.match_articles(new_articles, self._STOPWORDS)

        matched_count = sum(len(v) for v in matched.values())
        logger.info(f"매칭 결과: {matched_count}건 매칭, {len(unmatched)}건 미매칭")

        # 2. 이전 테마 업데이트
        # 이전 미분류 테마는 제거 (신규 미분류 테마로 교체)
        prev_themes = [t for t in prev_briefing.get('themes', []) if t.get('theme_id') != 'unclassified']
        refresh_ids = set()

        for tid, articles in matched.items():
            self.theme_index.update_theme_count(tid, len(articles))
            if len(articles) >= 3:
                refresh_ids.add(tid)

        # 3. 미매칭 기사가 3건 이상이면 그것끼리만 소규모 그룹핑
        new_analyzed = []
        if len(unmatched) >= 3:
            new_themes = self._group_by_theme(unmatched)
            candidates = [t for t in new_themes if len(t['articles']) >= 3]
            for t in candidates:
                sources = set(a.get('source', '') for a in t['articles'])
                cat_weights = [self.CATEGORY_WEIGHT.get(a.get('category', ''), 2) for a in t['articles']]
                avg_weight = sum(cat_weights) / len(cat_weights) if cat_weights else 2
                t['_score'] = len(t['articles']) * avg_weight + len(sources) * 3
            candidates.sort(key=lambda t: t['_score'], reverse=True)

            for i, theme in enumerate(candidates[:5]):
                # 신규 테마가 기존 테마와 중복인지 사전 확인
                dup_id = self._is_duplicate_of_existing(theme, prev_themes)
                if dup_id:
                    matched[dup_id].extend(theme['articles'])
                    self.theme_index.update_theme_count(dup_id, len(theme['articles']))
                    logger.info(f"신규 테마 → 기존 테마 흡수: {theme['title'][:30]}")
                    continue

                logger.info(f"새 테마 분석 [{i+1}/{min(5,len(candidates))}]: {theme['title'][:40]} ({len(theme['articles'])}건)")
                result = self._analyze_and_attach(theme, prev_briefing)
                if result:
                    result['article_count'] = len(theme['articles'])
                    result['article_sources'] = list(set(a.get('source', '') for a in theme['articles']))
                    result['theme_id'] = theme['theme_id']
                    new_analyzed.append(result)

            # candidates가 비었거나 불충분하면 미분류 테마로 통합
            if len(candidates) == 0 or len(new_analyzed) == 0:
                unclassified_theme = {
                    'theme_id': 'unclassified',
                    'title': '분류되지 않은 기사',
                    'keywords': ['기타'],
                    '_articles': unmatched[:20],
                    'article_count': len(unmatched),
                    'article_sources': list(set(a.get('source', '') for a in unmatched)),
                    'importance': 0,
                }
                new_analyzed.append(unclassified_theme)
                logger.info(f"미분류 테마 생성: {len(unmatched)}건 기사")

        # 미분류 테마: 3건 미만 미매칭 기사를 저장 (내부 추적용)
        elif len(unmatched) > 0 and len(unmatched) < 3:
            unclassified_theme = {
                'theme_id': 'unclassified',
                'title': '분류되지 않은 기사',
                'keywords': ['기타'],
                '_articles': unmatched[:20],
                'article_count': len(unmatched),
                'article_sources': list(set(a.get('source', '') for a in unmatched)),
                'importance': 0,
            }
            new_analyzed.append(unclassified_theme)
            logger.info(f"미분류 테마 생성: {len(unmatched)}건 기사")

        # 4. 기사 많이 추가된 기존 테마 재분석 (상위 3개)
        refreshed_count = 0
        for tid in list(refresh_ids)[:3]:
            pt = next((t for t in prev_themes if t.get('theme_id') == tid), None)
            if not pt:
                continue
            matched_arts = matched.get(tid, [])
            # 이전 기사와 새로운 기사를 함께 포함하여 분석
            prev_articles = prev_article_map.get(tid, [])
            combined_articles = prev_articles + matched_arts
            fake_theme = {
                'title': pt.get('title', ''),
                'articles': combined_articles[:15],  # LLM 입력 상한
                'keywords': pt.get('keywords', []),
                'theme_id': tid,
            }
            logger.info(f"테마 갱신: {pt.get('title','')[:30]} (+{len(matched_arts)}건)")
            result = self._analyze_and_attach(fake_theme, prev_briefing)
            if result:
                # _articles를 combined로 유지 (최대 20개)
                result['_articles'] = combined_articles[:20]
                result['article_count'] = pt.get('article_count', 0) + len(matched_arts)
                result['article_sources'] = pt.get('article_sources', [])
                result['theme_id'] = tid
                # 기존 테마 교체
                for idx, t in enumerate(prev_themes):
                    if t.get('theme_id') == tid:
                        prev_themes[idx] = result
                        refreshed_count += 1
                        break

        # matched 테마들의 _articles도 prev_article_map으로 업데이트
        for pt in prev_themes:
            theme_id = pt.get('theme_id')
            if theme_id in prev_article_map:
                # prev_article_map의 기사 + matched 기사 병합
                prev_arts = prev_article_map[theme_id]
                matched_arts = matched.get(theme_id, [])
                if matched_arts:
                    # 중복 제거하며 합치기
                    all_arts = prev_arts + matched_arts
                    seen = set()
                    unique = []
                    for art in all_arts:
                        aid = art.get('id', '') or art.get('url', '')
                        if aid and aid not in seen:
                            seen.add(aid)
                            unique.append(art)
                    pt['_articles'] = unique[:20]
                    # article_count도 실제 추가된 수만큼 업데이트
                    pt['article_count'] = pt.get('article_count', 0) + len(matched_arts)
                else:
                    pt['_articles'] = prev_arts
            elif not pt.get('_articles'):
                pt['_articles'] = []

        analyzed_themes = prev_themes + new_analyzed

        # 테마 인덱스에 새 테마 등록 + 저장
        self.theme_index.register_themes(new_analyzed, self._STOPWORDS)
        self.theme_index.save()

        logger.info(f"증분 분석: 유지 {len(prev_themes)}개 + 신규 {len(new_analyzed)}개 + 갱신 {refreshed_count}개")

        if not analyzed_themes:
            logger.warning("분석된 테마 없음")
            return None

        # 5. 분석 후 중복 테마 병합
        analyzed_themes = self._merge_analyzed_themes(analyzed_themes)

        # 6. 전체 종합 브리핑
        logger.info("전체 종합 브리핑 생성 중...")
        overall = self._generate_overall_briefing(analyzed_themes)

        analyzed_themes.sort(key=lambda t: (t.get('importance', 0), t.get('article_count', 0)), reverse=True)
        analyzed_themes = analyzed_themes[:15]

        # 최종 저장 전 _articles 손실 방지
        for theme in analyzed_themes:
            if not theme.get('_articles'):
                theme['_articles'] = []

        # article_count는 실제 저장된 _articles 합계로 다시 센다
        total_articles = sum(len(t.get('_articles', [])) for t in analyzed_themes)

        briefing = {
            'generated_at': datetime.now().isoformat(),
            'article_count': total_articles,
            'theme_count': len(analyzed_themes),
            'themes': analyzed_themes,
            'overall': overall,
            'raw_theme_count': len(new_analyzed),
            'mode': 'incremental',
        }

        self.store.save_briefing(briefing)
        logger.info(f"증분 분석 완료: {len(analyzed_themes)}개 테마")
        return briefing

    def _analyze_full(self, articles, prev_briefing):
        """전체 분석 (첫 회차 또는 리셋 시)"""
        logger.info(f"전체 분석 시작: {len(articles)}건")

        # 1. 테마별 그룹핑 (LLM 없이)
        themes = self._group_by_theme(articles)
        logger.info(f"테마 {len(themes)}개 도출")

        # 2. 키워드 겹침 기반 유사 테마 병합
        themes = self._merge_similar_themes(themes)
        logger.info(f"테마 병합 후: {len(themes)}개")

        # 3. 주요 테마별 Ollama 흐름 분석 (상위 15개)
        # 카테고리 가중치 × 기사수 + 소스 다양성으로 점수 산정
        for t in themes:
            sources = set(a.get('source', '') for a in t['articles'])
            cat_weights = [self.CATEGORY_WEIGHT.get(a.get('category', ''), 2) for a in t['articles']]
            avg_weight = sum(cat_weights) / len(cat_weights) if cat_weights else 2
            t['_score'] = len(t['articles']) * avg_weight + len(sources) * 3
        top_themes = sorted(themes, key=lambda t: t['_score'], reverse=True)[:15]
        analyzed_themes = []
        for i, theme in enumerate(top_themes):
            if len(theme['articles']) < 2:
                continue
            logger.info(f"테마 분석 [{i+1}/{len(top_themes)}]: {theme['title'][:40]} ({len(theme['articles'])}건)")
            result = self._analyze_and_attach(theme, prev_briefing)
            if result:
                result['article_count'] = len(theme['articles'])
                result['article_sources'] = list(set(
                    a.get('source', '') for a in theme['articles']
                ))
                result['theme_id'] = theme['theme_id']
                analyzed_themes.append(result)

        if not analyzed_themes:
            logger.warning("분석된 테마 없음")
            return None

        # 4. 분석 후 중복 테마 병합
        analyzed_themes = self._merge_analyzed_themes(analyzed_themes)

        # 5. 자기 평가 + 불량 테마 재생성
        analyzed_themes = self._self_evaluate_and_retry(analyzed_themes, top_themes, prev_briefing)

        # 6. 전체 종합 브리핑
        logger.info("전체 종합 브리핑 생성 중...")
        overall = self._generate_overall_briefing(analyzed_themes)

        # 최종 저장 전 _articles 손실 방지
        for theme in analyzed_themes:
            if not theme.get('_articles'):
                theme['_articles'] = []

        # article_count는 실제 저장된 _articles 합계로 다시 센다
        total_articles = sum(len(t.get('_articles', [])) for t in analyzed_themes)

        briefing = {
            'generated_at': datetime.now().isoformat(),
            'article_count': total_articles,
            'theme_count': len(analyzed_themes),
            'themes': analyzed_themes,
            'overall': overall,
            'raw_theme_count': len(themes),
        }

        # 7. 테마 인덱스 저장 (증분 분석용)
        self.theme_index.load()  # 오늘자로 초기화

        # top_themes에서 원본 articles 매핑
        top_themes_map = {t.get('theme_id'): t for t in top_themes}

        for t in analyzed_themes:
            # _articles가 없으면 복구 시도
            if not t.get('_articles'):
                # 먼저 top_themes에서 원본 articles 찾기
                original = top_themes_map.get(t.get('theme_id'))
                if original and original.get('articles'):
                    t['_articles'] = original.get('articles', [])[:20]
                else:
                    # 원본이 없으면 키워드 기반으로 복구
                    t['_articles'] = [a for a in articles if any(
                        kw.lower() in a.get('title', '').lower() for kw in t.get('keywords', [])[:3]
                    )][:20]
        self.theme_index.register_themes(analyzed_themes, self._STOPWORDS)
        # 전체 분석한 기사 ID 등록
        for a in articles:
            self.theme_index._article_ids.add(self.theme_index._article_id(a))
        self.theme_index.save()
        logger.info(f"테마 인덱스 저장: {len(self.theme_index._themes)}개 테마")

        self.store.save_briefing(briefing)
        logger.info(f"흐름 분석 완료: {len(analyzed_themes)}개 테마")
        return briefing

    # 불용어 (일반적이고 주제 구분에 도움 안 되는 단어)
    _STOPWORDS = {
        # 한글 - 동사/조사/부사
        '있다', '없다', '하다', '되다', '이다', '것이다', '수', '등', '및', '위해',
        '대한', '통해', '에서', '으로', '에게', '까지', '부터', '에서는', '으로는',
        '관련', '올해', '지난해', '이번', '최근', '현재', '오늘', '내일', '어제',
        # 한글 - 뉴스 일반
        '종합', '속보', '단독', '포토', '영상', '뉴스', '기자', '특파원', '사진',
        '발생', '사망', '부상', '피해', '사건', '사고', '조사', '수사', '확인',
        '발표', '공개', '논란', '의혹', '혐의', '주장', '지적', '비판', '우려',
        '대응', '대책', '방안', '추진', '검토', '결정', '합의', '논의', '회의',
        '시작', '진행', '예정', '계획', '전망', '가능', '상황', '문제', '결과',
        '이상', '이하', '이후', '이전', '약', '만', '억', '조', '원',
        '지역', '전국', '서울', '국내', '국외', '세계', '글로벌',
        '경우', '위험', '영향', '변화', '증가', '감소', '상승', '하락',
        '필요', '중요', '심각', '긴급', '전면', '전체', '일부', '추가',
        '오전', '오후', '새벽', '밤', '낮', '시간', '분', '초',
        '월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일',
        '내일', '모레', '주말', '평일', '당일', '오늘날',
        '1월', '2월', '3월', '4월', '5월', '6월',
        '7월', '8월', '9월', '10월', '11월', '12월',
        # 영어 - 기본
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'can', 'shall', 'must', 'to', 'of', 'in',
        'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'about',
        'after', 'before', 'between', 'under', 'and', 'but', 'or', 'not',
        'no', 'so', 'if', 'than', 'too', 'very', 'just', 'that', 'this',
        'it', 'its', 'his', 'her', 'their', 'our', 'my', 'your', 'who',
        'which', 'what', 'how', 'says', 'said', 'new', 'also', 'more',
        'over', 'after', 'like', 'get', 'back', 'out', 'up', 'one', 'two',
        # 영어 - 뉴스 일반
        'killed', 'dead', 'injured', 'attack', 'fire', 'found', 'report',
        'people', 'first', 'last', 'year', 'years', 'day', 'days', 'time',
        'make', 'made', 'take', 'come', 'going', 'want', 'need', 'know',
        'think', 'tell', 'show', 'look', 'give', 'most', 'some', 'many',
        'much', 'well', 'way', 'use', 'work', 'world', 'three', 'four',
        'five', 'still', 'been', 'only', 'then', 'them', 'when', 'where',
        'here', 'there', 'down', 'long', 'high', 'right', 'left', 'big',
        'say', 'says', 'told', 'warns', 'reveals', 'claims', 'amid',
    }

    def _group_by_theme(self, articles):
        """엔티티 그래프 기반 기사 클러스터링"""
        if len(articles) < 2:
            return self._build_groups(articles, [[0]])

        # 1. 각 기사에서 엔티티 추출 (제목만 사용)
        article_entities = []
        for a in articles:
            title = a.get('title', '')
            entities = self._extract_entities(title)
            article_entities.append(entities)

        # 2. Union-Find로 엔티티를 공유하는 기사 연결
        parent = list(range(len(articles)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        entity_to_articles = defaultdict(list)
        for idx, entities in enumerate(article_entities):
            for e in entities:
                entity_to_articles[e].append(idx)

        # 같은 엔티티를 공유하는 기사쌍 연결
        # 조건: 공유 엔티티 2개 이상 AND Jaccard 유사도 0.25 이상
        for idx_i in range(len(articles)):
            if not article_entities[idx_i]:
                continue
            for idx_j in range(idx_i + 1, len(articles)):
                if not article_entities[idx_j]:
                    continue
                shared = article_entities[idx_i] & article_entities[idx_j]
                if len(shared) < 2:
                    continue
                union_size = len(article_entities[idx_i] | article_entities[idx_j])
                jaccard = len(shared) / union_size if union_size else 0
                if jaccard >= 0.25:
                    union(idx_i, idx_j)

        # 3. 연결 컴포넌트 추출
        clusters = defaultdict(list)
        for idx in range(len(articles)):
            clusters[find(idx)].append(idx)

        groups = self._build_groups(articles, clusters.values())
        logger.info(f"엔티티 그래프 클러스터링: {len(articles)}건 → {len(groups)}개 테마")
        return groups

    def _extract_entities(self, text):
        """제목에서 핵심 엔티티 추출"""
        entities = set()
        # 한글 2~5자 명사 (인물, 지명, 기업, 핵심어)
        for w in re.findall(r'[가-힣]{2,5}', text):
            if w not in self._STOPWORDS:
                entities.add(w.lower())
        # 영어 3자+ 단어
        for w in re.findall(r'[a-zA-Z]{3,}', text):
            if w.lower() not in self._STOPWORDS:
                entities.add(w.lower())
        return entities

    def _merge_similar_themes(self, themes):
        """LLM을 사용하여 같은 사건/이슈의 테마끼리 병합"""
        if len(themes) < 2:
            return themes

        # 기사 2건 이상인 테마만 병합 대상
        big = [t for t in themes if len(t['articles']) >= 2]
        small = [t for t in themes if len(t['articles']) < 2]

        if len(big) < 2:
            return themes

        # 점수 기준 상위 30개만 LLM 병합 검토
        for t in big:
            sources = set(a.get('source', '') for a in t['articles'])
            cat_weights = [self.CATEGORY_WEIGHT.get(a.get('category', ''), 2) for a in t['articles']]
            avg_weight = sum(cat_weights) / len(cat_weights) if cat_weights else 2
            t['_pre_score'] = len(t['articles']) * avg_weight + len(sources) * 3
        big.sort(key=lambda t: t['_pre_score'], reverse=True)
        candidates = big[:30]
        rest = big[30:]

        # LLM에게 테마 목록을 보내서 그룹핑 요청
        themes_list = '\n'.join(
            f"{i+1}. \"{c['title'][:60]}\" ({len(c['articles'])}건) 키워드: {', '.join(c.get('keywords', [])[:5])}"
            for i, c in enumerate(candidates)
        )

        prompt = THEME_MERGE_PROMPT.format(themes_list=themes_list)
        try:
            result = self.client.generate_json(prompt, system="테마 그룹핑 전문가. 반드시 JSON 배열만 출력하세요.")
            if not isinstance(result, list):
                logger.warning("LLM 테마 병합 결과가 배열이 아님, 병합 스킵")
                return big + small

            # LLM 결과로 병합
            merged = []
            used = set()
            for group in result:
                if not isinstance(group, list):
                    continue
                # LLM은 1부터 번호를 매긴다
                indices = [g - 1 for g in group if isinstance(g, int) and 1 <= g <= len(candidates)]
                indices = [i for i in indices if i not in used]
                if not indices:
                    continue
                for i in indices:
                    used.add(i)

                if len(indices) == 1:
                    merged.append(candidates[indices[0]])
                else:
                    all_articles = []
                    all_keywords = []
                    for idx in indices:
                        all_articles.extend(candidates[idx]['articles'])
                        all_keywords.extend(candidates[idx].get('keywords', []))
                    rep = max(indices, key=lambda idx: len(candidates[idx]['articles']))
                    kw_counts = Counter(all_keywords)
                    merged.append({
                        'theme_id': candidates[rep]['theme_id'],
                        'title': candidates[rep]['title'],
                        'articles': all_articles,
                        'keywords': [kw for kw, _ in kw_counts.most_common(10)],
                    })
                    names = [candidates[i]['title'][:25] for i in indices]
                    logger.info(f"LLM 테마 병합: {len(indices)}개 → '{candidates[rep]['title'][:30]}' ({len(all_articles)}건)")

            # LLM이 빠뜨린 테마 추가
            for i in range(len(candidates)):
                if i not in used:
                    merged.append(candidates[i])

            return merged + rest + small

        except Exception as e:
            logger.error(f"LLM 테마 병합 실패: {e}, 병합 없이 진행")
            return big + small

    def _build_groups(self, articles, cluster_indices):
        """클러스터 인덱스를 테마 그룹으로 변환"""
        groups = []
        for indices in cluster_indices:
            cluster_articles = [articles[i] for i in indices]
            titles = [a.get('title', '') for a in cluster_articles]

            # 대표 제목: 가장 많은 엔티티를 포함한 제목
            rep_title = max(titles, key=lambda t: len(self._extract_entities(t)))

            # 키워드: 클러스터 내 모든 제목에서 빈도순
            all_entities = []
            for t in titles:
                all_entities.extend(self._extract_entities(t))
            kw_counts = Counter(all_entities)
            keywords = [kw for kw, _ in kw_counts.most_common(10)]

            groups.append({
                'theme_id': f"theme_{hashlib.md5(rep_title.encode()).hexdigest()[:8]}",
                'title': rep_title,
                'articles': cluster_articles,
                'keywords': keywords,
            })

        return groups

    def _analyze_and_attach(self, theme, prev_briefing):
        """_analyze_theme() 결과에 _articles를 바로 붙인다. 뒤에서 누락되는 걸 막기 위함."""
        result = self._analyze_theme(theme, prev_briefing)
        if result:
            result['_articles'] = theme.get('articles', [])[:20]
        return result

    def _analyze_theme(self, theme, prev_briefing):
        """테마 하나에 대한 흐름 분석 (mini-MoE: 카테고리별 전문가 라우팅)"""
        articles_text = '\n'.join(
            f"- [{a.get('source', '')}] {a['title']}"
            + (f"\n  {a.get('content_snippet', '')[:100]}" if a.get('content_snippet') else '')
            for a in theme['articles'][:10]
        )

        # dominant 카테고리는 RAG 필터와 전문가 라우팅에 같이 쓴다
        cat_counts = Counter(a.get('category', '') for a in theme.get('articles', []) if a.get('category'))
        dom_cat = cat_counts.most_common(1)[0][0] if cat_counts else ''
        # 룰 + 임베딩 하이브리드 라우터 (실패 시 룰로 폴백)
        route_meta = None
        try:
            route_meta = get_expert_smart(
                dom_cat, theme.get('title', ''), articles=theme.get('articles', []),
                top_k=2, return_meta=True,
            )
            expert_id = route_meta['primary']
            route_info = f"{route_meta['used']}({route_meta['rule']}→{expert_id})"
        except Exception as e:
            logger.warning(f"스마트 라우팅 실패, 룰 fallback: {e}")
            expert_id = get_expert(dom_cat)
            route_info = f"rule_fallback({expert_id})"

        # 벡터DB에서 관련 과거 기사 검색 (테마 카테고리로 필터링)
        related_context = ''
        if self.vector:
            try:
                keywords = theme.get('keywords', [])
                search_cats = None
                if dom_cat and dom_cat != 'general':
                    search_cats = [dom_cat, 'general']
                elif dom_cat:
                    search_cats = [dom_cat]
                related = self.vector.search_related(
                    theme['title'], keywords, n_results=10, category=search_cats
                )
                # 현재 테마 기사 ID 제외
                current_ids = set(a.get('id', '') for a in theme['articles'])
                related = [r for r in related if r['id'] not in current_ids]
                if related:
                    related_lines = '\n'.join(
                        f"- [{r['date']}] [{r['source']}] {r['title']}"
                        for r in related[:7]
                    )
                    related_context = f"\n[관련 과거 기사]\n{related_lines}\n"
            except Exception as e:
                logger.error(f"벡터 검색 실패: {e}")

        # 이전 브리핑 히스토리 컨텍스트
        history_context = ''
        if prev_briefing:
            prev_themes = prev_briefing.get('themes', [])
            for pt in prev_themes:
                pt_kw = set(k.lower() for k in pt.get('keywords', []))
                theme_kw = set(k.lower() for k in theme.get('keywords', []))
                if len(pt_kw & theme_kw) >= 2:
                    history_context = f"""
[이전 분석 참고 ({prev_briefing.get('generated_at', '')[:10]})]
제목: {pt.get('title', '')}
배경: {pt.get('background', '')}
당시 상황: {pt.get('current_situation', '')}
당시 전망: {pt.get('prediction', '')}

위 이전 분석을 참고하여 현재 상황이 어떻게 변화했는지도 포함해서 분석해주세요.
"""
                    break

        if not history_context:
            history_context = """(이 주제에 대한 이전 분석 히스토리가 아직 없습니다.
기사 내용을 기반으로 배경을 작성해주세요.)"""

        prompt = THEME_ANALYSIS_PROMPT.format(
            theme_title=theme['title'][:50],
            articles_text=articles_text + related_context,
            history_context=history_context,
        )

        if not hasattr(self, '_feedback_cache'):
            self._feedback_cache = self._load_feedback_context()

        # 경계 케이스에서만 Top-2 동시 호출 (MOE_TOP2=1일 때)
        if Config.MOE_TOP2 and route_meta:
            top2 = route_meta.get('top2', [])
            scores = route_meta.get('scores', {})
            if len(top2) >= 2 and top2[0] != top2[1]:
                score_diff = abs(scores.get(top2[0], 0) - scores.get(top2[1], 0))
                if score_diff < Config.MOE_TOP2_MARGIN:
                    return self._analyze_theme_top2(prompt, theme, top2[0], top2[1], route_info)

        system = build_expert_system(SYSTEM_PROMPT, expert_id, self._feedback_cache or '')
        logger.info(f"[전문가] {expert_id} | {route_info} | {theme.get('title', '')[:40]}")
        return self.client.generate_json(prompt, system=system)

    def _analyze_theme_top2(self, prompt, theme, expert_a, expert_b, route_info):
        """Top-2 전문가가 동시에 분석하고 결과를 병합 (MOE_TOP2=1일 때만)"""
        sys_a = build_expert_system(SYSTEM_PROMPT, expert_a, self._feedback_cache or '')
        sys_b = build_expert_system(SYSTEM_PROMPT, expert_b, self._feedback_cache or '')
        result_a = self.client.generate_json(prompt, system=sys_a)
        result_b = self.client.generate_json(prompt, system=sys_b)
        merged = self._merge_expert_results(result_a, result_b)
        logger.info(f"[전문가] TOP-2 {expert_a}+{expert_b} | {route_info} | {theme.get('title', '')[:40]}")
        return merged

    def _merge_expert_results(self, a, b):
        """두 전문가 결과 병합. 서술 필드는 긴 쪽, key_facts/keywords는 합집합."""
        if not a:
            return b
        if not b:
            return a

        def longer(x, y):
            return x if len(str(x or '')) >= len(str(y or '')) else y

        # key_facts / keywords 합집합 (순서 유지)
        facts = list(dict.fromkeys((a.get('key_facts') or []) + (b.get('key_facts') or [])))[:6]
        kws = list(dict.fromkeys((a.get('keywords') or []) + (b.get('keywords') or [])))[:6]

        return {
            'title': a.get('title') or b.get('title') or '',
            'background': longer(a.get('background', ''), b.get('background', '')),
            'current_situation': longer(a.get('current_situation', ''), b.get('current_situation', '')),
            'flow_analysis': longer(a.get('flow_analysis', ''), b.get('flow_analysis', '')),
            'prediction': longer(a.get('prediction', ''), b.get('prediction', '')),
            'korea_impact': longer(a.get('korea_impact', ''), b.get('korea_impact', '')),
            'importance': max(a.get('importance', 0) or 0, b.get('importance', 0) or 0),
            'key_facts': facts,
            'keywords': kws,
        }

    def _merge_analyzed_themes(self, themes):
        """분석 완료된 테마들 중 중복/유사 테마를 LLM으로 병합"""
        if len(themes) < 2:
            return themes

        import json as _json
        merge_items = []
        for i, t in enumerate(themes):
            merge_items.append(
                f"{i+1}. \"{t.get('title','')}\" ({t.get('article_count',0)}건)\n"
                f"   현황: {t.get('current_situation','')[:100]}\n"
                f"   키워드: {', '.join(t.get('keywords',[])[:5])}"
            )

        prompt = f"""다음은 분석 완료된 뉴스 테마 목록입니다.
같은 사건의 직접적 인과관계가 있는 테마끼리만 보수적으로 묶어주세요.

{chr(10).join(merge_items)}

[병합 기준 — 엄격하게]
✅ 같은 사건/사고의 직접 인과관계가 있을 때만 묶으세요.
   - "이란 미사일 발사" + "유가 급등" + "코스피 하락" (직접 인과)
   - "트럼프 발표 X" + "Y측 반응" (직접 반응)
   - "한 사건의 원인 → 결과 → 후속 조치"

❌ 카테고리만 같은 테마는 절대 묶지 마세요:
   - "美 노동시장 지표" + "한국 유조선 입항" + "EU 자동차 관세" → ❌ 모두 미국 경제이지만 별개 사건
   - "김관영 무혐의" + "강북구청장 선거구 지정" → ❌ 모두 정치이지만 별개
   - "BTS 콘서트" + "오늘 날씨" → ❌ 같은 날이지만 무관

❌ 단어가 겹친다고 묶지 마세요. 인과관계가 있어야 합니다.

⚠️ 의심스러우면 무조건 분리하세요. 잘못 묶는 것보다 분리된 게 낫습니다.
⚠️ 모든 테마 번호가 결과에 포함되어야 합니다.

JSON 배열로 출력 예시: [[1, 5], [2], [3], [4]]"""

        try:
            result = self.client.generate_json(prompt, system="테마 중복 검출 전문가. JSON 배열만 출력하세요.")
            if not isinstance(result, list):
                return themes

            merged = []
            used = set()
            for group in result:
                if not isinstance(group, list):
                    continue
                indices = [g - 1 for g in group if isinstance(g, int) and 1 <= g <= len(themes)]
                indices = [i for i in indices if i not in used]
                if not indices:
                    continue
                for i in indices:
                    used.add(i)
                if len(indices) == 1:
                    merged.append(themes[indices[0]])
                else:
                    # 기사 수 가장 많은 테마를 대표로
                    rep_idx = max(indices, key=lambda i: themes[i].get('article_count', 0))
                    rep = dict(themes[rep_idx])
                    total_articles = 0
                    all_sources = set()
                    all_articles = []
                    seen = set()
                    for idx in indices:
                        total_articles += themes[idx].get('article_count', 0)
                        all_sources.update(themes[idx].get('article_sources', []))
                        for art in themes[idx].get('_articles', []):
                            aid = art.get('id', '') or art.get('url', '')
                            if aid and aid not in seen:
                                seen.add(aid)
                                all_articles.append(art)

                    # 병합된 _articles로 LLM에게 재분석 요청 (단순 concat 금지)
                    re_input = {
                        'title': rep.get('title', ''),
                        'articles': all_articles[:10],
                        'keywords': rep.get('keywords', []),
                        'theme_id': rep.get('theme_id', ''),
                    }
                    re_result = self._analyze_theme(re_input, prev_briefing=None)
                    if re_result:
                        re_result['theme_id'] = rep.get('theme_id', '')
                        re_result['article_count'] = total_articles
                        re_result['article_sources'] = list(all_sources)
                        re_result['_articles'] = all_articles[:20]
                        merged.append(re_result)
                    else:
                        # 재분석 실패 시 대표 테마만 남긴다. 그냥 이어 붙이면 다른 사건 내용이 섞임
                        rep['article_count'] = total_articles
                        rep['article_sources'] = list(all_sources)
                        rep['_articles'] = all_articles[:20]
                        merged.append(rep)
                    titles = [themes[i].get('title', '')[:25] for i in indices]
                    logger.info(f"분석 후 병합 → 재분석: {' + '.join(titles)} → '{rep.get('title','')[:30]}' ({total_articles}건)")

            # 누락된 테마 추가
            for i in range(len(themes)):
                if i not in used:
                    merged.append(themes[i])

            return merged
        except Exception as e:
            logger.error(f"분석 후 병합 실패: {e}")
            return themes

    def _generate_overall_briefing(self, themes):
        """전체 종합 브리핑 (실패 시 최대 2회 재시도, 그래도 실패 시 fallback)"""
        sorted_themes = sorted(themes, key=lambda x: x.get('importance', 0), reverse=True)[:10]
        themes_text = '\n\n'.join(
            f"[{t.get('title', '')}] (중요도: {t.get('importance', '?')}/10, 기사 {t.get('article_count', 0)}건)\n"
            f"현황: {t.get('current_situation', '')}\n"
            f"흐름: {t.get('flow_analysis', '')}\n"
            f"전망: {t.get('prediction', '')}"
            for t in sorted_themes
        )

        prompt = OVERALL_BRIEFING_PROMPT.format(
            datetime=datetime.now().strftime('%Y-%m-%d %H:%M'),
            themes_text=themes_text,
        )

        for attempt in range(3):
            result = self.client.generate_json(prompt, system=SYSTEM_PROMPT)
            if result and isinstance(result, dict) and result.get('headline'):
                return result
            logger.warning(f"종합 브리핑 생성 실패 (시도 {attempt + 1}/3)")

        # fallback: 테마 제목으로 간단히 구성
        logger.error("종합 브리핑 3회 실패, fallback 생성")
        top = sorted_themes[:3]
        titles = ', '.join(t.get('title', '') for t in top)
        return {
            'headline': top[0].get('title', '주요 뉴스') if top else '주요 뉴스',
            'executive_summary': f"주요 이슈: {titles}. 자세한 내용은 각 테마별 분석을 참고해 주세요.",
            'key_themes': [t.get('title', '') for t in top],
        }

    def _self_evaluate_and_retry(self, analyzed_themes, top_themes, prev_briefing):
        """자기 평가: 품질 낮은 테마를 감지하고 재생성"""
        import json as _json

        # 테마별 원본 기사 제목 매핑 (LLM에 사실 근거 제공)
        top_themes_map = {t['theme_id']: t for t in top_themes if 'theme_id' in t}

        eval_items = []
        source_lines = []
        for i, t in enumerate(analyzed_themes):
            eval_items.append({
                'index': i,
                'title': t.get('title', '')[:50],
                'current_situation': t.get('current_situation', '')[:200],
                'prediction': t.get('prediction', '')[:200],
                'key_facts': t.get('key_facts', [])[:3],
            })
            # 해당 테마의 원본 기사 제목 3개 추가
            tid = t.get('theme_id', '')
            arts = t.get('_articles', []) or top_themes_map.get(tid, {}).get('articles', [])
            titles = [a.get('title', '')[:80] for a in arts[:3] if a.get('title')]
            if titles:
                source_lines.append(f"[테마 {i}] {' / '.join(titles)}")

        prompt = SELF_EVAL_PROMPT.format(
            today=datetime.now().strftime('%Y-%m-%d'),
            source_titles='\n'.join(source_lines) if source_lines else '(원본 기사 정보 없음)',
            themes_json=_json.dumps(eval_items, ensure_ascii=False, indent=2),
        )
        eval_system = ("뉴스 서술 품질 검수 전문가. "
                       "당신의 학습 데이터는 오래되어 최신 인물/사건을 모를 수 있습니다. "
                       "기사 내용의 사실 여부는 절대 의심하지 말고, 한국어 서술 품질만 평가하세요. "
                       "JSON만 출력하세요.")
        eval_result = self.client.generate_json(prompt, system=eval_system)

        if not eval_result or not isinstance(eval_result, dict):
            logger.warning("자기 평가 실패, 원본 유지")
            return analyzed_themes

        overall_score = eval_result.get('overall_score', 10)
        evaluations = eval_result.get('evaluations', [])
        logger.info(f"자기 평가 완료: 전체 {overall_score}/10")

        # 불량 테마 찾기 (score 6 이하)
        retry_indices = []
        for ev in evaluations:
            idx = ev.get('theme_index', -1)
            score = ev.get('score', 10)
            issues = ev.get('issues', [])
            if 0 <= idx < len(analyzed_themes):
                analyzed_themes[idx]['_eval_score'] = score
                analyzed_themes[idx]['_eval_issues'] = issues
                if score <= 6:
                    retry_indices.append(idx)
                    logger.info(f"  불량 테마 [{idx}] {analyzed_themes[idx].get('title','')[:30]} "
                               f"(점수:{score}) 문제: {', '.join(issues)}")

        if not retry_indices:
            logger.info("자기 평가: 모든 테마 통과")
            return analyzed_themes

        # theme_id별 top_themes 원본
        theme_map = {t['theme_id']: t for t in top_themes if 'theme_id' in t}

        # 불량 테마 재생성 (최대 5개)
        retry_count = 0
        for idx in retry_indices[:5]:
            old = analyzed_themes[idx]
            theme_id = old.get('theme_id', '')
            original = theme_map.get(theme_id)
            if not original:
                continue

            issues_hint = ', '.join(old.get('_eval_issues', []))
            logger.info(f"  재생성 [{idx}]: {old.get('title','')[:30]} (문제: {issues_hint})")

            result = self._analyze_and_attach(original, prev_briefing)
            if result:
                result['article_count'] = old.get('article_count', 0)
                result['article_sources'] = old.get('article_sources', [])
                result['theme_id'] = theme_id
                # original에 없으면 기존 테마의 _articles 유지
                if not result.get('_articles'):
                    result['_articles'] = old.get('_articles', original.get('articles', []))[:20]
                result['_retried'] = True
                result['_prev_issues'] = old.get('_eval_issues', [])
                analyzed_themes[idx] = result
                retry_count += 1

        logger.info(f"자기 평가 재생성: {retry_count}/{len(retry_indices)}개 완료")
        return analyzed_themes

    def _load_latest_briefing(self):
        """가장 최근 브리핑 로드"""
        return self.store.load_latest_briefing()

    def _is_duplicate_of_existing(self, candidate, existing_themes):
        """신규 테마가 기존 테마와 중복인지 확인 (엔티티 기반)"""
        cand_entities = self._extract_entities(candidate.get('title', ''))
        for et in existing_themes:
            et_entities = self._extract_entities(et.get('title', ''))
            for kw in et.get('keywords', []):
                et_entities.update(self._extract_entities(kw))
            overlap = cand_entities & et_entities
            # 3개 이상 겹치면 중복으로 판단
            if len(overlap) >= 3:
                return et.get('theme_id')
        return None
