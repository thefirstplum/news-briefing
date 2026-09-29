"""RSS 피드 수집기: 60개 피드를 파싱하고 본문 HTML을 정제한다."""
import feedparser
import hashlib
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from config import Config
import logging
import requests

logger = logging.getLogger(__name__)

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) NewsCollector/1.0'


class RSSCollector:
    def __init__(self):
        self.feeds = Config.RSS_FEEDS
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': USER_AGENT})

    def collect_all(self):
        all_articles = []
        for feed_id, feed_info in self.feeds.items():
            try:
                articles = self._collect_feed(feed_id, feed_info)
                all_articles.extend(articles)
                logger.info(f"[{feed_id}] {len(articles)}건 수집")
            except Exception as e:
                logger.error(f"[{feed_id}] 수집 실패: {e}")
        logger.info(f"전체 {len(all_articles)}건 수집 완료")
        return all_articles

    def _collect_feed(self, feed_id, feed_info):
        url = feed_info['url']
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except requests.RequestException:
            feed = feedparser.parse(url)

        articles = []
        for entry in feed.entries:
            try:
                article = self._parse_entry(entry, feed_info, feed_id)
                if article:
                    articles.append(article)
            except Exception as e:
                logger.debug(f"엔트리 파싱 실패: {e}")
        return articles

    def _parse_entry(self, entry, feed_info, feed_id):
        title = self._clean_html(entry.get('title', ''))
        if not title:
            return None

        link = entry.get('link', '')
        article_id = self._generate_id(link or title)

        published = self._parse_date(entry)
        description = self._clean_html(
            entry.get('summary', entry.get('description', ''))
        )
        # 일부 피드는 content 필드에 본문이 있음
        content = ''
        if hasattr(entry, 'content') and entry.content:
            content = self._clean_html(entry.content[0].get('value', ''))

        return {
            'id': article_id,
            'title': title,
            'source': feed_info['source'],
            'source_feed': feed_id,
            'category': feed_info['category'],
            'lang': feed_info['lang'],
            'url': link,
            'published_at': published,
            'collected_at': datetime.now().isoformat(),
            'content_snippet': content or description,
            'ai_analysis': None,
        }

    def _generate_id(self, text):
        h = hashlib.md5(text.encode('utf-8')).hexdigest()[:12]
        return f"art_{h}"

    def _clean_html(self, text):
        if not text:
            return ''
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'&[a-zA-Z]+;', ' ', text)
        text = re.sub(r'&#\d+;', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _parse_date(self, entry):
        for field in ['published_parsed', 'updated_parsed']:
            parsed = entry.get(field)
            if parsed:
                try:
                    from time import mktime
                    return datetime.fromtimestamp(mktime(parsed)).isoformat()
                except (ValueError, OverflowError):
                    pass
        for field in ['published', 'updated']:
            raw = entry.get(field, '')
            if raw:
                try:
                    return parsedate_to_datetime(raw).isoformat()
                except Exception:
                    pass
        return datetime.now().isoformat()
