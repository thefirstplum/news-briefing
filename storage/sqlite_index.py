"""역색인 SQLite 구현.

예전 JSON 구현(main_index.json)은 인덱스 전체를 한 덩어리로 들고 있어서, 기사 한 건을 넣어도
파일 전체(운영 기준 259MB)를 다시 써야 했다. 신규 기사가 중앙값 406건이면 한 사이클에 100GB 넘게 썼다.
여기서는 행 단위로 쓰고 커밋만 모은다.

메서드 시그니처와 반환 형태는 예전 JSON 구현과 같다. 기존 데이터는
scripts/migrate_index_to_sqlite.py로 한 번 옮긴다.
"""
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id           TEXT PRIMARY KEY,
    path         TEXT,
    title        TEXT,
    source       TEXT,
    category     TEXT,
    date         TEXT,
    published_at TEXT,
    importance   INTEGER,
    keywords     TEXT
);
CREATE INDEX IF NOT EXISTS idx_articles_date     ON articles(date);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
CREATE INDEX IF NOT EXISTS idx_articles_date_cat ON articles(date, category);
"""


class SqliteIndexManager:
    def __init__(self, store, db_path=None):
        self.store = store
        self._db_path = db_path or self._default_path()
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        # 수집은 스케줄러 스레드에서, 조회는 Flask 요청 스레드에서 일어난다.
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute('PRAGMA journal_mode=WAL')
        self._conn.execute('PRAGMA synchronous=NORMAL')
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        logger.info(f"인덱스 로드: 기사 {self._count()}건 ({self._db_path})")

    def _default_path(self):
        base = self.store._get_storage_path()
        return os.path.join(base, 'index', 'main_index.db')

    def _count(self):
        return self._conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]

    @staticmethod
    def _row_to_info(row):
        """JSON 구현이 돌려주던 dict와 같은 모양으로 맞춘다."""
        return {
            'path': row['path'],
            'title': row['title'],
            'source': row['source'],
            'category': row['category'],
            'date': row['date'],
            'published_at': row['published_at'],
            'keywords': json.loads(row['keywords'] or '[]'),
            'importance': row['importance'],
        }

    # 쓰기

    def add_article(self, article, path, flush=True):
        """기사 한 건을 색인한다. flush=False면 커밋만 미룬다."""
        ai = article.get('ai_analysis') or {}
        row = (
            article['id'],
            path,
            article['title'],
            article.get('source', ''),
            article.get('category', 'general'),
            article['collected_at'][:10],
            article.get('published_at', ''),
            ai.get('importance', 5),
            json.dumps(ai.get('keywords', []), ensure_ascii=False),
        )
        with self._lock:
            self._conn.execute(
                'INSERT OR REPLACE INTO articles '
                '(id, path, title, source, category, date, published_at, importance, keywords) '
                'VALUES (?,?,?,?,?,?,?,?,?)', row)
            if flush:
                self._conn.commit()

    def flush(self):
        with self._lock:
            self._conn.commit()

    # 조회

    def get_article(self, article_id):
        row = self._conn.execute(
            'SELECT * FROM articles WHERE id = ?', (article_id,)).fetchone()
        return self._row_to_info(row) if row else None

    def search(self, query, limit=50):
        """제목 부분일치 10점, 키워드 부분일치 건당 5점. JSON 구현과 동일한 채점."""
        if not query:
            return []
        q = query.lower()
        like = f'%{q}%'
        rows = self._conn.execute(
            'SELECT * FROM articles WHERE LOWER(title) LIKE ? OR LOWER(keywords) LIKE ?',
            (like, like)).fetchall()
        results = []
        for row in rows:
            info = self._row_to_info(row)
            score = 0
            if q in info['title'].lower():
                score += 10
            for kw in info['keywords']:
                if q in kw.lower():
                    score += 5
            if score > 0:
                results.append({**info, 'id': row['id'], 'score': score})
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:limit]

    def get_articles_by_date(self, date_str, category=None):
        if category is None:
            rows = self._conn.execute(
                'SELECT * FROM articles WHERE date = ? ORDER BY published_at DESC',
                (date_str,)).fetchall()
        else:
            rows = self._conn.execute(
                'SELECT * FROM articles WHERE date = ? AND category = ? '
                'ORDER BY published_at DESC', (date_str, category)).fetchall()
        return [{**self._row_to_info(r), 'id': r['id']} for r in rows]

    def get_stats(self):
        cur = self._conn
        total = cur.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
        dates = cur.execute('SELECT COUNT(DISTINCT date) FROM articles').fetchone()[0]
        cats = {r[0]: r[1] for r in cur.execute(
            'SELECT category, COUNT(*) FROM articles GROUP BY category')}
        return {
            'total_articles': total,
            'total_stories': 0,
            'dates': dates,
            'categories': cats,
        }

    def get_recent_article_ids(self, days=3):
        today = datetime.now()
        days_list = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days)]
        marks = ','.join('?' * len(days_list))
        return [r[0] for r in self._conn.execute(
            f'SELECT id FROM articles WHERE date IN ({marks})', days_list)]

    def article_exists(self, article_id):
        return self._conn.execute(
            'SELECT 1 FROM articles WHERE id = ?', (article_id,)).fetchone() is not None

    def close(self):
        with self._lock:
            self._conn.commit()
            self._conn.close()
