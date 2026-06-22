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

## 변경 기록 (2026-06-11)

- Depth 2 에이전트는 `search_needed` 판단값과 무관하게 `depth2_search_keywords`에 해당하는 `search_keywords`가 있으면 항상 최근 7일 뉴스 풀에서 추가 검색을 수행하도록 수정했다.
- `prompts/news_agent.txt`에서 Depth 2 추가 검색을 선택 행동이 아닌 기본 행동으로 명시하고, `search_needed=false`인 경우에도 검색 키워드 3~8개를 반드시 생성하도록 안내했다.
- `depth2_flow.step2_pre_search_thinking.search_needed`는 검색 실행 제어값이 아니라 판단 기록용 필드로 유지된다.

## 변경 기록 (2026-06-17)

- `outputs/sys_100.db`의 기존 `agents` 테이블에서 `news_depth`와 `persona_prompt`만 갱신했다.
- `ini_cash`, `strategy`, `bh_annual_turnover_category`, `trade_count_category`, `age_group`, `user_type` 점수를 합산해 총점 내림차순으로 정렬하고, 경계 동점은 `ini_cash` 상위, `strategy=value`, `trade_count_category` 낮은 순서로 배정했다.
- 최종 분포는 Depth 0 정확히 30명, Depth 1 정확히 55명, Depth 2 정확히 15명이다.

## 변경 기록 (2026-06-18)

- 거래 수수료율을 거래대금의 0.05%(`config.COMMISSION_RATE = 0.0005`)로 적용한다.
- `ExchangeAgent`는 체결된 에이전트 거래마다 `executed_price * executed_quantity * COMMISSION_RATE`를 `fee`로 계산한다.
- 합성 잔차 유동성인 `COUNTERSIDE` 거래는 수수료 대상에서 제외한다.
- `MemoryAgent`는 매수 시 `가격 * 수량 + 수수료`만큼 현금을 차감하고, 매도 시 `가격 * 수량 - 수수료`만큼 현금을 증가시키며 실현손익에서도 수수료를 차감한다.
- `trade_log`와 `exchange_fills.csv`에는 체결별 수수료가 기록된다.

## 변경 기록 (2026-06-22)

- `validation/` 폴더를 추가하고 삼성전자 실제 투자자별 순거래 데이터 `data_trading_value.csv`, `data_trading_volume.csv`를 해당 폴더로 이동했다.
- `validation/validate_trading_direction.py`는 시뮬레이션 로그의 LLM 에이전트 일별 순매수/순매도 방향을 실제 개인 투자자(`Individuals`) 순거래 방향과 비교한다.
- 검증은 거래대금(value)과 거래량(volume)을 모두 산출하며, `COUNTERSIDE` 흐름도 실제 기관, 외인, 기타법인 순거래 방향과 보조 비교한다.
- 방향 일치율은 원본 순거래값의 부호 기준으로 유지하고, 양상 비교는 `max_abs`, `z_score`, `cumulative_max_abs` 정규화 지표를 함께 산출한다.
- 검증 실행 결과는 `validation/outputs/<run_id>/` 아래에 `daily_comparison_value.csv`, `daily_comparison_volume.csv`, `normalized_comparison_value.csv`, `normalized_comparison_volume.csv`, `summary_metrics.json`, `validation_report.pdf`로 생성된다.

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
