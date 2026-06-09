# 매일경제 검색/기사 수집 테스트

## 실행

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scrape_mk.py
```

## 예시

```bash
.venv/bin/python scrape_mk.py \
  --word 삼성전자 \
  --start-date 2026-03-11 \
  --end-date 2026-03-12 \
  --sort accuracy \
  --search-field title \
  --json mk_articles.json
```

검색 목록은 `#list_area li.news_node a.news_item`에서 파싱하고, 기사 본문은 `div.news_cnt_detail_wrap`에서 가져옵니다.
매경ECONOMY 형식 기사는 `#article_body`와 JSON-LD `datePublished`를 fallback으로 사용합니다.

확인 결과 `startDate`와 `endDate`를 같은 날짜로 주면 0건이 반환됩니다. 특정일 뉴스는 검색 URL에서 `startDate=전날`, `endDate=해당일` 형태로 조회해야 합니다.

## 기간 데이터셋 생성

```bash
.venv/bin/python build_mk_dataset.py \
  --start 2026-02-01 \
  --end 2026-03-31 \
  --out-dir data
```

생성 파일:

- `data/mk_samsung_raw_20260201_20260331.jsonl`: 원문 raw JSONL
- `data/mk_samsung_raw_20260201_20260331.pkl`: 원문 raw pickle
- `data/mk_samsung_summaries_20260201_20260331.jsonl`: 기사별 요약 JSONL
- `data/mk_samsung_assigned_20260201_20260331.jsonl`: cutoff 기준 거래일 배정 상세
- `data/mk_samsung_unassigned_20260201_20260331.jsonl`: 마지막 cutoff 이후라 최종 pkl에 들어가지 않은 기사
- `data/samsung_mk_news_20260201_20260331.pkl`: 최종 `cal_date`, `news` DataFrame

거래일은 `pandas_market_calendars`의 `XKRX` 캘린더를 사용합니다. 각 기사 발생 시각은 `09:00 KST` cutoff보다 이전인 가장 가까운 거래일에 배정됩니다.
