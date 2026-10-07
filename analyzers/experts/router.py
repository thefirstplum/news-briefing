"""전문가 라우터: 피드 category 룰을 기본으로 쓰고, 임베딩이 충분히 강하게
반대할 때만 뒤집는다. 룰 단독은 라벨이 부정확한 매체에서, 임베딩 단독은
라벨이 명확한 케이스에서 각각 오분류를 낸다.
"""

EXPERT_IDS = [
    'stocks',    # 주식/시황 (최우선 카테고리)
    'economy',   # 경제 (거시/산업/부동산 포함)
    'tech',      # IT/테크
    'politics',  # 정치
    'world',     # 세계
    'society',   # 사회
    'sports',    # 스포츠
    'culture',   # 문화
    'general',   # 종합 (fallback)
]

CATEGORY_TO_EXPERT = {
    'stocks':     'stocks',
    'economy':    'economy',
    'industry':   'economy',
    'realestate': 'economy',
    'tech':       'tech',
    'politics':   'politics',
    'world':      'world',
    'society':    'society',
    'sports':     'sports',
    'culture':    'culture',
    'general':    'general',
}


def get_expert(category):
    """카테고리 문자열을 전문가 ID로 변환.
    미지의 카테고리는 'general' 전문가로 fallback.
    """
    if not category:
        return 'general'
    return CATEGORY_TO_EXPERT.get(category, 'general')


# 룰 후보가 임베딩 1등보다 이만큼 이상 낮을 때만 임베딩 결과로 뒤집는다.
# 0.04에선 운영 로그상 override 0건(사실상 룰 전용)이라 0.025로 낮춤.
_OVERRIDE_MARGIN = 0.025

# 룰 라우팅을 신뢰하지 않을 카테고리 (애매한 라벨이라 임베딩에 우선권)
_LOW_CONFIDENCE_CATEGORIES = {'general', '', None}


def get_expert_smart(category, theme_title, articles=None, top_k=2, return_meta=False):
    """룰 + 임베딩 하이브리드 라우터.

    룰 전문가가 임베딩 top_k 안에 있으면 룰을 따르고, 밖에 있으면
    임베딩 1등과의 점수 차가 _OVERRIDE_MARGIN을 넘을 때만 뒤집는다.
    return_meta=True면 {primary, top2, rule, scores, used} dict를 반환.
    """
    from .embedder import ExpertEmbedder

    rule_expert = get_expert(category)
    embedder = ExpertEmbedder()
    ranked = embedder.rank_experts(theme_title, articles=articles, top_k=top_k)

    top_ids = [eid for eid, _ in ranked]
    top_scores = {eid: sc for eid, sc in ranked}
    emb_top1, emb_top1_score = ranked[0]

    if category in _LOW_CONFIDENCE_CATEGORIES:
        # general/빈 라벨이면 임베딩 따름
        primary = emb_top1
        used = 'embedding'
    elif rule_expert in top_ids:
        # 룰이 임베딩 상위에 포함되면 룰 신뢰
        primary = rule_expert
        used = 'rule'
    else:
        # 룰과 임베딩이 충돌: 점수 차이 확인
        rule_score = top_scores.get(rule_expert)
        if rule_score is None:
            # 룰 후보가 top_k에 없으니 전체 점수 다시 보기
            full = embedder.rank_experts(theme_title, articles=articles, top_k=len(embedder.expert_ids))
            rule_score = next((sc for eid, sc in full if eid == rule_expert), 0.0)
        if emb_top1_score - rule_score > _OVERRIDE_MARGIN:
            primary = emb_top1
            used = 'embedding_override'
        else:
            primary = rule_expert
            used = 'rule'

    if not return_meta:
        return primary

    return {
        'primary': primary,
        'top2': top_ids[:2],
        'rule': rule_expert,
        'scores': top_scores,
        'used': used,
    }
