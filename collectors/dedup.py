import json
import os
import hashlib
from difflib import SequenceMatcher
import logging

logger = logging.getLogger(__name__)


class DedupChecker:
    SIMILARITY_THRESHOLD = 0.85
    RECENT_TITLE_LIMIT = 5000  # 유사도 비교는 최근 5000건만

    def __init__(self, store):
        self.store = store
        self._hashes = set()
        self._titles = {}  # hash -> title
        self._recent_titles = []  # 최근 타이틀 (유사도 비교용)
        self._load_hashes()

    def _hash_path(self):
        base = self.store._get_storage_path()
        return os.path.join(base, 'index', 'dedup_hashes.json')

    def _load_hashes(self):
        path = self._hash_path()
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._hashes = set(data.get('url_hashes', []))
            self._titles = data.get('titles', {})
            # 최근 타이틀만 유사도 비교용으로 보관
            all_titles = list(self._titles.values())
            self._recent_titles = all_titles[-self.RECENT_TITLE_LIMIT:]
            logger.info(f"중복 해시 로드: {len(self._hashes)}건 (유사도 비교: 최근 {len(self._recent_titles)}건)")

    def _save_hashes(self):
        path = self._hash_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            'url_hashes': list(self._hashes),
            'titles': self._titles,
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    def _url_hash(self, url):
        return hashlib.md5(url.encode('utf-8')).hexdigest()

    def _title_hash(self, title):
        return hashlib.md5(title.strip().lower().encode('utf-8')).hexdigest()

    def is_duplicate(self, article):
        url = article.get('url', '')
        title = article.get('title', '')

        # URL 정확 매칭
        if url:
            uh = self._url_hash(url)
            if uh in self._hashes:
                return True

        # 제목 정확 매칭
        th = self._title_hash(title)
        if th in self._titles:
            return True

        # 제목 유사도 매칭 (최근 것만 비교)
        title_lower = title.lower()
        for existing_title in self._recent_titles:
            ratio = SequenceMatcher(None, title_lower, existing_title.lower()).ratio()
            if ratio >= self.SIMILARITY_THRESHOLD:
                return True

        return False

    def register(self, article):
        url = article.get('url', '')
        title = article.get('title', '')

        if url:
            self._hashes.add(self._url_hash(url))

        th = self._title_hash(title)
        self._titles[th] = title
        self._recent_titles.append(title)
        # 최근 리스트 크기 유지
        if len(self._recent_titles) > self.RECENT_TITLE_LIMIT:
            self._recent_titles = self._recent_titles[-self.RECENT_TITLE_LIMIT:]

    def filter_new(self, articles):
        new_articles = []
        for article in articles:
            if not self.is_duplicate(article):
                self.register(article)
                new_articles.append(article)
        self._save_hashes()
        logger.info(f"중복 제거: {len(articles)}건 -> {len(new_articles)}건 (신규)")
        return new_articles
