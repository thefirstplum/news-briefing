"""JSON 역색인(main_index.json)을 SQLite(main_index.db)로 옮기는 일회성 마이그레이션.

사용: python scripts/migrate_index_to_sqlite.py [인덱스 폴더]
인덱스 폴더를 생략하면 앱과 같은 저장 위치(NEWS_STORAGE_PATH 또는 data/)의 index/를 쓴다.
원본 JSON은 읽기만 한다. 실패해도 기존 인덱스는 그대로 남는다.
"""
import json
import os
import sqlite3
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from storage.json_store import JsonStore  # noqa: E402
from storage.sqlite_index import SCHEMA  # noqa: E402

BATCH = 20000


def migrate(json_path, db_path):
    if os.path.exists(db_path):
        print(f"이미 존재: {db_path} — 먼저 지우거나 다른 경로를 쓰세요")
        return 1

    t0 = time.time()
    print(f"JSON 로드 중: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    articles = data.get('articles', {})
    print(f"  기사 {len(articles):,}건, {time.time()-t0:.1f}초")

    tmp_db = db_path + '.building'
    if os.path.exists(tmp_db):
        os.remove(tmp_db)
    conn = sqlite3.connect(tmp_db)
    conn.executescript(SCHEMA)
    conn.execute('PRAGMA journal_mode=OFF')
    conn.execute('PRAGMA synchronous=OFF')

    t1 = time.time()
    rows, n, skipped = [], 0, 0
    for aid, info in articles.items():
        if not isinstance(info, dict):
            skipped += 1
            continue
        rows.append((
            aid,
            info.get('path', ''),
            info.get('title', ''),
            info.get('source', ''),
            info.get('category', 'general'),
            info.get('date', ''),
            info.get('published_at', ''),
            info.get('importance', 5),
            json.dumps(info.get('keywords', []), ensure_ascii=False),
        ))
        if len(rows) >= BATCH:
            conn.executemany('INSERT OR REPLACE INTO articles VALUES (?,?,?,?,?,?,?,?,?)', rows)
            n += len(rows)
            rows = []
            print(f"  {n:,}건 적재 ({time.time()-t1:.0f}초)")
    if rows:
        conn.executemany('INSERT OR REPLACE INTO articles VALUES (?,?,?,?,?,?,?,?,?)', rows)
        n += len(rows)
    conn.commit()

    got = conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
    conn.close()
    print(f"\n적재 완료: {n:,}건 입력 → 테이블 {got:,}행 (건너뜀 {skipped}건), {time.time()-t1:.0f}초")

    if got != len(articles) - skipped:
        print("✗ 건수 불일치 — 중단")
        return 1

    os.replace(tmp_db, db_path)
    print(f"→ {db_path}  ({os.path.getsize(db_path)/1e6:.0f} MB)")
    print(f"총 {time.time()-t0:.0f}초")
    return 0


if __name__ == '__main__':
    # 기본값은 SqliteIndexManager._default_path()와 같은 폴더
    base = sys.argv[1] if len(sys.argv) > 1 else os.path.join(JsonStore()._get_storage_path(), 'index')
    if not os.path.exists(os.path.join(base, 'main_index.json')):
        print(f"main_index.json이 없음: {base}")
        print("사용: python scripts/migrate_index_to_sqlite.py [인덱스 폴더]")
        sys.exit(1)
    sys.exit(migrate(os.path.join(base, 'main_index.json'),
                     os.path.join(base, 'main_index.db')))
