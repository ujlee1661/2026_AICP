# Code_Status.md — 임의 결정 기록

> 이 문서는 **4개 설계 문서에 명시되지 않아 구현 중 임의로 정한 결정**을 기록한다.
> 설계서에 답이 있는 사항은 여기 적지 않는다(설계서가 진실의 원천).
> 각 항목은 **무엇을 / 왜 / 영향 / 되돌릴 때** 형식으로 남긴다.
> 코드를 짜다가 설계서에 없는 선택을 할 때마다 이 문서에 한 줄이라도 추가한다.

---

## 기록 형식

```
### [ID] 제목  (Step N, YYYY-MM-DD)
- 무엇을: 어떤 결정을 내렸는가
- 왜: 설계서에 왜 없었고, 왜 이렇게 정했는가
- 영향: 어떤 모듈/동작에 영향을 주는가
- 되돌릴 때: 나중에 바꾸려면 무엇을 고치면 되는가
```

---

## 사전 식별된 결정 (착수 전 미리 합의)

아래는 Code_Plan 수립 단계에서 이미 드러난, 구현 시 따를 결정들이다. 해당 Step에 도달하면 실제 값과 함께 확정한다.

### [D-01] LLM 백엔드 = OpenRouter (OpenAI 호환), 모델명은 .env  (Step 0)
- 무엇을: LLM 호출은 OpenRouter(OpenAI 호환) 클라이언트로 하고, 모델명은 `.env`의 `OPENROUTER_MODEL`로 주입식 지정한다.
- 왜: 설계서는 LLM 제공자를 명시하지 않음. 기존 프로젝트 config 관례(api_key/model_name/base_url)와 사용자 지시(OpenRouter + .env)를 따름.
- 영향: `twinmarket_kr/llm/client.py`, 모든 LLM 호출(belief/decision/news tool calling).
- 되돌릴 때: `client.py`의 클라이언트 초기화부와 `.env` 키만 교체. 모델 교체는 `.env` 한 줄.

### [D-02] 시뮬레이션 상태 저장소 = SQLite (outputs/sim.db)  (Step 0)
- 무엇을: belief_history / portfolio_state / trade_log / StockData / TradingDetails를 단일 SQLite `sim.db`에 둔다. 선발 결과는 `outputs/sys_100.db`.
- 왜: 설계서는 "이렇게 기록되어야 한다"는 참고 스키마만 제시. 기존 sys_*.db(SQLite) 관례와 일관성·단순성 위해 SQLite 선택.
- 영향: `db/schema.py`, `db/connection.py`, Memory/Exchange Agent.
- 되돌릴 때: connection 계층만 교체하면 Postgres 등으로 이전 가능(스키마 동일).

### [D-03] 원본 sys_1000.db는 읽기 전용  (Step 1)
- 무엇을: `data/sys_1000.db`는 절대 수정하지 않고, 선발 결과만 `outputs/sys_100.db`에 신규 기록.
- 왜: 풀 데이터 보존. 재현성 확보.
- 영향: `persona/select.py`.
- 되돌릴 때: 해당 없음(보존 원칙 유지 권장).

### [D-04] Fundamental 파생지표 계산 (ma20 / volatility_20d / volume_chg)  (Step 3)
- 무엇을: `stock_data.csv`에 `ma_hfq_5/10/30`만 있고 `ma20`이 없음. `ma20`·`volatility_20d`·`volume_chg`는 close 시계열로 파생 계산한다(ma20=20일 단순이동평균, volatility_20d=20일 로그수익률 표준편차, volume_chg=전일 대비 거래량 변화율).
- 왜: 설계서(Overall §6)는 ma20 등을 요구하지만 원본 데이터 컬럼과 불일치.
- 영향: `agents/fundamental_agent.py`.
- 되돌릴 때: stock_data.csv에 해당 컬럼이 생기면 파생 계산을 직접 조회로 교체.
- ※ 실제 컬럼명/존재 여부는 Step 3에서 데이터 확인 후 확정.

### [D-05] News 일일 중요도 계산 = 휴리스틱  (Step 4a)
- 무엇을: 하루 후보 30건 → 일일 10건(종목5/섹터3/경제2) 선정 시 중요도를 휴리스틱(삼성/반도체/거시 키워드 빈도 + 카테고리 가중 + 발행시각)으로 계산한다.
- 왜: News 설계서는 "중요도를 계산한다"만 명시하고 구체 알고리즘 미제시.
- 영향: `scripts/02_prepare_news.py`.
- 되돌릴 때: 중요도 함수만 교체(예: 가격충격 기반·LLM 스코어링).

### [D-06] search_news는 키워드 기반(임베딩 미사용)  (Step 4c)
- 무엇을: `search_news`는 최근 7일 뉴스에서 키워드 중복 등장 수로 점수화·정렬한다. 의미검색(임베딩)은 쓰지 않는다.
- 왜: News 설계 §4.2가 키워드 매칭 방식으로 명시(의미유사도 비의존). 임베딩 인프라 불필요 → 단순화.
- 영향: `agents/news_agent.py`, `.env`의 EMBED_MODEL 비활성.
- 되돌릴 때: 의미검색 필요 시 임베딩 인덱스 추가.

### [D-07] Thinking Depth 부여 방식  (Step 4d)
- 무엇을: 에이전트별 Depth(1/2)는 sys_100 스키마에 없으므로 별도 부여한다. 분포 비율은 config 파라미터로 두고, 선발 후 결정적 시드로 할당(재현성).
- 왜: News 설계는 Depth를 페르소나 속성이라 하지만 Persona 설계의 agents 스키마엔 Depth 컬럼이 없음.
- 영향: `config.py`(Depth 비율), 페르소나 로드부.
- 되돌릴 때: sys_100 스키마에 depth 컬럼을 추가하면 그쪽을 우선 사용.

### [D-08] 100명 LLM 호출 = async 배치  (Step 9)
- 무엇을: 하루 100명×2콜을 비동기 배치로 처리(동시성 상한은 config).
- 왜: 설계서 미명시. 처리량·시간 위해. (원본도 비동기 사용)
- 영향: `simulation.py`, `llm/client.py`(async).
- 되돌릴 때: 동시성 상한을 1로 두면 순차 실행.

### [D-09] 실험 기간·거래 상수 config화  (Step 0)
- 무엇을: 실험 start/end date, 수수료율, 서킷브레이커(±30%), Phase 경계(N_WARMUP=3, N_TRANSITION=4), ini_cash 티어(1억/10억)를 `config.py`에 둔다.
- 왜: 데이터 가용 기간·KRX 규칙에 맞춰 조정 가능해야 함. (Matching §3 기본값 채택)
- 영향: 전 모듈.
- 되돌릴 때: config.py 값만 수정.

---

## 구현 중 추가 결정 (Step 진행하며 누적)

### [D-10] 제공 입력 sys_1000은 CSV로 처리  (Step 1, 2026-06-02)
- 무엇을: 원 계획의 `data/sys_1000.db` 대신 사용자가 제공한 `sys_1000.csv`를 `data/sys_1000.csv`로 두고, pool 로더가 SQLite `Profiles`와 CSV를 모두 지원하도록 구현했다.
- 왜: 현재 작업 폴더에는 `sys_1000.db`가 없고 `sys_1000.csv`만 첨부되어 있다.
- 영향: `twinmarket_kr/persona/select.py`의 `load_pool()`.
- 되돌릴 때: `data/sys_1000.db`가 제공되면 같은 로더가 자동으로 DB를 우선 사용한다.

### [D-11] fixed_slots.csv 자동 생성  (Step 1, 2026-06-02)
- 무엇을: `fixed_slots.csv`가 없으면 Persona 설계 §5의 100개 슬롯을 `slots.py`에서 `data/fixed_slots.csv`로 생성한다.
- 왜: 계획상 입력 파일이지만 현재 폴더에는 없고, 설계 문서에는 전체 슬롯 목록이 명시되어 있다.
- 영향: `twinmarket_kr/persona/slots.py`, `data/fixed_slots.csv`.
- 되돌릴 때: 외부 `fixed_slots.csv`를 제공하면 로더가 그 파일을 읽는다.

### [D-12] Persona 선발 시드 = 2  (Step 1, 2026-06-02)
- 무엇을: `RANDOM_SEED`를 2로 고정했다.
- 왜: 2026-06-02 14:42에 사용자가 `sys_1000.csv`를 1000명 파일로 교체했다. 시드 2는 새 1000명 pool에서도 검증 기준인 젊은 남성 turnover > 고령층 turnover 방향성을 만족한다.
- 영향: `config.py`, `scripts/01_build_persona.py` 실행 결과.
- 되돌릴 때: 더 큰 pool이나 별도 실험 조건이 생기면 `config.py`의 `RANDOM_SEED`를 바꿔 재선발한다.

### [D-13] agents 테이블에 news_depth 저장  (Step 1, 2026-06-02 / 2026-06-10 갱신)
- 무엇을: `agents` 스키마에 `news_depth` 컬럼을 추가했다. 2026-06-10 갱신 후에는 기존 Depth 1 후보 중 15명을 시드 기반 랜덤으로 Depth 0에 배정하여 15명 Depth 0, 55명 Depth 1, 30명 Depth 2 구조를 사용한다.
- 왜: News 설계는 Depth를 페르소나 속성으로 요구하지만 Persona 스키마에는 별도 컬럼이 없었다.
- 영향: `twinmarket_kr/db/schema.py`, `twinmarket_kr/persona/select.py`.
- 되돌릴 때: Depth를 별도 설정 파일에서 관리하려면 `assign_news_depth()`와 agents DDL을 조정한다.

### [D-14] `.env`/OpenAI 패키지 import는 optional 처리  (Step 0/6, 2026-06-02)
- 무엇을: `python-dotenv`와 `openai` 패키지가 없어도 offline 검증 가능한 모듈은 import되도록 fallback을 두었다. 실제 LLM 호출 시에는 `openai` 설치와 `OPENROUTER_API_KEY`가 필요하다.
- 왜: 현재 기본 Python 환경에는 해당 패키지가 설치되어 있지 않지만, 코드 구조와 deterministic 모듈 검증은 계속 진행해야 한다.
- 영향: `config.py`, `twinmarket_kr/llm/client.py`, offline initial belief 생성.
- 되돌릴 때: 프로젝트 가상환경에 requirements를 설치한 뒤 fallback은 유지해도 무해하다.

### [D-15] Initial Belief offline 생성 모드  (Step 6, 2026-06-02)
- 무엇을: API 키 없이도 `scripts/04_generate_initial_beliefs.py --offline`으로 페르소나 기반 템플릿 initial belief를 생성할 수 있게 했다.
- 왜: 설계상 정식 Initial Belief는 LLM 생성물이지만, 현재 API 키/패키지가 없는 상태에서 Memory/Context 파이프라인을 검증하려면 turn=0 belief가 필요하다.
- 영향: `twinmarket_kr/llm/belief.py`, `outputs/sim.db`의 현재 turn=0 belief 100개.
- 되돌릴 때: `.env`와 requirements 설치 후 `scripts/04_generate_initial_beliefs.py`를 offline 없이 다시 실행하면 LLM 기반 belief로 덮어쓸 수 있다.

### [D-16] 실제 시장/뉴스 데이터 미제공 상태에서 모듈 검증은 fixture 사용  (Step 3/4/5, 2026-06-02)
- 무엇을: `stock_data.csv`와 `samsung_news_raw.pkl`이 아직 없어 Step 3/4는 임시 fixture로 로딩/조회 로직을 검증했다. 실제 데이터 적재는 파일 제공 후 실행한다.
- 왜: 데이터가 없는 상태에서도 코드 경로, 파생지표 계산, 뉴스 도구 입출력, 매칭 엔진을 먼저 검증할 수 있다.
- 영향: `FundamentalAgent`, `NewsAgent`, `ExchangeAgent` 검증 방식.
- 되돌릴 때: `data/stock_data.csv`, `data/samsung_news_raw.pkl`을 넣고 `scripts/03_load_stock_data.py`, `scripts/02_prepare_news.py`를 실행한다.

### [D-17] 뉴스 해석과 거래 전 시장 분석 프롬프트 연결  (Step 7/8, 2026-06-09)
- 무엇을: `prompts/news_interpretation.txt`, `prompts/market_analysis.txt`를 `twinmarket_kr/llm/analysis.py`로 연결하고, `daily_cycle`에서 news_interpretation → update_belief → market_analysis → make_decision 순서로 호출한다.
- 왜: `make_decision.txt`가 `market_analysis` 입력을 요구하도록 바뀌었고, 새 프롬프트가 코드에 연결되지 않으면 런타임 포맷 오류가 발생한다.
- 영향: `twinmarket_kr/llm/analysis.py`, `twinmarket_kr/llm/decision.py`, `twinmarket_kr/core/daily_cycle.py`.
- 되돌릴 때: `make_decision.txt`에서 `market_analysis` 입력을 제거하고 `decision.py` 시그니처를 이전 형태로 되돌린다.

### [D-18] Depth별 뉴스 컨텍스트 materialization  (Step 4d/8, 2026-06-09 / 2026-06-10 갱신)
- 무엇을: `collect_context`는 agent의 `news_depth`를 NewsAgent에 전달한다. Depth 0은 일일 제목 10개만, Depth 1은 일일 제목 10개와 요약 10개 전체를, Depth 2는 Depth 1 정보에 더해 LLM pre-search가 정한 키워드로 최근 7일 flat 검색 결과 10개를 추가한다.
- 왜: 기존 구현은 Depth 1이 최대 3개 선택 읽기였고, Depth 2 검색 키워드를 Python이 하드코딩으로 정해 agentic search 흐름이 로그에 남지 않았다.
- 영향: `twinmarket_kr/agents/news_agent.py`, `twinmarket_kr/core/collect_context.py`, `twinmarket_kr/core/daily_cycle.py`.
- 되돌릴 때: 완전한 tool-calling loop를 구현하면 `expand_context_from_selection()`을 OpenAI tool call 처리 루프로 대체한다.

### [D-19] 재실행 격리와 체결 기준 trade_log  (Step 8/9, 2026-06-10)
- 무엇을: 시뮬레이션 시작 시 `TradingDetails`, `trade_log`, turn>0 `belief_history`, turn>0 `portfolio_state`를 정리한다. `trade_log`는 주문 제출 시 pending으로 기록하고 Exchange 이후 filled/unfilled로 갱신한다. 체결이 없는 날도 포트폴리오 current_price와 미실현손익을 갱신한다.
- 왜: 같은 `sim.db` 재사용 시 이전 실행 체결 내역이 섞이고, 미체결 주문이 실제 거래처럼 다음날 context에 전달되는 문제를 막기 위해서다.
- 영향: `twinmarket_kr/simulation.py`, `twinmarket_kr/agents/memory_agent.py`, `twinmarket_kr/db/schema.py`.
- 되돌릴 때: run_id별 DB 파일을 도입하면 런타임 테이블 정리 대신 실행별 DB 경로를 사용한다.
