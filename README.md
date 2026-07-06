# TwinMarket Korea

삼성전자(`005930`)를 대상으로 LLM 기반 개인 투자자 에이전트들이 뉴스, 시장 정보, 포트폴리오, 커뮤니티 반응을 읽고 매수/매도 주문을 제출하는 시장 시뮬레이션 프로젝트입니다.

현재 코드의 기준 흐름은 다음과 같습니다.

```text
원천 데이터 준비
  -> 100명 페르소나 선발
  -> 뉴스 전처리 및 일별 뉴스 선택
  -> 주가 데이터 DB 적재
  -> 초기 포트폴리오와 초기 belief 생성
  -> am/pm 의사결정 시뮬레이션
  -> 로그, PDF 리포트, 실제 개인 투자자 순거래 방향 검증
```

## 문서

| 문서 | 역할 |
| --- | --- |
| `README.md` | 설치, 데이터 준비, 실행, 검증 방법 |
| `ARCHITECTURE.md` | 현재 코드 구조와 주요 설계 결정 |
| `Code_Status.md` | 유지해야 할 핵심 구현 결정 |
| `fake_news_injection_experiment.md` | 가짜뉴스 주입 실험 설계 |
| `validation/README.md` | 실제 투자자 순거래 방향 검증 |
| `News_Scraper/README.md` | 뉴스 수집 보조 스크립트 |

## 디렉터리 구조

```text
.
├── config.py
├── data/                         # 원천 데이터
├── outputs/
│   ├── sys_100.db                # 선발된 에이전트 DB
│   ├── sim.db                    # 시뮬레이션 상태 DB
│   ├── processed_news.csv        # 정제된 전체 뉴스
│   ├── daily_news_selection.csv  # 일별 노출 뉴스 목록
│   ├── logs/                     # 실행별 로그
│   └── reports/                  # PDF 리포트
├── prompts/                      # LLM 프롬프트
├── scripts/                      # 단계별 실행 스크립트
├── twinmarket_kr/                # 시뮬레이션 패키지
├── validation/                   # 실제 투자자 순거래 방향 검증
└── News_Scraper/                 # 뉴스 수집 보조 도구
```

## 환경 설정

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

LLM 호출은 OpenRouter API를 사용합니다. 프로젝트 루트에 `.env`를 만들고 값을 설정합니다.

```bash
OPENROUTER_API_KEY=...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openai/gpt-4o
OPENROUTER_COMMUNITY_MODEL=openai/gpt-4o-mini
```

일부 데이터 수집/리포트 스크립트는 `pandas`, `yfinance`, `reportlab`, `matplotlib` 등 추가 패키지가 필요할 수 있습니다.

## 데이터 준비

### 1. 시장 데이터 수집

```bash
python scripts/00_fetch_market_data.py
```

생성 파일:

- `data/stock_data.csv`
- `data/macro_data.csv`

### 2. 100명 에이전트 구성

```bash
python scripts/01_build_persona.py
```

생성 파일:

- `outputs/sys_100.db`
- `outputs/persona_validation_report.json`

### 3. 뉴스 전처리

```bash
python scripts/02_prepare_news.py --seed 2
```

생성 파일:

- `outputs/processed_news.csv`
- `outputs/daily_news_selection.csv`

기본 일별 뉴스 선정 목표는 종목 5개, 섹터 3개, 경제 2개입니다. 시간대별 `am/pm` 5:5 배분은 보장하지 않습니다.

### 4. 주가 데이터 DB 적재

```bash
python scripts/03_load_stock_data.py
```

`data/stock_data.csv`를 `outputs/sim.db`의 `StockData` 테이블에 적재합니다.

### 5. 초기 포트폴리오 생성

```bash
python scripts/02_init_memory.py
```

`portfolio_state`의 `turn=0` 초기 상태를 생성합니다.

### 6. 초기 belief 생성

LLM 없이 템플릿 기반으로 생성:

```bash
python scripts/04_generate_initial_beliefs.py --offline
```

LLM으로 생성:

```bash
python scripts/04_generate_initial_beliefs.py
```

## 시뮬레이션 실행

대표 실행:

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
| `--max-agents` | 실행할 에이전트 수 |
| `--max-days` | 실행할 거래일 수 |
| `--start-date`, `--end-date` | 실행 기간 |
| `--concurrency` | LLM 호출 동시성 |
| `--random-agents` | 무작위 에이전트 샘플 |
| `--balanced-depths` | Depth 0/1/2 균형 샘플 |
| `--seed` | 샘플 재현용 seed |
| `--information-mode` | 정보 컷오프 방식 |
| `--use-fake-news-injection` | injection 뉴스 CSV를 사용 |
| `--fake-news-mode` | `on`이면 fake row 노출, `off`이면 `is_fake=true` row 숨김 |
| `--no-logs` | 상세 로그 비활성화 |

`--information-mode`:

- `pre_close_cutoff`: 기본값. `am`은 전 거래일 15:30 이후부터 당일 08:59까지의 뉴스, `pm`은 당일 08:59 이후부터 15:30까지의 뉴스를 사용합니다.
- `prior_close`: 전일 시장 데이터와 전일까지의 뉴스만 사용합니다.
- `same_day`: 당일 시장 데이터와 당일 뉴스를 사용합니다.

현재 주문 결정 공간은 `buy_sell_only`입니다.

가짜뉴스 주입 CSV를 쓰면서 에이전트에게 가짜뉴스를 노출하려면:

```bash
python scripts/05_run_simulation.py --use-fake-news-injection --fake-news-mode on
```

같은 injection CSV를 쓰되 가짜뉴스 row를 숨기려면:

```bash
python scripts/05_run_simulation.py --use-fake-news-injection --fake-news-mode off
```

`--use-fake-news-injection`만 지정하면 기존 동작과 같게 `--fake-news-mode on`으로 처리됩니다.

## 뉴스 Depth

| Depth | 동작 |
| --- | --- |
| 0 | 선택 뉴스 헤드라인 중심 |
| 1 | 선택 뉴스 요약 본문까지 반영 |
| 2 | Depth 1 정보에 더해 LLM 키워드 기반 추가 뉴스 검색 |

Depth 2 검색은 `outputs/processed_news.csv`의 뉴스 풀을 사용합니다.

## 커뮤니티

커뮤니티 기능은 `config.py`에서 제어합니다.

```python
ENABLE_COMMUNITY = True
ENABLE_COMMUNITY_POSTING = True
ENABLE_COMMUNITY_READING = True
```

커뮤니티는 매일 `pm` 체결 이후 실행됩니다.

- Depth 1 이상 에이전트가 게시글을 작성할 수 있습니다.
- 에이전트는 게시글 후보를 읽고 반응합니다.
- Best 게시글과 읽기 로그는 다음 의사결정 컨텍스트에 반영됩니다.

## 로그와 리포트

시뮬레이션 로그는 `outputs/logs/<run_id>/`에 생성됩니다.

| 파일 | 내용 |
| --- | --- |
| `run_metadata.json` | 실행 옵션과 에이전트 목록 |
| `run_complete.json` | 완료 상태 |
| `agent_turns.csv` / `.jsonl` | 에이전트별 컨텍스트, belief, 분석, 결정 |
| `submitted_orders.csv` | 제출 주문 |
| `exchange_fills.csv` | 체결 내역 |
| `daily_exchange_summary.csv` | 일별 체결 요약 |
| `portfolio_updates.jsonl` | 포트폴리오 상태 |
| `community_*.csv` / `.jsonl` | 커뮤니티 로그 |
| `errors.jsonl` | 에러 로그 |

리포트 생성:

```bash
python scripts/generate_run_report_pdf.py \
  --run-dir outputs/logs/simulation_YYYYMMDD_HHMMSS \
  --output outputs/reports/simulation_YYYYMMDD_HHMMSS_report.pdf

python scripts/generate_community_report_pdf.py \
  --run-dir outputs/logs/simulation_YYYYMMDD_HHMMSS \
  --output outputs/reports/simulation_YYYYMMDD_HHMMSS_community_report.pdf

python scripts/generate_deep_analysis_report.py \
  --run-id simulation_YYYYMMDD_HHMMSS
```

가짜뉴스 노출 및 영향 보고서:

```bash
python scripts/generate_fake_news_report_pdf.py \
  --run-dir outputs/logs/simulation_FAKE_RUN \
  --output outputs/reports/fake_news_impact_simulation_FAKE_RUN.pdf
```

Baseline 실행과 비교하려면:

```bash
python scripts/generate_fake_news_report_pdf.py \
  --run-dir outputs/logs/simulation_FAKE_RUN \
  --baseline-run-dir outputs/logs/simulation_BASELINE_RUN \
  --output outputs/reports/fake_news_impact_compare.pdf
```

보고서는 PDF와 함께 `.summary.json`, `.exposures.csv`를 생성합니다. `agent_turns` 로그의 `fake_news_audit`를 기준으로 어떤 가짜뉴스가 어떤 에이전트에게 기본 노출/본문 읽기/Depth 2 검색/selected 뉴스로 잡혔는지 집계하고, baseline이 있으면 공통 에이전트와 날짜 기준으로 수익률, 순체결 수량, 주문 변경을 비교합니다.

## 검증

실제 개인 투자자 순거래 방향과 시뮬레이션 순거래 방향을 비교합니다.

```bash
python validation/validate_trading_direction.py \
  --run-dir outputs/logs/simulation_YYYYMMDD_HHMMSS
```

산출물은 `validation/outputs/<run_id>/`에 생성됩니다.

## 빠른 점검

데이터 준비 상태:

```bash
python scripts/99_validate.py
```

커뮤니티 포함 짧은 smoke test:

```bash
python scripts/06_run_community_smoke_test.py \
  --max-agents 3 \
  --max-days 2 \
  --concurrency 1
```

## 주의 사항

- 시뮬레이션 시작 시 `outputs/sim.db`의 런타임 테이블 일부가 초기화됩니다.
- 실행 날짜는 `StockData`와 `daily_news_selection.csv`에 공통으로 존재하는 거래일만 사용합니다.
- `pre_close_cutoff`와 `prior_close`는 전일 데이터가 필요하므로 첫 거래일이 제외될 수 있습니다.
- LLM 비용과 속도는 에이전트 수, 거래일 수, Depth 2 비율, 커뮤니티 설정에 크게 좌우됩니다.
