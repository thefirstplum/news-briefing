import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Ollama
    OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen3.6:35b-a3b')
    OLLAMA_TIMEOUT = 300

    # Storage: NEWS_STORAGE_PATH가 실제로 마운트돼 있으면 그쪽, 아니면 저장소 안의 로컬 경로
    _LOCAL_PATH = os.path.join(os.path.dirname(__file__), 'data', 'news_data')
    _EXTERNAL_PATH = os.getenv('NEWS_STORAGE_PATH', '')
    EXTERNAL_STORAGE_ACTIVE = bool(_EXTERNAL_PATH) and os.path.isdir(_EXTERNAL_PATH)
    HDD_BASE_PATH = _EXTERNAL_PATH if EXTERNAL_STORAGE_ACTIVE else _LOCAL_PATH
    LOCAL_FALLBACK_PATH = os.path.join(os.path.dirname(__file__), 'data', 'fallback')

    CATEGORIES = {
        'general': '종합',
        'economy': '경제',
        'stocks': '증권/시황',
        'industry': '산업/기업',
        'realestate': '부동산',
        'tech': 'IT/과학',
        'politics': '정치',
        'world': '세계',
        'society': '사회',
        'culture': '생활/문화',
        'sports': '스포츠',
    }

    # Top-2 전문가가 동시에 분석하고 결과를 병합. LLM 호출이 2배가 되므로 기본 비활성.
    # 다른 GPU 작업과 동시에 돌리면 OOM 위험.
    MOE_TOP2 = os.getenv('MOE_TOP2', '0') == '1'
    # Top-1과 Top-2 점수 차가 이 값 미만일 때만 동시 호출
    MOE_TOP2_MARGIN = float(os.getenv('MOE_TOP2_MARGIN', '0.05'))

    # RSS Feeds
    RSS_FEEDS = {
        # 한국 - 종합
        'chosun': {
            'url': 'https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml',
            'source': '조선일보',
            'category': 'general',
            'lang': 'ko',
        },
        'hankyoreh': {
            'url': 'https://www.hani.co.kr/rss/',
            'source': '한겨레',
            'category': 'general',
            'lang': 'ko',
        },
        'mk': {
            'url': 'https://www.mk.co.kr/rss/30000001/',
            'source': '매일경제',
            'category': 'economy',
            'lang': 'ko',
        },
        'hankyung': {
            'url': 'https://www.hankyung.com/feed/all-news',
            'source': '한국경제',
            'category': 'economy',
            'lang': 'ko',
        },
        # 한국 - 연합뉴스 (섹션별)
        'yonhap_politics': {
            'url': 'https://www.yna.co.kr/rss/politics.xml',
            'source': '연합뉴스',
            'category': 'politics',
            'lang': 'ko',
        },
        'yonhap_economy': {
            'url': 'https://www.yna.co.kr/rss/economy.xml',
            'source': '연합뉴스',
            'category': 'economy',
            'lang': 'ko',
        },
        'yonhap_society': {
            'url': 'https://www.yna.co.kr/rss/society.xml',
            'source': '연합뉴스',
            'category': 'society',
            'lang': 'ko',
        },
        'yonhap_culture': {
            'url': 'https://www.yna.co.kr/rss/culture.xml',
            'source': '연합뉴스',
            'category': 'culture',
            'lang': 'ko',
        },
        'yonhap_world': {
            'url': 'https://www.yna.co.kr/rss/international.xml',
            'source': '연합뉴스',
            'category': 'world',
            'lang': 'ko',
        },
        'yonhap_sports': {
            'url': 'https://www.yna.co.kr/rss/sports.xml',
            'source': '연합뉴스',
            'category': 'sports',
            'lang': 'ko',
        },
        # 한국 - SBS (섹션별)
        'sbs_politics': {
            'url': 'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=01&plink=RSSREADER',
            'source': 'SBS',
            'category': 'politics',
            'lang': 'ko',
        },
        'sbs_economy': {
            'url': 'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=02&plink=RSSREADER',
            'source': 'SBS',
            'category': 'economy',
            'lang': 'ko',
        },
        'sbs_society': {
            'url': 'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=03&plink=RSSREADER',
            'source': 'SBS',
            'category': 'society',
            'lang': 'ko',
        },
        'sbs_world': {
            'url': 'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=07&plink=RSSREADER',
            'source': 'SBS',
            'category': 'world',
            'lang': 'ko',
        },
        'sbs_culture': {
            'url': 'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=08&plink=RSSREADER',
            'source': 'SBS',
            'category': 'culture',
            'lang': 'ko',
        },
        'sbs_sports': {
            'url': 'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=09&plink=RSSREADER',
            'source': 'SBS',
            'category': 'sports',
            'lang': 'ko',
        },
        # 한국 - IT/과학
        'itchosun': {
            'url': 'https://it.chosun.com/rss/allArticle.xml',
            'source': 'IT조선',
            'category': 'tech',
            'lang': 'ko',
        },
        'hankyung_it': {
            'url': 'https://www.hankyung.com/feed/it',
            'source': '한국경제',
            'category': 'tech',
            'lang': 'ko',
        },
        'hani_science': {
            'url': 'https://www.hani.co.kr/rss/science/',
            'source': '한겨레',
            'category': 'tech',
            'lang': 'ko',
        },
        'etnews': {
            'url': 'https://rss.etnews.com/Section901.xml',
            'source': '전자신문',
            'category': 'tech',
            'lang': 'ko',
        },
        # 한국 - 경향신문 (섹션별)
        'khan_politics': {
            'url': 'https://www.khan.co.kr/rss/rssdata/politic_news.xml',
            'source': '경향신문',
            'category': 'politics',
            'lang': 'ko',
        },
        'khan_economy': {
            'url': 'https://www.khan.co.kr/rss/rssdata/economy_news.xml',
            'source': '경향신문',
            'category': 'economy',
            'lang': 'ko',
        },
        # 한국 - 뉴시스 (섹션별)
        'newsis_politics': {
            'url': 'https://newsis.com/RSS/politics.xml',
            'source': '뉴시스',
            'category': 'politics',
            'lang': 'ko',
        },
        'newsis_economy': {
            'url': 'https://newsis.com/RSS/economy.xml',
            'source': '뉴시스',
            'category': 'economy',
            'lang': 'ko',
        },
        'newsis_world': {
            'url': 'https://newsis.com/RSS/international.xml',
            'source': '뉴시스',
            'category': 'world',
            'lang': 'ko',
        },
        # 영국 - BBC (섹션별)
        'bbc_world': {
            'url': 'https://feeds.bbci.co.uk/news/world/rss.xml',
            'source': 'BBC',
            'category': 'world',
            'lang': 'en',
        },
        'bbc_politics': {
            'url': 'https://feeds.bbci.co.uk/news/politics/rss.xml',
            'source': 'BBC',
            'category': 'politics',
            'lang': 'en',
        },
        'bbc_business': {
            'url': 'https://feeds.bbci.co.uk/news/business/rss.xml',
            'source': 'BBC',
            'category': 'economy',
            'lang': 'en',
        },
        'bbc_tech': {
            'url': 'https://feeds.bbci.co.uk/news/technology/rss.xml',
            'source': 'BBC',
            'category': 'tech',
            'lang': 'en',
        },
        'bbc_science': {
            'url': 'https://feeds.bbci.co.uk/news/science_and_environment/rss.xml',
            'source': 'BBC',
            'category': 'tech',
            'lang': 'en',
        },
        'bbc_culture': {
            'url': 'https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml',
            'source': 'BBC',
            'category': 'culture',
            'lang': 'en',
        },
        'bbc_sports': {
            'url': 'https://feeds.bbci.co.uk/sport/rss.xml',
            'source': 'BBC',
            'category': 'sports',
            'lang': 'en',
        },
        # 영국 - The Guardian (섹션별)
        'guardian_world': {
            'url': 'https://www.theguardian.com/world/rss',
            'source': 'The Guardian',
            'category': 'world',
            'lang': 'en',
        },
        'guardian_tech': {
            'url': 'https://www.theguardian.com/uk/technology/rss',
            'source': 'The Guardian',
            'category': 'tech',
            'lang': 'en',
        },
        'guardian_sports': {
            'url': 'https://www.theguardian.com/uk/sport/rss',
            'source': 'The Guardian',
            'category': 'sports',
            'lang': 'en',
        },
        # 미국 - CNN (섹션별)
        'cnn_world': {
            'url': 'http://rss.cnn.com/rss/edition_world.rss',
            'source': 'CNN',
            'category': 'world',
            'lang': 'en',
        },
        'cnn_business': {
            'url': 'http://rss.cnn.com/rss/money_latest.rss',
            'source': 'CNN',
            'category': 'economy',
            'lang': 'en',
        },
        'cnn_tech': {
            'url': 'http://rss.cnn.com/rss/edition_technology.rss',
            'source': 'CNN',
            'category': 'tech',
            'lang': 'en',
        },
        # 미국 - 기타
        'nyt_world': {
            'url': 'https://rss.nytimes.com/services/xml/rss/nyt/World.xml',
            'source': 'New York Times',
            'category': 'world',
            'lang': 'en',
        },
        'npr': {
            'url': 'https://feeds.npr.org/1001/rss.xml',
            'source': 'NPR',
            'category': 'general',
            'lang': 'en',
        },
        # 중동 - Al Jazeera
        'aljazeera': {
            'url': 'https://www.aljazeera.com/xml/rss/all.xml',
            'source': 'Al Jazeera',
            'category': 'world',
            'lang': 'en',
        },
        # 일본
        'nhk': {
            'url': 'https://www3.nhk.or.jp/rss/news/cat0.xml',
            'source': 'NHK',
            'category': 'general',
            'lang': 'ja',
        },
        'mainichi': {
            'url': 'https://mainichi.jp/rss/etc/mainichi-flash.rss',
            'source': '마이니치신문',
            'category': 'general',
            'lang': 'ja',
        },
        'japantimes': {
            'url': 'https://www.japantimes.co.jp/feed/',
            'source': 'Japan Times',
            'category': 'general',
            'lang': 'en',
        },
        # 한국 증권 전문 피드 (최우선 카테고리)
        'edaily_stock': {
            'url': 'http://rss.edaily.co.kr/stock_news.xml',  # HTTP만 작동 (HTTPS는 302)
            'source': '이데일리',
            'category': 'stocks',
            'lang': 'ko',
        },
        'edaily_finance': {
            'url': 'http://rss.edaily.co.kr/finance_news.xml',
            'source': '이데일리',
            'category': 'stocks',
            'lang': 'ko',
        },
        'edaily_economy': {
            'url': 'http://rss.edaily.co.kr/economy_news.xml',
            'source': '이데일리',
            'category': 'economy',
            'lang': 'ko',
        },
        'edaily_news': {
            'url': 'http://rss.edaily.co.kr/edaily_news.xml',
            'source': '이데일리',
            'category': 'general',
            'lang': 'ko',
        },
        'mt_stock': {
            'url': 'https://rss.mt.co.kr/mt_news.xml',
            'source': '머니투데이',
            'category': 'stocks',
            'lang': 'ko',
        },
        'mk_stock': {
            'url': 'https://www.mk.co.kr/rss/40300001/',
            'source': '매일경제',
            'category': 'stocks',
            'lang': 'ko',
        },
        'hk_market': {
            'url': 'https://www.hankyung.com/feed/finance',
            'source': '한국경제',
            'category': 'stocks',
            'lang': 'ko',
        },
        'sedaily_stock': {
            'url': 'https://www.sedaily.com/RSS/?id=S1',
            'source': '서울경제',
            'category': 'stocks',
            'lang': 'ko',
        },
        # 한국 산업/기업 (종목별 영향)
        'mk_industry': {
            'url': 'https://www.mk.co.kr/rss/50100032/',
            'source': '매일경제',
            'category': 'industry',
            'lang': 'ko',
        },
        'hk_industry': {
            'url': 'https://www.hankyung.com/feed/industry',
            'source': '한국경제',
            'category': 'industry',
            'lang': 'ko',
        },
        'sedaily_industry': {
            'url': 'https://www.sedaily.com/RSS/?id=S2',
            'source': '서울경제',
            'category': 'industry',
            'lang': 'ko',
        },
        # 한국 부동산 (거시 영향)
        'mk_realestate': {
            'url': 'https://www.mk.co.kr/rss/50300009/',
            'source': '매일경제',
            'category': 'realestate',
            'lang': 'ko',
        },
        # 글로벌 주식 매체
        'bloomberg_markets': {
            'url': 'https://feeds.bloomberg.com/markets/news.rss',
            'source': 'Bloomberg',
            'category': 'stocks',
            'lang': 'en',
        },
        'cnbc_markets': {
            'url': 'https://www.cnbc.com/id/15839069/device/rss/rss.html',
            'source': 'CNBC',
            'category': 'stocks',
            'lang': 'en',
        },
        'investing_news': {
            'url': 'https://www.investing.com/rss/news_25.rss',
            'source': 'Investing.com',
            'category': 'stocks',
            'lang': 'en',
        },
        'wsj_markets': {
            'url': 'https://feeds.a.dj.com/rss/RSSMarketsMain.xml',
            'source': 'WSJ',
            'category': 'stocks',
            'lang': 'en',
        },
    }
