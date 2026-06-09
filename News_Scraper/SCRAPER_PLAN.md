# News Scraper 구현 계획서

> TwinMarket Korea 시뮬레이션용 뉴스 수집 시스템.
> `News_System_Design.md` 기반, `samsung_news_raw.pkl` 생성을 목표로 한다.

---

## 1. 수집 목표

| 카테고리 | 목표량 | 소스 | 수집 방식 |
|----------|--------|------|----------|
| 종목 | 최대 20건/일 | 매일경제(mk.co.kr) 검색 | 키워드 검색, 제목 필터링 |
| 섹터 | 최대 20건/일 | 매일경제(mk.co.kr) 섹션 | 기업 > 반도체·전자 섹션 직접 수집 |
| 경제 | 최대 20건/일 | 한국경제(hankyung.com) 섹션 | 경제 > 거시경제/외환시장 섹션 직접 수집 |

- 당일 뉴스가 목표량에 미달하면 수집된 만큼만 사용 (하한선 없음)
- 수집 기간: **2025-01-01 ~ 현재**

---

## 2. 카테고리별 수집 규칙

### 2-1. 종목 뉴스 (mk.co.kr 검색)

- 검색 엔드포인트: `https://www.mk.co.kr/search`
- **제목 필터 조건**: 아래 키워드 중 하나 이상이 제목에 포함되어야 수집
  ```
  삼성전자 | 삼전 | Samsung
  ```
- 검색 파라미터: `searchField=title`, `sort=desc` (최신순)
- 중복 제거: `article_id` 기준

### 2-2. 섹터 뉴스 (mk.co.kr 섹션)

- 수집 방식: 매일경제 **기업 > 반도체·전자** 섹션 목록 직접 파싱
- 섹션 URL: `https://www.mk.co.kr/news/business/semiconductors-electronics`
- 별도 키워드 검색 없이 해당 섹션의 기사 목록 순서대로 수집
- 본문은 `parse_article()` 그대로 재사용

### 2-3. 경제 뉴스 (hankyung.com 섹션)

- 수집 방식: 한국경제 두 섹션 목록 합산 파싱 (외환시장 제외 — 프리미엄 기사 비중 높음)
- 섹션 URL:
  - 거시경제: `https://www.hankyung.com/economy/macro`
  - 경제 정책: `https://www.hankyung.com/economy/economic-policy`
- 두 섹션을 합쳐서 최대 20건 (각 섹션에서 최신순으로 수집 후 날짜 필터 → 합산 → 상위 20건)
- 본문 추출 셀렉터: hankyung.com 구조에 맞게 별도 구현 필요

---

## 3. 출력 데이터 형식

### 3-1. 원본 수집 결과 — `samsung_news_raw.pkl`

```
pandas DataFrame (pickle)

컬럼:
  id            str   "news_YYYYMMDD_종목_0001" 형식
  title         str   기사 제목
  date          str   "YYYY-MM-DD"
  time          str   "HH:MM"
  category      str   "종목" | "섹터" | "경제"
  body          str   본문 전체
  source        str   "mk" | "hankyung"
  url           str   원문 URL
```

### 3-2. 전처리 결과 — `processed_news.csv`

```
컬럼: id, title, date, time, category, summary(200자 이내)
```

### 3-3. 일별 선정 결과 — `daily_news_selection.csv`

```
컬럼: id, title, date, time, category
일별 10건 선정: 종목 5건 + 섹터 3건 + 경제 2건
```

> 전처리(요약·선정)는 별도 스크립트에서 수행. 스크래퍼는 raw 수집만 담당.

---

## 4. 파일 구조 (목표)

```
News_Scraper/
├── scrape_mk.py              # 기존: mk.co.kr 검색 스크래퍼
├── scrape_mk_sector.py       # 신규: mk.co.kr 섹션 스크래퍼 (섹터)
├── scrape_hankyung.py        # 신규: hankyung.com 섹션 스크래퍼 (경제)
├── collect_all.py            # 신규: 세 스크래퍼 통합 실행 → samsung_news_raw.pkl 생성
├── SCRAPER_PLAN.md           # 이 문서
├── requirements.txt
└── README.md
```

---

## 5. 수집 전략 — 날짜별 처리

```
for date in trading_days(2025-01-01 ~ today):
    종목: mk 검색(삼성전자|삼전|Samsung) → 제목 필터 → 최대 20건
    섹터: mk 섹션 목록 → date 필터 → 최대 20건
    경제: hankyung 섹션 목록 → date 필터 → 최대 20건
    → 합쳐서 하루치 DataFrame row 추가

최종 저장: samsung_news_raw.pkl
```

---

## 6. 미확정 사항 (TBD)

| 항목 | 내용 | 상태 |
|------|------|------|
| mk.co.kr 섹터 섹션 URL | 기업 > 반도체·전자 정확한 URL | ✅ 확인 완료 |
| hankyung.com 경제 섹션 URL | 거시경제 + 경제 정책 (외환시장 제외) | ✅ 확인 완료 |
| hankyung 본문 셀렉터 | `div.article-body#articletxt` | ✅ 확인 완료 |
| 페이지네이션 처리 | `?page=N` 방식, target_date 이전 기사 등장 시 중단 | ✅ 구현 완료 |
| 요청 간격(delay) | 카테고리 간 1.5초, 날짜 간 2.0초 | ✅ 구현 완료 |

---

## 7. hankyung.com 섹션 페이지-날짜 매핑 (2026-06-02 기준)

> 과거 날짜 수집 시 몇 페이지까지 넘겨야 하는지 빠르게 확인용.
> 날짜가 오래될수록 더 높은 페이지 번호. 약 1달에 10~20페이지 증가.

### 거시경제 (`/economy/macro`)
| 페이지 | 날짜 범위 |
|--------|----------|
| 1 | 2026-06-02 |
| 10 | 2026-02-20 ~ 2026-02-26 |
| 20 | 2025-11-26 ~ 2025-12-02 |
| 30 | 2025-09-01 ~ 2025-09-10 |
| 40 | 2025-06-23 ~ 2025-06-30 |
| 50 | 2025-03-20 ~ 2025-03-26 |
| 60 | 2025-01-16 ~ 2025-01-24 |
| **62** | **2025-01-01** ← 시뮬레이션 시작일 |
| 70 | 2024-09-12 (max_page=72, 이후 데이터 없음) |

### 경제정책 (`/economy/economic-policy`)
| 페이지 | 날짜 범위 |
|--------|----------|
| 1 | 2026-06-02 |
| 60 | 2025-11-30 ~ 2025-12-02 |
| 100 | 2025-07-22 ~ 2025-07-24 |
| 120 | 2025-05-09 ~ 2025-05-14 |
| 131 | 2025-03-24 ~ 2025-03-27 |
| **152** | **2025-01-01** ← 시뮬레이션 시작일 |
| max_page=160 | 여유 설정 |

> 이 표는 시간이 지나면 오래됩니다. 매핑이 맞지 않으면 `debug_hankyung.py`로 재측정.

---
