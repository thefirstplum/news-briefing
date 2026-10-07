import json
import os
import hashlib
from difflib import SequenceMatcher
from config import Config
import logging

logger = logging.getLogger(__name__)


class DedupChecker:
    SIMILARITY_THRESHOLD = 0.85
    RECENT_TITLE_LIMIT = 5000  # 유사도 비교는 최근 5000건만

    def __init__(self, store):
        self.store = store
        self._hashes = set()
        self._title_hashes = set()      # 제목 완전일치 판정용
        self._recent_titles = []        # 유사도 비교용 (최근 RECENT_TITLE_LIMIT건)
        self._load_hashes()

    def _hash_path(self):
        base = self.store._get_storage_path()
        return os.path.join(base, 'index', 'dedup_hashes.json')

    def _load_hashes(self):
        path = self._hash_path()
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self._hashes = set(data.get('url_hashes', []))
        if 'titles' in data:
            # 구 형식: {해시: 제목}을 통째로 들고 있었다. 제목 문자열은 최근 것만 필요하므로
            # 해시 집합과 최근 제목으로 나눠 담는다. 다음 저장부터 새 형식으로 쓰인다.
            titles = data['titles']
            self._title_hashes = set(titles.keys())
            self._recent_titles = list(titles.values())[-self.RECENT_TITLE_LIMIT:]
            logger.info(f"중복 해시 로드: 구 형식 {len(titles)}건 → 새 형식으로 전환")
        else:
            self._title_hashes = set(data.get('title_hashes', []))
            self._recent_titles = data.get('recent_titles', [])
        logger.info(f"중복 해시 로드: URL {len(self._hashes)}건 · 제목 {len(self._title_hashes)}건 "
                    f"(유사도 비교: 최근 {len(self._recent_titles)}건)")

    def _save_hashes(self):
        path = self._hash_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            'version': 2,
            'url_hashes': list(self._hashes),
            'title_hashes': list(self._title_hashes),
            'recent_titles': self._recent_titles,
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
        if th in self._title_hashes:
            return True

        # 제목 유사도 매칭 (최근 것만 비교)
        #
        # ratio()는 비싸다. 아래 두 단계는 ratio()의 상한을 먼저 계산해
        # 임계값에 못 미치는 게 확정된 쌍을 건너뛴다. 상한이므로 판정 결과는 바뀌지 않는다.
        #   1) 길이 상한: ratio <= 2*min(len) / (len1+len2)
        #   2) SequenceMatcher의 real_quick_ratio / quick_ratio (표준 라이브러리가 주는 상한)
        title_lower = title.lower()
        n1 = len(title_lower)
        if n1 == 0:
            return False
        thr = self.SIMILARITY_THRESHOLD
        for existing_title in self._recent_titles:
            other = existing_title.lower()
            n2 = len(other)
            if n2 == 0:
                continue
            if 2 * min(n1, n2) / (n1 + n2) < thr:
                continue
            m = SequenceMatcher(None, title_lower, other)
            if m.real_quick_ratio() < thr or m.quick_ratio() < thr:
                continue
            if m.ratio() >= thr:
                return True

        return False

    def register(self, article):
        url = article.get('url', '')
        title = article.get('title', '')

        if url:
            self._hashes.add(self._url_hash(url))

        th = self._title_hash(title)
        self._title_hashes.add(th)
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
