import json
import os
from datetime import datetime
from config import Config
import logging

logger = logging.getLogger(__name__)


class JsonStore:
    def __init__(self):
        self.base_path = Config.HDD_BASE_PATH
        self.fallback_path = Config.LOCAL_FALLBACK_PATH

    def _get_storage_path(self):
        if self.is_hdd_available():
            return self.base_path
        if Config.EXTERNAL_STORAGE_ACTIVE:
            logger.warning("외장 HDD 미연결 - 로컬 폴백 사용")
        os.makedirs(self.fallback_path, exist_ok=True)
        return self.fallback_path

    def is_hdd_available(self):
        # 외장 경로를 안 쓰면 폴백이 곧 저장소다. 여기서 True가 나오면
        # sync_fallback_to_hdd()가 폴백 안의 ChromaDB까지 지워 버린다.
        return Config.EXTERNAL_STORAGE_ACTIVE and os.path.isdir(self.base_path)

    def _ensure_dir(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _write_json(self, path, data):
        self._ensure_dir(path)
        tmp_path = path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)

    def _read_json(self, path):
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _article_path(self, article):
        base = self._get_storage_path()
        dt = datetime.fromisoformat(article['collected_at'])
        category = article.get('category', 'general')
        return os.path.join(
            base, 'articles',
            dt.strftime('%Y'), dt.strftime('%m'), dt.strftime('%d'),
            category,
            f"{article['id']}.json"
        )

    def save_article(self, article):
        path = self._article_path(article)
        self._write_json(path, article)
        logger.debug(f"기사 저장: {article['id']}")
        return path

    def load_article(self, article_id, date_str=None, category=None):
        base = self._get_storage_path()
        if date_str and category:
            y, m, d = date_str.split('-')
            path = os.path.join(base, 'articles', y, m, d, category, f"{article_id}.json")
            return self._read_json(path)
        # index에서 경로를 찾아야 함
        return None

    def list_articles_by_date(self, date_str, category=None):
        base = self._get_storage_path()
        y, m, d = date_str.split('-')
        date_dir = os.path.join(base, 'articles', y, m, d)
        if not os.path.isdir(date_dir):
            return []
        results = []
        categories = [category] if category else os.listdir(date_dir)
        for cat in categories:
            cat_dir = os.path.join(date_dir, cat)
            if not os.path.isdir(cat_dir):
                continue
            for fname in os.listdir(cat_dir):
                if fname.endswith('.json'):
                    data = self._read_json(os.path.join(cat_dir, fname))
                    if data:
                        results.append(data)
        return sorted(results, key=lambda a: a.get('published_at', ''), reverse=True)

    def get_available_dates(self, limit=30):
        base = self._get_storage_path()
        articles_dir = os.path.join(base, 'articles')
        if not os.path.isdir(articles_dir):
            return []
        dates = []
        for year in sorted(os.listdir(articles_dir), reverse=True):
            year_dir = os.path.join(articles_dir, year)
            if not os.path.isdir(year_dir):
                continue
            for month in sorted(os.listdir(year_dir), reverse=True):
                month_dir = os.path.join(year_dir, month)
                if not os.path.isdir(month_dir):
                    continue
                for day in sorted(os.listdir(month_dir), reverse=True):
                    if os.path.isdir(os.path.join(month_dir, day)):
                        dates.append(f"{year}-{month}-{day}")
                        if len(dates) >= limit:
                            return dates
        return dates

    # 브리핑 (흐름 분석)

    def save_briefing(self, briefing):
        base = self._get_storage_path()
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(base, 'briefings', f"briefing_{ts}.json")
        self._write_json(path, briefing)
        # latest 심볼릭 파일도 저장
        latest_path = os.path.join(base, 'briefings', 'latest.json')
        self._write_json(latest_path, briefing)
        logger.info(f"브리핑 저장: {path}")
        return path

    def load_latest_briefing(self):
        base = self._get_storage_path()
        path = os.path.join(base, 'briefings', 'latest.json')
        return self._read_json(path)

    def load_briefing_by_filename(self, filename):
        base = self._get_storage_path()
        path = os.path.join(base, 'briefings', filename)
        data = self._read_json(path)
        if data:
            data['_filename'] = filename
        return data

    def get_adjacent_briefings(self, filename):
        """이전/다음 브리핑 파일명 반환"""
        base = self._get_storage_path()
        briefings_dir = os.path.join(base, 'briefings')
        if not os.path.isdir(briefings_dir):
            return None, None
        files = sorted(
            f for f in os.listdir(briefings_dir)
            if f.startswith('briefing_') and f.endswith('.json')
        )
        if filename not in files:
            return None, None
        idx = files.index(filename)
        prev_f = files[idx - 1] if idx > 0 else None
        next_f = files[idx + 1] if idx < len(files) - 1 else None
        return prev_f, next_f

    def list_briefings(self, limit=20):
        base = self._get_storage_path()
        briefings_dir = os.path.join(base, 'briefings')
        if not os.path.isdir(briefings_dir):
            return []
        files = sorted(
            [f for f in os.listdir(briefings_dir)
             if f.startswith('briefing_') and f.endswith('.json')],
            reverse=True,
        )[:limit]
        results = []
        for fname in files:
            data = self._read_json(os.path.join(briefings_dir, fname))
            if data:
                data['_filename'] = fname
                results.append(data)
        return results

    def sync_fallback_to_hdd(self):
        if not self.is_hdd_available():
            return False
        if not os.path.isdir(self.fallback_path):
            return True
        import shutil
        for root, dirs, files in os.walk(self.fallback_path):
            for fname in files:
                if not fname.endswith('.json'):
                    continue
                src = os.path.join(root, fname)
                rel = os.path.relpath(src, self.fallback_path)
                dst = os.path.join(self.base_path, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
        shutil.rmtree(self.fallback_path, ignore_errors=True)
        logger.info("폴백 데이터 -> HDD 동기화 완료")
        return True
