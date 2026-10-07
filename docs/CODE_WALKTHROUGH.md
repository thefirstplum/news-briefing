# 코드 워크스루 (요약)

설계 이유는 [NOTES.md](NOTES.md) 참조. 핵심 로직 대부분은 `analyzers/flow_analyzer.py` 한 파일에 위치.

## 한 사이클 순서

1. `scheduler.collect_and_analyze()`가 락 획득. 이미 실행 중이면 즉시 리턴
2. `_store.sync_fallback_to_hdd()`로 로컬에 쌓인 데이터를 외장으로 이동
3. `rss_collector.collect_all()` 수집, `dedup.filter_new()` 중복 제거, JSON 저장, SQLite 역색인과 ChromaDB 색인. 신규 0건이면 여기서 종료
4. Ollama 연결 확인, `_wait_for_vram()`(최대 5분), 직전 브리핑 로드
5. 직전 브리핑의 `generated_at`이 오늘이면 `_analyze_incremental()`, 아니면 `_analyze_full()`. 따라서 자정 이후 첫 사이클(보통 02시)만 전체 분석

전체 분석 순서: `_group_by_theme()` 군집화, `_merge_similar_themes()` 병합, 점수 기준 상위 15개 선정, 테마별 `_analyze_and_attach()`(라우팅과 LLM 호출), `_self_evaluate_and_retry()`, `_generate_overall_briefing()`.

## 데이터

- 기사(`rss_collector` 생성): `id`, `title`, `source`, `category`, `url`, `published_at`, `content_snippet` 등. `category`가 라우팅 룰 입력
- 분석된 테마: LLM이 `THEME_ANALYSIS_PROMPT` 형식으로 채운 `title`, `background`, `current_situation`, `flow_analysis`, `prediction`, `korea_impact`, `key_facts`, `importance`, `keywords`에 코드가 `theme_id`, `article_count`, `_articles`(최대 20건), `_eval_score` 등을 추가한 구조
- 브리핑: `themes` 15개와 종합(`overall`)을 담은 JSON 단일 파일. 웹 화면은 이 파일만 읽으므로 화면 이상 시 이 파일부터 확인

주의 사항:

- `_articles`는 이름에 `_` 접두사가 있으나 저장 대상. 증분 분석이 기존 기사 복구에 사용하므로 삭제 금지
- `theme_index.json`은 단일 파일. 내부 `date`가 오늘이 아니면 로드 시 초기화
- 웹과 수집이 한 프로세스라 `app.py` 재시작 시 수집도 중단

## 튜닝 포인트

| 항목 | 위치 | 현재값 |
|---|---|---|
| 수집 시각 | `scheduler.py` `add_job` | 하루 8회 |
| 브리핑 테마 수 | `_analyze_full`의 `[:15]` | 15 |
| 중복 판정 유사도 / 비교 범위 | `dedup.py` | 0.85 / 최근 5,000건 |
| 라우터 임베딩 교체 마진 | `router.py` `_OVERRIDE_MARGIN` | 0.025 |
| 재생성 기준 | `_self_evaluate_and_retry`의 `<= 6` | 6점 이하 |
| 증분 재생성 문턱 | `_analyze_incremental`의 `>= 3` | 3건 |
| 모델 / Top-2 병합 | `.env`의 `OLLAMA_MODEL` / `MOE_TOP2` | `qwen3.6:35b-a3b` / 꺼짐 |

수치는 로그 기준 조정 권장. 라우터 마진도 0.04에서 임베딩 교체 0건이라 하향한 값.

## 로그

`[전문가]` 줄에 라우팅 근거 기록.

- `rule(stocks→stocks)`: 룰대로 결정
- `embedding(general→world)`: 저신뢰 라벨이라 임베딩이 결정
- `embedding_override(tech→economy)`: 임베딩 교체(override). 임베딩이 룰 후보 대신 선택
- `rule_fallback(stocks)`: 임베딩 호출 실패

증상별 확인 위치:

- 브리핑이 직전과 동일: 어느 테마도 새 기사 3건 문턱 미달. `매칭 결과` 줄 확인
- 전문가 선택 이상: `rule`이면 `config.py`의 피드 카테고리, `embedding`이면 `embedder.py`의 대표 문구 우선 확인
- 깨진 글자나 한자 혼입: 프롬프트는 `SYSTEM_PROMPT`, 후처리는 `ollama_client._clean_garbled()`
- 수집은 되나 브리핑 없음: 대개 `Ollama 미연결`
- `이미 수집이 진행 중` 반복: 사이클이 크론 간격보다 김
- `수집 락이 N시간째 안 풀림` 기록: 수집 스레드 정지 상태. 앱 재시작 필요

테스트 코드가 없어 수정 후 `/api/collect/now`로 한 사이클 실행하고 로그로 확인.
