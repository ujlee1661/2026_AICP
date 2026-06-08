# TwinMarket Korea

LLM 기반 에이전트 100명이 삼성전자(005930) 단일 종목을 거래하는 시장 시뮬레이션 프로젝트.

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
