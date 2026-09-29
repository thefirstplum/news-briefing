"""역색인: 날짜·카테고리·키워드로 기사를 찾기 위한 인덱스 (웹 검색용)."""
import json
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class IndexManager:
    def __init__(self, store):
        self.store = store
        self._index = {
            'articles': {},      # id -> {path, title, source, category, date, keywords}
            'by_date': {},       # date -> [ids]
            'by_category': {},   # category -> [ids]
            'by_keyword': {},    # keyword -> [ids]
        }
        self._load_index()

    def _index_path(self):
        base = self.store._get_storage_path()
        return os.path.join(base, 'index', 'main_index.json')

    def _load_index(self):
        path = self._index_path()
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                self._index = json.load(f)
            logger.info(f"인덱스 로드: 기사 {len(self._index['articles'])}건")

    def _save_index(self):
        path = self._index_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self._index, f, ensure_ascii=False)
        os.replace(tmp, path)

    def add_article(self, article, path):
        aid = article['id']
        date = article['collected_at'][:10]
        category = article.get('category', 'general')
        keywords = []
        ai = article.get('ai_analysis')
        if ai:
            keywords = ai.get('keywords', [])

        self._index['articles'][aid] = {
            'path': path,
            'title': article['title'],
            'source': article.get('source', ''),
            'category': category,
            'date': date,
            'published_at': article.get('published_at', ''),
            'keywords': keywords,
            'importance': (article.get('ai_analysis') or {}).get('importance', 5),
        }

        self._index['by_date'].setdefault(date, [])
        if aid not in self._index['by_date'][date]:
            self._index['by_date'][date].append(aid)

        self._index['by_category'].setdefault(category, [])
        if aid not in self._index['by_category'][category]:
            self._index['by_category'][category].append(aid)

        for kw in keywords:
            self._index['by_keyword'].setdefault(kw, [])
            if aid not in self._index['by_keyword'][kw]:
                self._index['by_keyword'][kw].append(aid)

        self._save_index()

    def search(self, query, limit=50):
        query_lower = query.lower()
        results = []
        for aid, info in self._index['articles'].items():
            score = 0
            if query_lower in info['title'].lower():
                score += 10
            for kw in info.get('keywords', []):
                if query_lower in kw.lower():
                    score += 5
            if score > 0:
                results.append({**info, 'id': aid, 'score': score})
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:limit]

    def get_articles_by_date(self, date_str, category=None):
        ids = self._index['by_date'].get(date_str, [])
        results = []
        for aid in ids:
            info = self._index['articles'].get(aid)
            if info and (category is None or info['category'] == category):
                results.append({**info, 'id': aid})
        results.sort(key=lambda x: x.get('published_at', ''), reverse=True)
        return results

    def get_stats(self):
        return {
            'total_articles': len(self._index['articles']),
            'dates': len(self._index['by_date']),
            'categories': {k: len(v) for k, v in self._index['by_category'].items()},
        }
