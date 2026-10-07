"""임베딩 기반 전문가 선택

각 전문가의 '대표 문구(prototype)'를 다국어 임베딩 모델로 인코딩하고,
테마 임베딩과의 cosine 유사도로 전문가를 선택한다.
"""
import logging
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = 'intfloat/multilingual-e5-small'

# 전문가별 대표 문구. 영문 기사도 들어오므로 한·영을 섞음
EXPERT_PROTOTYPES = {
    'stocks': [
        '코스피 코스닥 상승 하락 마감 거래량 외국인 기관 매수 매도',
        '종목 주가 시가총액 등락률 PER ROE 배당 실적 발표',
        '뉴욕증시 다우 나스닥 S&P500 사상최고 옵션만기 FOMC',
        '삼성전자 SK하이닉스 LG에너지솔루션 매수세 매도세 사이드카',
        'stock market shares rally sell-off equity Wall Street Nasdaq',
        '증권 시황 종가 호가 거래대금 ETF 공매도 신용잔고',
    ],
    'economy': [
        '한국은행 기준금리 인상 동결 통화정책 환율 원달러',
        '소비자물가 CPI 인플레이션 GDP 성장률 무역수지 수출',
        '반도체 자동차 조선 2차전지 산업 가동률 매출 영업이익',
        '부동산 분양 청약 전세 매매 거래량 미분양 분양가',
        'Federal Reserve interest rate inflation GDP trade deficit',
        '기재부 금감원 금융위 경제정책 추경 세수 재정',
    ],
    'tech': [
        '인공지능 AI 머신러닝 LLM 챗GPT 클로드 제미나이 라마',
        '엔비디아 H100 H200 반도체 GPU TPU 데이터센터',
        '오픈AI 앤트로픽 구글 메타 마이크로소프트 빅테크',
        '스타트업 시리즈A B 투자 유치 IPO 기업가치 유니콘',
        'AI artificial intelligence neural network GPU semiconductor chip',
        '플랫폼 SaaS 클라우드 AWS 애저 카카오 네이버 쿠팡',
    ],
    'politics': [
        '대통령 총리 장관 청와대 여당 야당 국민의힘 민주당',
        '국회 본회의 상임위 법안 표결 가결 부결 의석',
        '선거 출마 후보 유세 공약 투표율 당선 낙선 개표',
        '대통령실 외교 정상회담 한미 한중 한일 동맹',
        '탄핵 특검 검찰 수사 청문회 국정감사 발의',
        'president election parliament vote impeachment opposition party',
    ],
    'world': [
        '미국 중국 일본 러시아 우크라이나 이스라엘 이란 북한',
        '트럼프 바이든 시진핑 푸틴 젤렌스키 네타냐후 김정은',
        '전쟁 휴전 미사일 핵 제재 외교 정상회담 무역분쟁',
        'NATO UN EU OPEC G7 G20 ASEAN 정상회담',
        'war ceasefire missile nuclear sanctions diplomacy summit',
        '중동 우크라이나 대만해협 남중국해 인도태평양 분쟁지역',
    ],
    'society': [
        '노동 임금 파업 해고 근로시간 노조 노사 협약',
        '교육 학교 수능 입시 교사 학생 대학 정원',
        '복지 연금 의료 건강보험 출산 육아 청년 노인',
        '사건 사고 화재 폭발 추락 익사 음주운전 살인',
        '검찰 경찰 수사 기소 재판 판결 구속 영장',
        'labor union strike education welfare crime accident healthcare',
    ],
    'sports': [
        '야구 KBO MLB 이정후 김하성 류현진 박찬호',
        '축구 K리그 EPL 손흥민 이강인 김민재 황희찬',
        '농구 NBA 골프 PGA LPGA 테니스 그랜드슬램',
        '올림픽 아시안게임 월드컵 챔피언스리그 결승',
        '경기 승리 패배 무승부 득점 어시스트 우승',
        'baseball football soccer basketball Olympics championship match',
    ],
    'culture': [
        '영화 개봉 박스오피스 감독 배우 시나리오',
        '음악 앨범 콘서트 데뷔 컴백 빌보드 차트',
        '드라마 시청률 방송 OTT 넷플릭스 디즈니플러스',
        '책 출간 베스트셀러 작가 노벨문학상',
        '미술 전시 공연 뮤지컬 발레 오페라 갤러리',
        'movie film concert album drama bestseller exhibition culture',
    ],
    'general': [
        '종합 뉴스 사회 일반 이슈 화제',
        '특집 기획 시리즈 분석 기사',
        '날씨 기상 예보 미세먼지 폭염 한파',
        'general news society issue feature analysis',
    ],
}


class ExpertEmbedder:
    """전문가 프로토타입 임베딩을 관리하고 테마-전문가 유사도를 계산한다."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        logger.info(f"전문가 임베더 초기화: {EMBEDDING_MODEL}")
        self.model = SentenceTransformer(EMBEDDING_MODEL)
        self.expert_ids = list(EXPERT_PROTOTYPES.keys())
        # 전문가별 프로토타입 임베딩 평균 (대표 벡터 1개)
        self.proto_vectors = {}
        for eid, texts in EXPERT_PROTOTYPES.items():
            # e5 규약: 프로토타입은 passage:, 테마는 query:
            prefixed = [f"passage: {t}" for t in texts]
            embs = self.model.encode(prefixed, normalize_embeddings=True)
            mean_vec = embs.mean(axis=0)
            mean_vec = mean_vec / (np.linalg.norm(mean_vec) + 1e-9)
            self.proto_vectors[eid] = mean_vec
        # (N_experts, dim). 행렬곱 한 번으로 전체 점수 계산
        self.proto_matrix = np.vstack([self.proto_vectors[eid] for eid in self.expert_ids])
        self._initialized = True
        logger.info(f"전문가 프로토타입 임베딩 완료: {len(self.expert_ids)}명")

    def _embed_query(self, text):
        emb = self.model.encode([f"query: {text}"], normalize_embeddings=True)[0]
        return emb / (np.linalg.norm(emb) + 1e-9)

    def rank_experts(self, theme_title, articles=None, top_k=2):
        """테마와 가장 유사한 전문가 top_k명을 (expert_id, score)로 반환.
        articles가 있으면 title을 결합해 더 풍부한 컨텍스트로 비교한다.
        """
        text = (theme_title or '').strip()
        if articles:
            extras = ' '.join(a.get('title', '')[:80] for a in articles[:5])
            if extras:
                text = f"{text} {extras}"
        if not text:
            return [('general', 0.0)]

        q = self._embed_query(text)
        scores = self.proto_matrix @ q
        order = np.argsort(-scores)
        return [(self.expert_ids[i], float(scores[i])) for i in order[:top_k]]
