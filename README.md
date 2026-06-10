# TwinMarket Korea

LLM 기반 에이전트 100명이 삼성전자(005930) 단일 종목을 거래하는 시장 시뮬레이션 프로젝트.

---

## 변경 기록 (2026-06-09)

- 뉴스 원본 pkl을 루트 `data/`로 정리하고 `outputs/processed_news.csv`, `outputs/daily_news_selection.csv` 생성 흐름을 확인했다.
- `news_interpretation` LLM 단계와 `market_analysis` LLM 단계를 일별 사이클에 연결했다.
- `news_depth`에 따라 Depth 1은 일일 뉴스 본문 최대 3개, Depth 2는 최근 7일 검색 결과와 추가 본문 최대 5개를 context에 반영한다.

## 변경 기록 (2026-06-10)

- `news_depth`를 Depth 0/1/2로 재정의했다. Depth 0은 헤드라인만, Depth 1은 당일 10개 요약 전체, Depth 2는 추가 LLM 기반 검색 결과 10개를 반영한다.
- 시뮬레이션 재실행 시 `sim.db`의 런타임 테이블을 정리하고, 체결 결과 기준으로 `trade_log` 상태를 갱신하도록 수정했다.
- 시뮬레이션 로그는 실행마다 `outputs/logs/current`로 새로 작성되며 이전 로그 폴더는 정리된다.

---

## 추가된 파일 (2026-06-02)

### `scripts/00_fetch_market_data.py`
Yahoo Finance에서 삼성전자 주가 데이터와 매크로 데이터를 수집하는 스크립트.

- 삼성전자(005930.KS): 2025-01-01 ~ 현재
- 지표 계산을 위해 2024-07-01부터 데이터를 받아온 뒤 2025-01-01 이전 행은 제거
- KOSPI 지수 및 USD/KRW 환율도 함께 수집

```bash
python scripts/00_fetch_market_data.py
```

---

### `data/stock_data.csv`
삼성전자 일별 주가 및 기술적 지표. `FundamentalAgent`가 직접 읽어 `sim.db`의 `StockData` 테이블에 적재한다.

| 컬럼 | 설명 |
|------|------|
| `date` | 거래일 (YYYY-MM-DD) |
| `open / high / low / close` | 시가 / 고가 / 저가 / 종가 (원) |
| `adj_close` | 수정 종가 |
| `volume` | 거래량 |
| `pct_chg` | 전일 대비 수익률 |
| `volume_chg` | 전일 대비 거래량 변화율 |
| `ma5 / ma20` | 5일 / 20일 이동평균 |
| `volatility_20d` | 20일 로그수익률 표준편차 |
| `rsi_14` | 14일 RSI |
| `macd / macd_signal / macd_hist` | MACD (12-26-9) |
| `bb_upper / bb_lower / bb_pct` | 볼린저밴드 상단 / 하단 / %B |

---

### `data/macro_data.csv`
KOSPI 지수 및 USD/KRW 환율 일별 데이터. 에이전트 belief 형성의 거시경제 맥락 참고용.

| 컬럼 | 설명 |
|------|------|
| `date` | 거래일 |
| `kospi_close / kospi_pct_chg` | KOSPI 종가 / 전일 대비 수익률 |
| `usdkrw / usdkrw_pct_chg` | USD/KRW 환율 / 전일 대비 변화율 |
