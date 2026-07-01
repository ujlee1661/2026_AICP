# TwinMarket Korea

삼성전자(`005930`) 단일 종목을 대상으로, LLM 기반 개인 투자자 에이전트들이 뉴스와 시장 정보, 포트폴리오 상태, 커뮤니티 반응을 읽고 주문을 제출하는 시장 시뮬레이션 프로젝트입니다.

현재 코드는 다음 흐름을 기준으로 동작합니다.

```text
원천 데이터 준비
  -> 페르소나 100명 구성
  -> 뉴스 전처리 및 일별 뉴스 선택
  -> 주가 데이터 DB 적재
  -> 초기 포트폴리오와 초기 belief 생성
  -> 일별 시뮬레이션 실행
  -> 로그, PDF 리포트, 실제 개인 투자자 순거래 방향 검증
```

## 디렉터리 구조

```text
.
├── config.py                         # 전역 경로, 종목, 수수료, 커뮤니티, LLM 설정
├── data/                             # 원천 데이터와 고정 입력 파일
├── outputs/
│   ├── sys_100.db                    # 선별된 100명 에이전트 DB
│   ├── sim.db                        # 시뮬레이션 상태 DB
│   ├── processed_news.csv            # 정제된 뉴스 전체
│   ├── daily_news_selection.csv      # 일별 선택 뉴스
│   ├── logs/                         # 실행별 상세 로그
│   └── reports/                      # PDF 보고서
├── scripts/                          # 단계별 실행 스크립트
├── twinmarket_kr/                    # 시뮬레이션 패키지
├── validation/                       # 실제 투자자별 순거래 방향 검증
└── News_Scraper/                     # 뉴스 수집 보조 스크립트
```

## 주요 입력과 출력

| 구분 | 경로 | 설명 |
| --- | --- | --- |
| 페르소나 풀 | `data/sys_1000.csv` | 후보 개인 투자자 페르소나 |
| 고정 슬롯 | `data/fixed_slots.csv` | 100명 선별에 사용할 분포 슬롯 |
| 원천 뉴스 | `data/samsung_news_raw.pkl` | 뉴스 전처리 입력 |
| 주가 데이터 | `data/stock_data.csv` | 삼성전자 OHLCV 및 기술적 지표 |
| 100명 에이전트 DB | `outputs/sys_100.db` | `agents` 테이블 |
| 시뮬레이션 DB | `outputs/sim.db` | belief, 포트폴리오, 주문, 체결, 커뮤니티 테이블 |
| 실행 로그 | `outputs/logs/<run_id>/` | CSV/JSONL 상세 로그 |
| 최신 실행 포인터 | `outputs/logs/current` | 최신 run directory를 가리키는 링크 또는 폴더 |

## 환경 설정

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

LLM 호출은 OpenRouter API를 사용합니다. 프로젝트 루트에 `.env`를 만들고 필요한 값을 설정합니다.

```bash
OPENROUTER_API_KEY=...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openai/gpt-4o
OPENROUTER_COMMUNITY_MODEL=openai/gpt-4o-mini
```

참고: `requirements.txt`에는 현재 LLM 클라이언트 중심의 최소 의존성이 들어 있습니다. 시장 데이터 수집, 리포트 생성, 검증 스크립트를 새 환경에서 실행하려면 `pandas`, `yfinance`, `reportlab` 등이 추가로 필요할 수 있습니다.

## 전체 실행 순서

### 1. 시장 데이터 수집

Yahoo Finance에서 삼성전자 주가, KOSPI, USD/KRW 데이터를 받아옵니다.

```bash
python scripts/00_fetch_market_data.py
```

생성 파일:

- `data/stock_data.csv`
- `data/macro_data.csv`

### 2. 100명 에이전트 구성

`data/sys_1000.csv` 후보군과 `data/fixed_slots.csv`를 이용해 100명 에이전트를 선별합니다.

```bash
python scripts/01_build_persona.py
```

생성 파일:

- `outputs/sys_100.db`
- `outputs/persona_validation_report.json`

### 3. 뉴스 전처리

원천 뉴스 pkl을 정제하고, 일별 최대 10개 뉴스 묶음을 만듭니다. 기본 카테고리 목표는 종목 5개, 섹터 3개, 경제 2개입니다.

```bash
python scripts/02_prepare_news.py --seed 2
```

생성 파일:

- `outputs/processed_news.csv`
- `outputs/daily_news_selection.csv`

### 4. 주가 데이터 DB 적재

```bash
python scripts/03_load_stock_data.py
```

`data/stock_data.csv`를 `outputs/sim.db`의 `StockData` 테이블에 적재합니다.

### 5. 초기 포트폴리오 생성

```bash
python scripts/02_init_memory.py
```

각 에이전트의 초기 현금 기준으로 `portfolio_state`의 `turn=0` 상태를 생성합니다.

### 6. 초기 belief 생성

LLM 없이 템플릿 기반 초기 belief를 만들려면:

```bash
python scripts/04_generate_initial_beliefs.py --offline
```

LLM으로 생성하려면:

```bash
python scripts/04_generate_initial_beliefs.py
```

## 시뮬레이션 실행

대표 실행 예시는 다음과 같습니다.

```bash
python scripts/05_run_simulation.py \
  --max-agents 50 \
  --balanced-depths \
  --seed 2 \
  --start-date 2026-02-27 \
  --end-date 2026-05-12 \
  --concurrency 8
```

주요 옵션:

| 옵션 | 설명 |
| --- | --- |
| `--max-agents` | 실행할 에이전트 수. 미지정 시 전체 사용 |
| `--max-days` | 실행할 거래일 수 |
| `--start-date`, `--end-date` | 실행 기간 필터 |
| `--concurrency` | 에이전트 LLM 호출 동시성 |
| `--random-agents` | 앞에서부터 자르지 않고 무작위 샘플 |
| `--balanced-depths` | Depth 0/1/2를 최대한 균형 있게 샘플 |
| `--seed` | 무작위 샘플 재현용 seed |
| `--information-mode` | 의사결정 시점의 정보 절단 방식 |
| `--no-logs` | 상세 로그 생성을 끔 |

`--information-mode` 값:

- `pre_close_cutoff`: 전일 장마감 이후부터 당일 주문 마감 시점까지의 뉴스와 전일 시장 데이터를 사용합니다.
- `prior_close`: 전일 시장 데이터와 전일까지의 뉴스만 사용합니다.
- `same_day`: 당일 시장 데이터와 당일 뉴스를 사용합니다.

현재 주문 결정 공간은 `buy_sell_only`입니다. 즉, LLM 의사결정은 매수 또는 매도 주문 제출을 기본으로 하며, 제약 조건상 주문이 불가능할 때만 미제출 상태가 됩니다.

## 일별 코드 흐름

`scripts/05_run_simulation.py`는 `twinmarket_kr.simulation.run_simulation()`을 호출합니다. 하루 거래일마다 흐름은 다음과 같습니다.

1. `MemoryAgent`가 이전 belief, 직전 포트폴리오, 마지막 행동 이유를 읽습니다.
2. `FundamentalAgent`가 기준일의 시장 피처를 읽습니다.
3. `NewsAgent`가 에이전트의 `news_depth`에 맞는 뉴스 컨텍스트를 구성합니다.
4. Depth 2 에이전트는 추가 검색 키워드를 만들고, 최근 뉴스 풀에서 관련 뉴스를 더 읽습니다.
5. LLM이 뉴스 해석(`interpret_news`)을 생성합니다.
6. LLM이 belief를 업데이트하고 `belief_history`에 저장합니다.
7. LLM이 시장 분석과 주문 결정을 생성합니다.
8. 주문 가능 수량, 현금, 보유 수량 제약을 적용해 주문을 구성합니다.
9. `ExchangeAgent`가 일별 주문을 실제 종가에 앵커링해 체결합니다.
10. 수수료를 반영해 `trade_log`, `TradingDetails`, `portfolio_state`를 갱신합니다.
11. 커뮤니티 기능이 켜져 있으면 게시글 작성, 읽기, 반응, Best 글 선정, 다음 날 community thinking 저장을 수행합니다.

수수료율은 `config.COMMISSION_RATE = 0.0005`입니다. 합성 잔차 유동성 주체인 `COUNTERSIDE`는 수수료 대상에서 제외됩니다.

## 뉴스 Depth

| Depth | 동작 |
| --- | --- |
| 0 | 일별 선택 뉴스의 헤드라인 중심 컨텍스트 |
| 1 | 일별 선택 뉴스의 요약 본문까지 반영 |
| 2 | 기본 뉴스 컨텍스트에 더해 LLM 키워드 기반 추가 뉴스 검색 결과를 반영 |

Depth 1 이상 에이전트는 커뮤니티 게시글 작성과 읽기 대상이 됩니다. 커뮤니티 읽기 개수는 `config.py`의 `COMMUNITY_DEPTH1_READ_LIMIT`, `COMMUNITY_DEPTH2_READ_LIMIT`로 제어합니다.

## 거래 체결 방식

`ExchangeAgent`는 매수/매도 지정가 주문을 모아 종목별로 처리합니다.

- 초기 `config.N_WARMUP` 거래일은 warmup 체결 로직을 사용합니다.
- 이후에는 실제 종가를 기준 가격으로 삼고, 전일 종가 대비 `config.CIRCUIT_BREAKER` 범위 안에서 체결합니다.
- 수급 불균형은 `COUNTERSIDE` 주문을 추가해 실제 종가 앵커 체결을 보정합니다.
- 체결 결과는 `TradingDetails`와 실행 로그의 `exchange_fills.csv`, `daily_exchange_summary.csv`에 남습니다.

## 커뮤니티 기능

커뮤니티는 `config.py`에서 제어합니다.

```python
ENABLE_COMMUNITY = True
ENABLE_COMMUNITY_POSTING = True
ENABLE_COMMUNITY_READING = True
```

커뮤니티 단계는 매일 체결 이후 실행됩니다.

- Depth 1 이상 에이전트가 매매 결과와 당일 판단을 바탕으로 글을 쓸 수 있습니다.
- 에이전트별 수익률, 자산, 영향력 기준으로 뱃지를 계산합니다.
- 에이전트는 보이는 게시글 후보 중 일부를 읽고 반응합니다.
- 일별 Best 게시글을 선정하고, 다음 날 의사결정 컨텍스트에 사용할 community log를 저장합니다.

## 로그와 리포트

시뮬레이션을 실행하면 `outputs/logs/<run_id>/`에 상세 로그가 생성됩니다.

주요 로그:

| 파일 | 내용 |
| --- | --- |
| `run_metadata.json` | 실행 옵션과 에이전트 목록 |
| `run_complete.json` | 완료 상태와 로그 경로 |
| `agent_turns.csv` / `.jsonl` | 에이전트별 컨텍스트, belief, 분석, 주문 결정 |
| `submitted_orders.csv` | 제출 주문 |
| `exchange_fills.csv` | 체결 내역 |
| `daily_exchange_summary.csv` | 일별 주문/체결 요약 |
| `portfolio_updates.jsonl` | 체결 후 포트폴리오 상태 |
| `community_*.csv` / `.jsonl` | 커뮤니티 게시글, 선택 화면, 반응, Best 글, 로그 |
| `errors.jsonl` | 에이전트 턴 오류 |

최신 실행을 PDF로 정리하려면:

```bash
python scripts/generate_run_report_pdf.py
python scripts/generate_community_report_pdf.py
```

특정 실행 로그를 지정하려면:

```bash
python scripts/generate_run_report_pdf.py \
  --run-dir outputs/logs/simulation_YYYYMMDD_HHMMSS \
  --output outputs/reports/simulation_YYYYMMDD_HHMMSS_report.pdf

python scripts/generate_community_report_pdf.py \
  --run-dir outputs/logs/simulation_YYYYMMDD_HHMMSS \
  --output outputs/reports/simulation_YYYYMMDD_HHMMSS_community_report.pdf
```

## 검증

실제 개인 투자자 순거래 방향과 시뮬레이션의 LLM 에이전트 순거래 방향을 비교합니다.

```bash
python validation/validate_trading_direction.py
```

특정 실행 로그 검증:

```bash
python validation/validate_trading_direction.py \
  --run-dir outputs/logs/simulation_YYYYMMDD_HHMMSS
```

입력:

- `validation/data_trading_value.csv`
- `validation/data_trading_volume.csv`
- `outputs/logs/<run_id>/exchange_fills.csv`

산출물은 `validation/outputs/<run_id>/`에 생성됩니다.

- `daily_comparison_value.csv`
- `daily_comparison_volume.csv`
- `normalized_comparison_value.csv`
- `normalized_comparison_volume.csv`
- `summary_metrics.json`
- `validation_report.pdf`

기본 검증은 LLM 에이전트 전체 순거래 방향과 실제 `Individuals` 방향을 비교합니다. 보조 검증은 `COUNTERSIDE` 흐름을 기관, 외국인, 기타법인 흐름과 비교합니다.

## 빠른 점검

데이터 준비 상태를 요약 확인하려면:

```bash
python scripts/99_validate.py
```

커뮤니티 포함 2일 smoke test와 전체 입출력 묶음 로그를 만들려면:

```bash
python scripts/06_run_community_smoke_test.py \
  --max-agents 3 \
  --max-days 2 \
  --concurrency 1
```

## 핵심 모듈

| 모듈 | 역할 |
| --- | --- |
| `twinmarket_kr/simulation.py` | 전체 실행 루프, 일별 주문 처리, 포트폴리오 갱신, 커뮤니티 단계 |
| `twinmarket_kr/core/daily_cycle.py` | 에이전트 1명의 하루 의사결정 흐름 |
| `twinmarket_kr/core/collect_context.py` | belief, 포트폴리오, 뉴스, 시장, 커뮤니티 컨텍스트 수집 |
| `twinmarket_kr/agents/news_agent.py` | 뉴스 전처리, 일별 뉴스 선택, Depth별 뉴스 컨텍스트, 추가 검색 |
| `twinmarket_kr/agents/fundamental_agent.py` | 주가 데이터 적재와 시장 피처 조회 |
| `twinmarket_kr/agents/memory_agent.py` | belief, 포트폴리오, 거래 로그 저장과 조회 |
| `twinmarket_kr/agents/exchange_agent.py` | 주문 체결, 수수료 계산, 체결 DB 저장 |
| `twinmarket_kr/community/` | 게시글 작성, 읽기, 반응, 뱃지, community thinking |
| `twinmarket_kr/llm/` | OpenRouter 클라이언트와 LLM 프롬프트 단계 |
| `twinmarket_kr/run_logger.py` | 실행별 CSV/JSONL 로그 저장 |

## 주의 사항

- 시뮬레이션 시작 시 `outputs/sim.db`의 실행 중 생성 데이터가 초기화됩니다. `StockData`, 초기 belief, 초기 포트폴리오(`turn=0`)는 유지되고, 체결/거래 로그와 `turn>0` belief/포트폴리오/커뮤니티 로그가 새 실행 기준으로 정리됩니다.
- 시뮬레이션 날짜는 `StockData`와 `daily_news_selection.csv`에 공통으로 존재하는 거래일만 사용합니다.
- `pre_close_cutoff`와 `prior_close` 모드는 전일 시장 데이터가 필요하므로 첫 거래일은 실행 대상에서 제외될 수 있습니다.
- LLM 호출 비용과 속도는 에이전트 수, 거래일 수, `--concurrency`, Depth 2 비율, 커뮤니티 설정에 크게 영향을 받습니다.
