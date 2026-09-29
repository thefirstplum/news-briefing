from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from collectors import RSSCollector, DedupChecker
from analyzers import FlowAnalyzer, OllamaClient
from config import Config
import logging
import threading
import requests as _req

logger = logging.getLogger(__name__)

_store = None
_index = None
_vector = None
_rss_collector = RSSCollector()
_dedup = None
_flow_analyzer = None


def init_scheduler(store, index, vector=None):
    global _store, _index, _vector, _dedup, _flow_analyzer
    _store = store
    _index = index
    _vector = vector
    _dedup = DedupChecker(store)
    _flow_analyzer = FlowAnalyzer(store, vector)


def _wait_for_vram():
    """분석 전 VRAM 여유 확인. 다른 모델이 점유 중이면 최대 5분 대기"""
    import time
    for attempt in range(10):
        try:
            resp = _req.get(f"{Config.OLLAMA_BASE_URL}/api/ps", timeout=5)
            models = resp.json().get('models', [])
            others = [m['name'] for m in models if m['name'] != Config.OLLAMA_MODEL]
            if not others:
                return True
            total_vram = sum(m.get('size', 0) for m in models)
            if total_vram < 50e9:  # 50GB 이하면 여유 있음
                return True
            logger.info(f"VRAM 대기 ({attempt+1}/10): {', '.join(others)} 사용 중 ({total_vram/1e9:.0f}GB)")
            time.sleep(30)
        except Exception:
            return True
    logger.warning("VRAM 대기 타임아웃, 분석 진행")
    return True


# 크론과 수동 트리거가 같은 함수를 부른다. 한 사이클이 한 시간을 넘기도 해서
# 겹칠 수 있는데, 그러면 중복 해시 인덱스와 그날 브리핑을 양쪽이 같이 덮어쓴다.
_collect_lock = threading.Lock()


def is_collecting():
    return _collect_lock.locked()


def collect_and_analyze():
    if not _collect_lock.acquire(blocking=False):
        logger.warning("이미 수집이 진행 중 — 이번 실행은 건너뜁니다")
        return
    try:
        _collect_and_analyze_impl()
    finally:
        _collect_lock.release()


def _collect_and_analyze_impl():
    logger.info("=== 뉴스 수집 시작 ===")
    start = datetime.now()

    _store.sync_fallback_to_hdd()

    raw_articles = _rss_collector.collect_all()

    new_articles = _dedup.filter_new(raw_articles)
    if not new_articles:
        logger.info("신규 기사 없음")
        return

    for article in new_articles:
        path = _store.save_article(article)
        _index.add_article(article, path)

    logger.info(f"{len(new_articles)}건 저장 완료")

    if _vector:
        _vector.add_articles(new_articles)

    # 다른 모델이 VRAM을 물고 있으면 분석 단계만 대기시킨다
    if OllamaClient().is_available():
        _wait_for_vram()
        prev = _store.load_latest_briefing()
        today = datetime.now().strftime('%Y-%m-%d')
        prev_is_today = prev and prev.get('generated_at', '').startswith(today)

        if prev_is_today:
            # 오늘 브리핑이 이미 있으면 새 기사만 증분 분석
            logger.info(f"증분 분석: 새 기사 {len(new_articles)}건")
            _flow_analyzer.analyze(new_articles, incremental=True)
        else:
            # 오늘 첫 회차는 전체 분석
            all_today = _store.list_articles_by_date(today)
            if all_today:
                logger.info(f"전체 분석: 오늘자 {len(all_today)}건 대상")
                _flow_analyzer.analyze(all_today, incremental=False)
            else:
                _flow_analyzer.analyze(new_articles, incremental=False)
    else:
        logger.warning("Ollama 미연결 - 흐름 분석 건너뜀")

    elapsed = (datetime.now() - start).total_seconds()
    logger.info(f"=== 완료: {len(new_articles)}건 수집, {elapsed:.1f}초 ===")


def setup_scheduler(store, index, vector=None):
    """국내장 흐름에 맞춰 하루 8회 수집·분석.

      02:00 미국장 마감 반영
      06:00 출근 전 아침 브리핑
      08:00 동시호가, 장 시작 직전
      09:30 장 시작 30분
      11:00 오전장 정리
      14:30 마감 임박
      16:00 장 마감 후
      20:00 미국장 시작 전
    """
    init_scheduler(store, index, vector)
    scheduler = BackgroundScheduler(daemon=True)
    # 정각 실행분
    scheduler.add_job(
        collect_and_analyze, 'cron',
        hour='2,6,8,11,16,20', minute=0,
        id='main_collection',
    )
    # 장중 09:30(개장 30분), 14:30(마감 임박)
    scheduler.add_job(
        collect_and_analyze, 'cron',
        hour='9,14', minute=30,
        id='intraday_collection',
    )
    scheduler.start()
    next_run = min(j.next_run_time for j in scheduler.get_jobs())
    logger.info(
        f"스케줄러 시작: 02/06/08/09:30/11/14:30/16/20시, 다음 실행 {next_run.strftime('%Y-%m-%d %H:%M')}"
    )
    return scheduler
