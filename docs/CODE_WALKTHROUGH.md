# 코드 워크스루 (요약)

설계 이유는 README에 있다. 핵심 로직은 대부분 `analyzers/flow_analyzer.py` 한 파일에 있다.

## 한 사이클 순서

1. `scheduler.collect_and_analyze()`가 락을 잡는다. 이미 돌고 있으면 바로 리턴한다.
2. `_store.sync_fallback_to_hdd()`로 로컬에 쌓인 데이터를 외장으로 옮긴다.
3. `rss_collector.collect_all()` 수집, `dedup.filter_new()` 중복 제거, JSON 저장, 역색인과 ChromaDB 색인. 신규가 0건이면 여기서 끝난다.
4. Ollama 연결 확인, `_wait_for_vram()`(최대 5분), 직전 브리핑 로드.
5. 직전 브리핑의 `generated_at`이 오늘이면 `_analyze_incremental()`, 아니면 `_analyze_full()`. 그래서 자정 이후 첫 사이클(보통 02시)만 전체 분석이다.

전체 분석은 `_group_by_theme()` 군집화, `_merge_similar_themes()` 병합, 점수로 상위 15개, 테마마다 `_analyze_and_attach()`(라우팅과 LLM 호출), `_self_evaluate_and_retry()`, `_generate_overall_briefing()` 순이다.

## 데이터

기사(`rss_collector`가 생성)는 `id`, `title`, `source`, `category`, `url`, `published_at`, `content_snippet` 등을 갖는다. `category`가 라우팅 룰의 입력이다.

분석된 테마는 LLM이 `THEME_ANALYSIS_PROMPT` 형식으로 채운 `title`, `background`, `current_situation`, `flow_analysis`, `prediction`, `korea_impact`, `key_facts`, `importance`, `keywords`에 코드가 `theme_id`, `article_count`, `_articles`(최대 20건), `_eval_score` 등을 덧붙인 것이다.

브리핑은 `themes` 15개와 종합(`overall`)을 담은 JSON 한 파일이다. 웹 화면은 이것만 읽으니 화면이 이상하면 이 파일부터 본다.

주의할 점:

- `_articles`는 이름에 `_`가 붙었지만 저장된다. 증분 분석이 이걸로 기존 기사를 복구하니 지우면 안 된다.
- `theme_index.json`은 파일이 하나다. 안의 `date`가 오늘이 아니면 로드할 때 비운다.
- 웹과 수집이 한 프로세스라 `app.py`를 재시작하면 수집도 끊긴다.

## 튜닝 포인트

| 항목 | 위치 | 현재값 |
|---|---|---|
| 수집 시각 | `scheduler.py` `add_job` | 하루 8회 |
| 브리핑 테마 수 | `_analyze_full`의 `[:15]` | 15 |
| 중복 판정 유사도 / 비교 범위 | `dedup.py` | 0.85 / 최근 5,000건 |
| 라우터 뒤집기 마진 | `router.py` `_OVERRIDE_MARGIN` | 0.025 |
| 재생성 기준 | `_self_evaluate_and_retry`의 `<= 6` | 6점 이하 |
| 증분 재생성 문턱 | `_analyze_incremental`의 `>= 3` | 3건 |
| 모델 / Top-2 병합 | `.env`의 `OLLAMA_MODEL` / `MOE_TOP2` | `qwen3.6:35b-a3b` / 꺼짐 |

숫자는 로그를 보고 바꾸는 게 낫다. 라우터 마진도 0.04에서 override가 0건이라 내린 값이다.

## 로그

`[전문가]` 줄에 라우팅 근거가 찍힌다. `rule(stocks→stocks)`는 룰대로, `embedding(general→world)`는 저신뢰 라벨이라 임베딩이 결정, `embedding_override(tech→economy)`는 임베딩이 룰을 뒤집음, `rule_fallback(stocks)`은 임베딩 호출 실패다.

자주 보는 상황:

- 브리핑이 직전과 똑같다: 어느 테마도 새 기사 3건 문턱을 못 넘은 경우. `매칭 결과` 줄을 본다.
- 전문가가 엉뚱하다: `rule`이면 `config.py`의 피드 카테고리, `embedding`이면 `embedder.py`의 대표 문구를 먼저 본다.
- 깨진 글자나 한자가 섞인다: 프롬프트는 `SYSTEM_PROMPT`, 후처리는 `ollama_client._clean_garbled()`.
- 수집은 되는데 브리핑이 없다: 대개 `Ollama 미연결`이다.
- `이미 수집이 진행 중`이 반복된다: 사이클이 크론 간격보다 길다.

테스트 코드가 없어서 고친 뒤엔 `/api/collect/now`로 한 사이클 돌려 보고 로그로 확인한다.
