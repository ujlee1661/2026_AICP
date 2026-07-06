# News Scraper

뉴스 원천 데이터를 만들기 위한 보조 스크립트 모음이다. 메인 시뮬레이션은 이 폴더를 직접 호출하지 않고, 최종적으로 `data/samsung_news_raw.pkl` 또는 그에 준하는 원천 pkl을 `scripts/02_prepare_news.py`가 읽는다.

## 주요 파일

| 파일 | 역할 |
| --- | --- |
| `scrape_mk.py` | 매일경제 검색 결과와 기사 본문 수집 |
| `scrape_mk_stock_playwright.py` | Playwright 기반 종목 뉴스 수집 |
| `scrape_mk_sector_playwright.py` | Playwright 기반 섹터 뉴스 수집 |
| `scrape_hankyung.py` | 한국경제 뉴스 수집 |
| `collect_all.py` | 여러 수집기를 묶어 실행 |
| `summarize.py` | 수집 뉴스 요약 |
| `_test_resummary.py` | 재요약 테스트 보조 |

## 설치

```bash
cd News_Scraper
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Playwright 기반 스크립트를 쓰는 경우 브라우저 설치가 추가로 필요할 수 있다.

```bash
.venv/bin/python -m playwright install chromium
```

## 매일경제 검색 수집 예시

```bash
.venv/bin/python scrape_mk.py \
  --word 삼성전자 \
  --start-date 2026-03-11 \
  --end-date 2026-03-12 \
  --sort accuracy \
  --search-field title \
  --json mk_articles.json
```

매경 검색은 같은 날짜를 `startDate`와 `endDate`에 동시에 넣으면 0건이 나올 수 있다. 특정일 뉴스는 검색 URL에서 `startDate=전날`, `endDate=해당일` 형태로 조회하는 쪽이 안정적이다.

## 메인 파이프라인 연결

수집 결과를 메인 프로젝트에서 쓰려면 최종 원천 뉴스를 `data/samsung_news_raw.pkl` 형식으로 맞춘 뒤 루트에서 아래를 실행한다.

```bash
python scripts/02_prepare_news.py --seed 2
```

그 결과 메인 런타임 입력인 아래 파일이 생성된다.

- `outputs/processed_news.csv`
- `outputs/daily_news_selection.csv`
