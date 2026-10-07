"""라우팅 정확도 채점: 골드셋 라벨 대비 룰 / 임베딩 / 하이브리드 비교.

사용법:
    python eval/score_routing.py eval/gold_labels.json

gold_labels.json 형식: {"<theme_id>": "<정답 expert_id>", ...}
'__ambiguous__' 라벨은 채점에서 제외한다.

표본은 4개 층에서 각 50건씩 뽑았으므로, 모집단 추정치는 층 가중치를 적용해 계산한다.
"""
import json
import sys
import collections

EXPERTS = ['stocks', 'economy', 'tech', 'politics', 'world',
           'society', 'sports', 'culture', 'general']

# 전문가 9종을 관점 그룹 6종으로 묶는다.
# 증권/경제, 정치/국제, 문화/스포츠는 사람이 라벨링할 때도 경계가 흔들리는 쌍이라,
# 그룹 단위 정확도를 주 지표로 쓰고 9분류 정확도는 참고로 함께 보고한다.
GROUP = {
    'stocks': '시장', 'economy': '시장',
    'politics': '정치외교', 'world': '정치외교',
    'society': '사회',
    'tech': '기술',
    'culture': '문화스포츠', 'sports': '문화스포츠',
    'general': '종합',
}


def load(labels_path, sample_path='eval/gold_sample.json'):
    sample = json.load(open(sample_path, encoding='utf-8'))
    labels = json.load(open(labels_path, encoding='utf-8'))
    rows, dropped = [], 0
    for o in sample:
        gold = labels.get(o['theme_id'])
        if not gold or gold == '__ambiguous__':
            dropped += 1
            continue
        rows.append({**o, 'gold': gold})
    return rows, dropped


def hit(r, field, grouped=False):
    if grouped:
        return GROUP[r[field]] == GROUP[r['gold']]
    return r[field] == r['gold']


def accuracy(rows, field, weighted=False, grouped=False):
    """weighted=True면 층 가중치로 모집단 정확도를 추정한다.
    grouped=True면 전문가 9종 대신 관점 그룹 6종으로 채점한다."""
    if not rows:
        return 0.0
    if not weighted:
        return sum(hit(r, field, grouped) for r in rows) / len(rows)
    num = sum(r['weight'] for r in rows if hit(r, field, grouped))
    den = sum(r['weight'] for r in rows)
    return num / den if den else 0.0


def per_stratum(rows, grouped=False):
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        for f in ('rule_pred', 'emb_pred', 'hybrid_pred'):
            out[r['stratum']][f].append(hit(r, f, grouped))
    return out


def confusion(rows, field):
    m = collections.Counter()
    for r in rows:
        m[(r['gold'], r[field])] += 1
    return m


def print_confusion(rows, field):
    m = confusion(rows, field)
    used = [e for e in EXPERTS
            if any(g == e or p == e for (g, p) in m)]
    w = max(len(e) for e in used) + 1
    print('      정답\\예측 ' + ' '.join(f'{e[:6]:>6}' for e in used))
    for g in used:
        line = ''.join(f'{m.get((g, p), 0):>7}' for p in used)
        tot = sum(v for (gg, _), v in m.items() if gg == g)
        hit = m.get((g, g), 0)
        rate = f'{100*hit/tot:5.1f}%' if tot else '    -'
        print(f'  {g:>{w}} |{line}   ({hit}/{tot} {rate})')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rows, dropped = load(sys.argv[1])
    n = len(rows)
    print('=' * 66)
    print(f'라우팅 정확도: 골드셋 {n}건 채점 (애매/미라벨 {dropped}건 제외)')
    print('=' * 66)

    preds = [('rule_pred', '룰 단독'), ('emb_pred', '임베딩 단독'), ('hybrid_pred', '하이브리드(현행)')]

    print('\n[관점 그룹 6종 기준, 주 지표]')
    print(f'  {"":16} {"표본":>8} {"모집단 추정":>12}')
    for f, name in preds:
        print(f'  {name:16} {100*accuracy(rows, f, grouped=True):7.1f}% {100*accuracy(rows, f, True, True):11.1f}%')
    gain_g = accuracy(rows, 'hybrid_pred', True, True) - accuracy(rows, 'rule_pred', True, True)
    print(f'  하이브리드 - 룰 단독: {100*gain_g:+.1f}%p')

    print('\n[전문가 9종 기준, 참고]')
    print(f'  {"":16} {"표본":>8} {"모집단 추정":>12}')
    for f, name in preds:
        print(f'  {name:16} {100*accuracy(rows, f):7.1f}% {100*accuracy(rows, f, True):11.1f}%')
    gain = accuracy(rows, 'hybrid_pred', True) - accuracy(rows, 'rule_pred', True)
    print(f'  하이브리드 - 룰 단독: {100*gain:+.1f}%p')

    strict = accuracy(rows, 'hybrid_pred', True)
    loose = accuracy(rows, 'hybrid_pred', True, True)
    print(f'\n  두 지표의 차이 {100*(loose-strict):.1f}%p = 같은 그룹 안에서 갈린 분량')
    print('  (증권/경제, 정치/국제, 문화/스포츠는 사람이 라벨링할 때도 흔들리는 경계)')

    print('\n[층별 정확도, 그룹 기준]')
    ps = per_stratum(rows, grouped=True)
    print(f'  {"층":26} {"n":>4} {"룰":>7} {"임베딩":>7} {"하이브리드":>9}')
    for s in sorted(ps):
        d = ps[s]
        k = len(d['rule_pred'])
        f = lambda v: f'{100*sum(v)/len(v):5.1f}%' if v else '    -'
        print(f'  {s:26} {k:>4} {f(d["rule_pred"]):>7} {f(d["emb_pred"]):>7} {f(d["hybrid_pred"]):>9}')

    print('\n[override가 맞았나: S4_뒤집음 층, 그룹 기준]')
    ov = [r for r in rows if r['stratum'] == 'S4_뒤집음']
    if ov:
        right = sum(hit(r, 'hybrid_pred', True) for r in ov)
        would = sum(hit(r, 'rule_pred', True) for r in ov)
        print(f'  뒤집은 결과가 정답      {right}/{len(ov)} ({100*right/len(ov):.1f}%)')
        print(f'  안 뒤집었으면 정답      {would}/{len(ov)} ({100*would/len(ov):.1f}%)')
        print(f'  뒤집기 순이득 {right - would:+d}건')

    print('\n[혼동 행렬: 하이브리드]')
    print_confusion(rows, 'hybrid_pred')

    print('\n[오분류 사례: 그룹까지 틀린 것 (최대 15건)]')
    bad = [r for r in rows if not hit(r, 'hybrid_pred', True)]
    for r in bad[:15]:
        print(f"  정답 {r['gold']:9} 예측 {r['hybrid_pred']:9} [{r['used']:18}] {r['title'][:38]}")
    print(f'  총 오분류 {len(bad)}건')


if __name__ == '__main__':
    main()
