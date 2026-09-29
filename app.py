from flask import Flask, render_template, jsonify, request
from storage import JsonStore, IndexManager, VectorStore
from analyzers import OllamaClient
from scheduler import setup_scheduler
from config import Config
from datetime import datetime
import logging
import atexit
import hmac
import threading
import json
import os

# 로그 파일 핸들러가 디렉토리를 만들지는 않는다. 새로 받아 처음 띄울 때 여기서 죽는다.
os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/news.log', encoding='utf-8'),
    ],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

store = JsonStore()
index = IndexManager(store)
vector = VectorStore()
ollama = OllamaClient()

# 수집 한 사이클이 수십 분 걸려서 트리거가 열려 있으면 누구나 GPU를 붙잡아 둘 수 있다.
# 비밀번호를 설정하지 않았으면 엔드포인트는 항상 거부한다.
COLLECT_PW = os.environ.get('NEWS_COLLECT_PW', '')


# 페이지 라우트

@app.route('/')
@app.route('/briefing')
def briefing_latest():
    briefing = store.load_latest_briefing()
    stats = index.get_stats()
    if not briefing:
        return render_template('briefing.html', briefing=None, stats=stats, categories=Config.CATEGORIES)
    return render_template('briefing.html',
                           briefing=briefing,
                           stats=stats,
                           categories=Config.CATEGORIES)


@app.route('/briefing/history')
def briefing_history():
    briefings = store.list_briefings(limit=30)
    return render_template('briefing_history.html',
                           briefings=briefings,
                           categories=Config.CATEGORIES)


@app.route('/briefing/<filename>')
def briefing_detail(filename):
    if not filename.startswith('briefing_') or not filename.endswith('.json'):
        return "잘못된 요청입니다", 400
    briefing = store.load_briefing_by_filename(filename)
    if not briefing:
        return "브리핑을 찾을 수 없습니다", 404
    prev_f, next_f = store.get_adjacent_briefings(filename)
    stats = index.get_stats()
    return render_template('briefing.html',
                           briefing=briefing,
                           stats=stats,
                           prev_file=prev_f,
                           next_file=next_f,
                           categories=Config.CATEGORIES)


@app.route('/theme/<theme_id>')
def theme_view(theme_id):
    briefing = store.load_latest_briefing()
    theme = None
    if briefing:
        for t in briefing.get('themes', []):
            if t.get('theme_id') == theme_id:
                theme = t
                break
    if not theme:
        return "테마를 찾을 수 없습니다", 404
    return render_template('theme.html',
                           theme=theme,
                           categories=Config.CATEGORIES)


@app.route('/category/<category>')
def category_view(category):
    today = datetime.now().strftime('%Y-%m-%d')
    articles = index.get_articles_by_date(today, category=category)
    cat_name = Config.CATEGORIES.get(category, category)
    # 이 카테고리 관련 테마 추출
    briefing = store.load_latest_briefing()
    themes = []
    if briefing:
        for t in briefing.get('themes', []):
            # 키워드 기반 매칭
            themes.append(t)
    return render_template('category.html',
                           articles=articles,
                           category=category,
                           category_name=cat_name,
                           themes=themes,
                           categories=Config.CATEGORIES)


@app.route('/article/<article_id>')
def article_view(article_id):
    date_str = request.args.get('date')
    category = request.args.get('category')
    article = store.load_article(article_id, date_str, category)
    if not article:
        info = index._index['articles'].get(article_id)
        if info and info.get('path'):
            article = store._read_json(info['path'])
    if not article:
        return "기사를 찾을 수 없습니다", 404
    return render_template('article.html',
                           article=article,
                           categories=Config.CATEGORIES)


@app.route('/archive')
def archive():
    dates = store.get_available_dates(limit=60)
    return render_template('archive.html',
                           dates=dates,
                           categories=Config.CATEGORIES)


@app.route('/archive/<date_str>')
def archive_date(date_str):
    articles = store.list_articles_by_date(date_str)
    return render_template('archive_date.html',
                           articles=articles,
                           date=date_str,
                           categories=Config.CATEGORIES)


@app.route('/search')
def search_view():
    q = request.args.get('q', '')
    results = index.search(q) if q else []
    return render_template('search.html',
                           query=q,
                           results=results,
                           categories=Config.CATEGORIES)


# API 라우트

@app.route('/api/stats')
def api_stats():
    stats = index.get_stats()
    stats['hdd_connected'] = store.is_hdd_available()
    stats['ollama_available'] = ollama.is_available()
    stats['ollama_model'] = Config.OLLAMA_MODEL
    briefing = store.load_latest_briefing()
    stats['last_briefing'] = briefing.get('generated_at', '') if briefing else ''
    return jsonify(stats)


@app.route('/api/briefing')
def api_briefing():
    briefing = store.load_latest_briefing()
    return jsonify(briefing or {})


@app.route('/api/collect/now', methods=['POST'])
def api_collect_now():
    from scheduler import collect_and_analyze, is_collecting

    if not COLLECT_PW:
        logger.error('NEWS_COLLECT_PW 미설정 — 수동 수집 거부')
        return jsonify({'status': 'error', 'message': '서버에 비밀번호가 설정되지 않았습니다'}), 503

    pw = request.headers.get('X-Collect-Password', '')
    if not hmac.compare_digest(pw, COLLECT_PW):
        logger.warning('수동 수집 인증 실패')
        return jsonify({'status': 'unauthorized', 'message': '비밀번호가 틀렸습니다'}), 401

    if is_collecting():
        return jsonify({'status': 'busy', 'message': '이미 수집이 진행 중입니다'}), 409

    t = threading.Thread(target=collect_and_analyze, daemon=True)
    t.start()
    logger.info('수동 수집 트리거됨')
    return jsonify({'status': 'started', 'message': '수집 + 흐름 분석이 시작되었습니다'})


@app.route('/api/search')
def api_search():
    q = request.args.get('q', '')
    results = index.search(q) if q else []
    return jsonify(results)


# 피드백 API

FEEDBACK_DIR = os.path.join(store.base_path, 'feedback')
os.makedirs(FEEDBACK_DIR, exist_ok=True)


def _get_feedback_path(date_str=None):
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
    return os.path.join(FEEDBACK_DIR, f'feedback_{date_str}.json')


def _load_feedback(date_str=None):
    path = _get_feedback_path(date_str)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'feedbacks': [], 'date': date_str or datetime.now().strftime('%Y-%m-%d')}


def _save_feedback(data, date_str=None):
    path = _get_feedback_path(date_str)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route('/api/feedback', methods=['POST'])
def api_feedback():
    body = request.get_json()
    theme_id = body.get('theme_id', '')
    rating = body.get('rating', '')
    title = body.get('title', '')

    if not theme_id or rating not in ('good', 'bad'):
        return jsonify({'error': '잘못된 요청'}), 400

    today = datetime.now().strftime('%Y-%m-%d')
    data = _load_feedback(today)

    # 같은 테마 기존 피드백 업데이트
    existing = next((f for f in data['feedbacks'] if f['theme_id'] == theme_id), None)
    if existing:
        existing['rating'] = rating
        existing['updated_at'] = datetime.now().isoformat()
    else:
        data['feedbacks'].append({
            'theme_id': theme_id,
            'title': title,
            'rating': rating,
            'created_at': datetime.now().isoformat(),
        })

    _save_feedback(data, today)
    msg = '좋은 분석!' if rating == 'good' else '개선 반영 예정'
    return jsonify({'status': 'ok', 'message': msg})


@app.route('/api/feedback/latest')
def api_feedback_latest():
    today = datetime.now().strftime('%Y-%m-%d')
    data = _load_feedback(today)
    return jsonify(data)


@app.route('/api/feedback/summary')
def api_feedback_summary():
    """최근 7일 피드백 요약 (조회용). 프롬프트에 넣는 집계는 FlowAnalyzer._load_feedback_context()가 따로 한다."""
    from datetime import timedelta
    good_titles = []
    bad_titles = []
    for i in range(7):
        date_str = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        data = _load_feedback(date_str)
        for fb in data.get('feedbacks', []):
            if fb['rating'] == 'good':
                good_titles.append(fb.get('title', ''))
            else:
                bad_titles.append(fb.get('title', ''))
    return jsonify({
        'good_count': len(good_titles),
        'bad_count': len(bad_titles),
        'good_examples': good_titles[:10],
        'bad_examples': bad_titles[:10],
    })


# 시작

if __name__ == '__main__':
    logger.info("뉴스 수집 시스템 시작")
    logger.info(f"HDD: {'연결됨' if store.is_hdd_available() else '미연결'}")
    logger.info(f"Ollama: {'사용가능' if ollama.is_available() else '미연결'}")

    scheduler = setup_scheduler(store, index, vector)
    atexit.register(lambda: scheduler.shutdown())

    app.run(host=os.getenv('HOST', '0.0.0.0'), port=int(os.getenv('PORT', '3400')), debug=False)
