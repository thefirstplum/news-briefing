"""테마 인덱스: 기존 테마를 저장하고 새 기사를 빠르게 매칭"""
import json
import os
import re
import hashlib
from datetime import datetime
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class ThemeIndex:
    """오늘의 테마 목록을 관리하고, 새 기사를 기존 테마에 매칭"""

    def __init__(self, store):
        self.store = store
        self._themes = {}  # theme_id -> theme_data
        self._entity_map = defaultdict(set)  # entity -> set(theme_ids)
        self._article_ids = set()  # 이미 분류된 기사 ID
        self._today = None

    def _index_path(self):
        base = self.store._get_storage_path()
        return os.path.join(base, 'index', 'theme_index.json')

    def load(self):
        """오늘자 테마 인덱스 로드"""
        today = datetime.now().strftime('%Y-%m-%d')
        path = self._index_path()
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('date') == today:
                self._today = today
                self._themes = data.get('themes', {})
                self._article_ids = set(data.get('article_ids', []))
                # 엔티티맵 재구성
                self._entity_map = defaultdict(set)
                for tid, t in self._themes.items():
                    for e in t.get('entities', []):
                        self._entity_map[e].add(tid)
                logger.info(f"테마 인덱스 로드: {len(self._themes)}개 테마, {len(self._article_ids)}건 분류됨")
                return True
        self._today = today
        self._themes = {}
        self._entity_map = defaultdict(set)
        self._article_ids = set()
        return False

    def save(self):
        """테마 인덱스 저장"""
        path = self._index_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            'date': self._today or datetime.now().strftime('%Y-%m-%d'),
            'themes': self._themes,
            'article_ids': list(self._article_ids),
            'updated_at': datetime.now().isoformat(),
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    def get_unclassified(self, articles):
        """이미 분류된 기사를 제외하고 새 기사만 반환"""
        new = [a for a in articles if self._article_id(a) not in self._article_ids]
        logger.info(f"기사 분류 현황: 전체 {len(articles)}건 중 신규 {len(new)}건")
        return new

    def match_articles(self, articles, stopwords):
        """새 기사들을 기존 테마에 매칭. 매칭 안 되는 기사는 unmatched로 반환"""
        matched = defaultdict(list)  # theme_id -> [articles]
        unmatched = []

        for a in articles:
            aid = self._article_id(a)
            if aid in self._article_ids:
                continue

            entities = self._extract_entities(a.get('title', ''), stopwords)
            best_theme = None
            best_score = 0

            # 엔티티맵으로 후보 테마 빠르게 찾기
            candidate_themes = defaultdict(int)
            for e in entities:
                for tid in self._entity_map.get(e, set()):
                    candidate_themes[tid] += 1

            for tid, overlap_count in candidate_themes.items():
                if overlap_count < 2:
                    continue
                theme_entities = set(self._themes[tid].get('entities', []))
                union_size = len(entities | theme_entities)
                jaccard = overlap_count / union_size if union_size else 0
                # 엔티티 3개 이상 겹치거나, 2개 겹치면서 Jaccard 0.25 이상
                if overlap_count >= 3 or (overlap_count >= 2 and jaccard >= 0.25):
                    if jaccard > best_score:
                        best_score = jaccard
                        best_theme = tid

            if best_theme:
                self._article_ids.add(aid)
                matched[best_theme].append(a)
            else:
                unmatched.append(a)

        return dict(matched), unmatched

    def register_themes(self, themes, stopwords):
        """분석 완료된 테마를 인덱스에 등록"""
        for t in themes:
            tid = t.get('theme_id', '')
            if not tid:
                continue

            # 기존 테마가 있으면 엔티티 확장
            existing = self._themes.get(tid, {})
            old_entities = set(existing.get('entities', []))

            # 제목 + 키워드에서 엔티티 추출
            title = t.get('title', '')
            keywords = t.get('keywords', [])
            entities = self._extract_entities(title, stopwords)
            for kw in keywords:
                entities.update(self._extract_entities(kw, stopwords))
            # 새 엔티티 우선, 최대 25개 제한
            combined = list(entities) + [e for e in old_entities if e not in entities]
            entities = set(combined[:25])

            self._themes[tid] = {
                'title': t.get('title', ''),
                'keywords': t.get('keywords', []),
                'entities': list(entities),
                'article_count': t.get('article_count', 0),
                'importance': t.get('importance', 0),
            }

            for e in entities:
                self._entity_map[e].add(tid)

            for a in t.get('_articles', []):
                self._article_ids.add(self._article_id(a))

    def update_theme_count(self, theme_id, added_count):
        if theme_id in self._themes:
            self._themes[theme_id]['article_count'] = \
                self._themes[theme_id].get('article_count', 0) + added_count

    def _article_id(self, article):
        url = article.get('url', '')
        title = article.get('title', '')
        key = url or title
        return hashlib.md5(key.encode('utf-8')).hexdigest()[:12]

    @staticmethod
    def _extract_entities(text, stopwords):
        entities = set()
        for w in re.findall(r'[가-힣]{2,5}', text):
            if w.lower() not in stopwords:
                entities.add(w.lower())
        for w in re.findall(r'[a-zA-Z]{3,}', text):
            if w.lower() not in stopwords:
                entities.add(w.lower())
        return entities
