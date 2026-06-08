# TwinMarket Korea — 코드 구현 마스터 플랜 (Code_Plan.md)

> 이 문서는 **코드를 짜기 위한 프롬프트 역할**을 하는 마스터 플랜이다.
> 4개 설계 문서를 넘나들며 구현할 때, 이 문서 하나를 기준점으로 삼는다.
> 코드는 한 번에 다 짜지 않고 **Step 단위로 나눠서** 작성·검토·기록하며 진행한다.

---

## 0. 이 문서를 읽는 AI/개발자에게 (필독)

이 프로젝트는 세션이 끊기거나 다른 머신·다른 작업자로 이어질 수 있다. 따라서 **진행상황을 문서에 남기는 것**이 코드를 짜는 것만큼 중요하다.

### 새 세션을 시작할 때
1. 이 문서(`Code_Plan.md`) 전체를 읽는다.
2. 맨 아래 **"진행 로그"** 섹션에서 마지막으로 완료된 Step을 확인한다.
3. 해당 Step의 `✅ 완료 노트`를 읽어 맥락을 복원한다.
4. `Code_Status.md`를 읽어 지금까지 내려진 임의 결정들을 파악한다.
5. 다음 미완료 Step부터 이어서 진행한다.

### 각 Step을 끝낼 때 (반드시)
- 이 문서 맨 아래 **진행 로그**에 해당 Step의 `✅ 완료 노트`를 추가한다:
  - **수행한 것**: 어떤 파일을 어떻게 생성/수정했는지
  - **핵심 판단**: 계획과 달라진 점이 있다면 무엇을 왜
  - **발견한 문제**: 예상과 다른 데이터 구조, 에러, 주의사항
  - **다음 Step 준비**: 다음 작업자가 바로 시작하려면 알아야 할 것
- 설계서에 없어서 **임의로 정한 결정**은 `Code_Status.md`에 "무엇을 / 왜" 형식으로 기록한다.

---

## Part A. 우리의 목적과 설계 문서 읽는 법

### A-1. 우리가 만드는 것 (목적)

LLM 기반 에이전트 **100명**이 **삼성전자(005930) 단일 종목**을 약 **6개월(데이터 가용 기간)** 거래하는 시장 시뮬레이션이다. 핵심 목적은 다음과 같다 (참조: `Overall_Framework_Design.md` §1).

- **가격을 재현하려는 것이 아니다.** 가격 동학(변동성 클러스터링 등 Macro)은 실제 삼성전자 역사 데이터로 고정한다.
- **목적은 Micro 행동 관찰이다.** 동일한 외생적 가격 환경에서 에이전트들이 각자의 페르소나·Belief에 따라 어떻게 다르게 정보를 받아들이고, 관점을 형성하고, 거래로 옮기는지를 본다.
- 의사결정 구조는 BDI를 버리고 **`collect_context → update_belief → make_decision → execute_trade`** 4단계로 단순화했다. 하루에 LLM은 기본 2회 호출된다 (update_belief, make_decision).

### A-2. 설계 문서 4종 — 역할과 읽는 순서

| 순서 | 문서 | 역할 | 언제 보는가 |
|----|------|------|-----------|
| ① | **Overall_Framework_Design.md** | 전체 뼈대·Flow·서비스 모듈 인터페이스·Belief·DB 스키마 | **항상 펴둔다.** 모든 Step의 기준점 |
| ② | **Persona_Distribution_Design.md** | sys_1000→sys_100 선발(100 슬롯·14 세그먼트·가중선발·persona_prompt) | Step 1 |
| ③ | **News_System_Design.md** | 뉴스 Agentic RAG (Depth 1/2, read_news/search_news, 일일 10건 선정) | Step 4 |
| ④ | **Matching_System_Design.md** | 주문 매칭 엔진 (실가격 앵커 집합경매, Phase 1/2/3, INSTITUTIONAL) | Step 5 |

**읽는 원칙:** 코드를 짤 때는 항상 ① Overall을 기준으로 전체 Flow를 잡고, 지금 만드는 Step에 해당하는 서브시스템 설계서(②③④)를 같이 펴서 세부 입출력·알고리즘을 맞춘다. 각 Step 설명에 "참조: <문서> §<섹션>"을 명시해 두었다.

### A-3. 전체 Flow 한눈에 (참조: Overall §3)

```
[Step1] sys_1000.db ──선발──> sys_100.db (100명 페르소나)
            │
            ▼
[Step2] portfolio_state_t000 초기화 (현금만 보유)
            │
[Step6] Initial Belief 생성 (페르소나만, turn=0)
            │
            ▼
   ┌────────────── 매 거래일 t 반복 ──────────────┐
   │ [Step8] collect_context                      │
   │   ├ Memory(이전belief·포트폴리오·최근근거)    │ ← Step2
   │   ├ News(일일10건 + 자율읽기)                 │ ← Step4
   │   └ Fundamental(종가·지표)                    │ ← Step3
   │            ↓ today_context                    │
   │ [Step6] update_belief  (LLM#1, 6차원 CoT)     │
   │            ↓ today_belief → Memory 저장        │
   │ [Step7] make_decision  (LLM#2)                │
   │            ↓ trading_decision                  │
   │ [Step5] execute_trade  (Phase1/2/3 매칭)       │
   │            ↓ 체결결과 → portfolio_state·trade_log │
   └──────────────────────────────────────────────┘
            │ (Step9: day_number로 Phase 분기, 100명 async)
            ▼
[Step10] 통합 검증
```

---

## Part B. 프로젝트 구조 & 공통 규약

### B-1. 디렉토리 구조

새 머신의 깨끗한 폴더(= 프로젝트 루트)에 4개 설계 md + 데이터만 있는 상태에서 시작한다. 아래 구조를 그 루트에 만든다.

```
(프로젝트 루트)
├─ Overall_Framework_Design.md          # 주어짐
├─ Persona_Distribution_Design.md       # 주어짐
├─ News_System_Design.md                # 주어짐
├─ Matching_System_Design.md            # 주어짐
├─ Code_Plan.md                         # 이 문서
├─ Code_Status.md                       # 임의결정 기록
│
├─ .env.example                         # OPENROUTER_API_KEY / BASE_URL / MODEL
├─ .gitignore                           # .env, outputs/, __pycache__ 등
├─ requirements.txt
├─ config.py                            # 경로·상수 중앙화 (단일 진실 공급원)
│
├─ data/                                # 입력 데이터 (따로 수집/제공)
│   ├─ sys_1000.db                      # Profiles 풀 (PK=user_id, 한자값)
│   ├─ fixed_slots.csv                  # 100명 고정 슬롯 (Persona §5)
│   ├─ stock_data.csv                   # 삼성전자 OHLCV+지표
│   ├─ trading_days.csv                 # KRX 거래 캘린더
│   └─ samsung_news_raw.pkl             # 원본 뉴스 (전처리 입력)
│
├─ prompts/                             # 모든 LLM 프롬프트 (코드와 분리)
│   ├─ initial_belief.txt
│   ├─ update_belief.txt
│   ├─ make_decision.txt
│   └─ news_agent.txt
│
├─ twinmarket_kr/                       # 메인 패키지
│   ├─ __init__.py
│   ├─ db/
│   │   ├─ schema.py                    # 테이블 DDL (belief_history 등)
│   │   └─ connection.py                # DB 커넥션 헬퍼
│   ├─ persona/
│   │   ├─ slots.py                     # 고정 슬롯 로드
│   │   ├─ segments.py                  # 14 세그먼트 프로파일
│   │   └─ select.py                    # 가중 선발 (sys_1000→sys_100)
│   ├─ agents/                          # 서비스 모듈
│   │   ├─ memory_agent.py
│   │   ├─ fundamental_agent.py
│   │   ├─ news_agent.py
│   │   └─ exchange_agent.py            # 매칭 엔진
│   ├─ llm/
│   │   ├─ client.py                    # OpenRouter(OpenAI 호환) 래퍼
│   │   ├─ belief.py                    # update_belief / initial_belief
│   │   └─ decision.py                  # make_decision
│   ├─ core/
│   │   ├─ collect_context.py
│   │   └─ daily_cycle.py               # 4단계 오케스트레이션
│   └─ simulation.py                    # 메인 루프
│
├─ scripts/                             # 실행 엔트리포인트
│   ├─ 01_build_persona.py              # Step1 실행
│   ├─ 02_prepare_news.py               # Step4a 전처리 실행
│   ├─ 03_run_simulation.py             # Step9 실행
│   └─ 99_validate.py                   # Step10 검증
│
└─ outputs/                            # 결과물 (gitignore)
    ├─ sys_100.db                       # 선발 결과 (Step1 산출)
    ├─ sim.db                           # belief_history/portfolio_state/trade_log/StockData/TradingDetails
    └─ logs/
```

> 참고: `data/`의 파일명은 실제 수집 결과에 따라 바뀔 수 있다. **경로는 모두 `config.py`에서 관리**하고, 코드에 하드코딩하지 않는다.

### B-2. 공통 규약

- **경로·상수 중앙화**: 모든 파일 경로와 시뮬레이션 상수는 `config.py`에. 코드에 매직넘버/하드코딩 경로 금지.
- **프롬프트 분리**: LLM에 보내는 자연어 프롬프트는 전부 `prompts/*.txt`. 코드(`llm/*.py`)에는 "프롬프트 로드 → 변수 주입 → 호출 → 파싱" 로직만.
- **LLM 백엔드**: OpenRouter(OpenAI 호환). `.env`의 `OPENROUTER_MODEL`로 모델명 지정. async + 재시도(backoff) + tool calling 지원(News Agent용).
- **DB**: SQLite. 입력 풀은 `data/sys_1000.db`, 선발 결과는 `outputs/sys_100.db`, 시뮬레이션 상태는 `outputs/sim.db`. 원본 `sys_1000.db`는 절대 수정하지 않는다(읽기 전용).
- **모듈 분류**: "서비스 모듈"(memory/fundamental/news/exchange)은 LLM 비호출 데이터 제공자, "llm"은 LLM 호출 담당, "core"는 오케스트레이션. 책임 경계를 섞지 않는다.
- **결정 기록**: 설계서에 답이 없어 임의로 정한 모든 것은 `Code_Status.md`에 기록한다.

### B-3. `.env` / 설정 (Step0에서 생성)

`.env.example` (사용자는 복사해서 `.env`로 채움):
```
OPENROUTER_API_KEY=sk-or-xxxx
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openai/gpt-4o        # 모델명만 바꾸면 교체됨 (claude 등도 가능)
OPENROUTER_EMBED_MODEL=               # (선택) 의미검색 쓸 경우만
```
`config.py`는 `python-dotenv`로 `.env`를 로드하고, 경로·상수와 함께 노출한다.

---

## Part C. 구현 Step (Step 0 → 10)

> 각 Step: **목적 / 참조 / 입력 / 출력 / 만들 것 / 검토 기준**.
> 의존성 순서대로 진행. 한 Step 끝나면 진행 로그에 완료 노트 작성.

---

### Step 0 — 프로젝트 스캐폴딩 & 공통 기반
**목적**: 이후 모든 Step이 의존하는 뼈대(설정·DB 스키마·LLM 클라이언트)를 만든다.
**참조**: Overall §8(스키마), Matching §7(StockData/TradingDetails), Persona §14(agents 스키마)

**만들 것**
- 디렉토리 구조 전체, `requirements.txt`, `.gitignore`, `.env.example`
- `config.py` — 경로 + 상수:
  - `STOCK_CODE="005930"`, `COMMISSION_RATE`(예: 0.00015 등 Code_Status에 근거 기록), `CIRCUIT_BREAKER=0.30`
  - `N_WARMUP=3`, `N_TRANSITION=4` (Phase 경계, Matching §3)
  - `INI_CASH_SMALL=100_000_000`, `INI_CASH_LARGE=1_000_000_000`
  - Belief 6차원 글자수 제한(Overall §7)
  - 실험 기간(start/end date) — 데이터 가용 범위
- `twinmarket_kr/db/schema.py` — 테이블 DDL:
  - `belief_history`, `portfolio_state`, `trade_log` (Overall §8)
  - `StockData`, `TradingDetails` (Matching §7)
  - `agents`(sys_100) DDL은 Step1에서 사용
- `twinmarket_kr/db/connection.py` — 커넥션/초기화 헬퍼
- `twinmarket_kr/llm/client.py` — OpenRouter 비동기 클라이언트(채팅+tool calling, 재시도)
- `Code_Status.md` 초기 작성

**검토 기준**: 패키지 import 정상 / `.env` 로드 / 빈 `sim.db` 생성(테이블 존재) / LLM 클라이언트 ping 1회 성공.

---

### Step 1 — Persona 선발 (sys_1000.db → sys_100.db)
**목적**: 1000명 행동 풀에서 100명을 가중 선발해 `outputs/sys_100.db`(agents)를 만든다.
**참조**: Persona_Distribution_Design.md **전체** (특히 §4 한자매핑, §5 고정슬롯, §6 세그먼트, §11 알고리즘, §14 스키마)

**입력**: `data/sys_1000.db`(Profiles), `data/fixed_slots.csv`(없으면 §5 목록으로 생성)
**출력**: `outputs/sys_100.db`(agents 테이블), 분포 검증 리포트

**만들 것**
- `persona/slots.py` — 고정 슬롯 100개 로드 (agent_id, gender, age, age_group, ini_cash). 성별 한국어→male/female, 운용자산 "1억/10억"→정수
- `persona/segments.py` — 14 세그먼트별 behavioral 우선순위 (§6 그대로)
- `persona/select.py` — Profiles 로드(+한자→영문 매핑 §4) → `get_behavioral_profile` → `score_agent`(1/2/3순위 +3/+2/+1, 최소1) → `match_agents`(가중 랜덤, 1인1슬롯) → `assign_location`(지역 가중) → `generate_persona_prompt`(§11) → sys_100 저장
- `scripts/01_build_persona.py` — 위 파이프라인 실행 + 검증 리포트 출력

**검토 기준** (Persona §15): 성별 43/57·연령대·자산군이 슬롯과 **편차 0** / 세그먼트 coherence(20·30대 남성 turnover가 60·70대보다 高) / fallback 빈도 / persona_prompt 빈값·포맷 오류 없음.

---

### Step 2 — Memory Agent (상태 관리 계층)
**목적**: belief/포트폴리오/거래근거의 단일 진실 공급원. 이후 거의 모든 Step이 사용.
**참조**: Overall §2(Memory Agent), §8(3개 테이블 스키마)

**만들 것** — `agents/memory_agent.py`
- 쓰기: `save_belief(belief)`, `update_portfolio(agent_id, turn, fills)`, `append_trade_log(record)`, `init_portfolio_t000(agents)`
- 읽기: `get_previous_belief(agent_id, turn)`(turn=1이면 Initial 사용), `get_portfolio_summary(agent_id, turn)`(→자연어 텍스트), `get_last_action_reason(agent_id)`(마지막 buy/sell의 reason, 없으면 null)
- 포트폴리오 요약 텍스트 빌더(현금·수량·평단가·미실현손익·수익률)

**검토 기준**: t000 100명 생성(현금=ini_cash, 포지션 없음) / 저장→조회 왕복 일치 / hold만 있을 때 `get_last_action_reason`=null.

---

### Step 3 — Fundamental Agent (시장 데이터)
**목적**: 날짜를 받아 시장 기술지표를 반환.
**참조**: Overall §6(Fundamental 요청), Matching §7(StockData)

**입력**: `data/stock_data.csv` → `StockData` 적재
**출력**: `get_market_features(date)` → `{close, pct_chg, volume_chg, ma5, ma20, volatility_20d}`

**만들 것** — `agents/fundamental_agent.py` + 적재 스크립트
- ⚠️ **데이터 매핑 주의**: `stock_data.csv`에는 `ma_hfq_5/10/30`만 있고 `ma20`이 없다. `volatility_20d`·`volume_chg`도 직접 없을 수 있다 → close 시계열로 **파생 계산**. (이 결정은 `Code_Status.md`에 기록)

**검토 기준**: 임의 날짜 조회 시 `close`가 stock_data.csv 실제 종가와 일치 / 파생지표 NaN 처리 정상.

---

### Step 4 — News Agent (Agentic RAG, Depth 1/2)
**목적**: 에이전트별 뉴스 컨텍스트를 자율 읽기 방식으로 제공.
**참조**: News_System_Design.md **전체**

**4a. 전처리** — `scripts/02_prepare_news.py`
- 원본 pkl → `processed_news.csv`(하루 ~30건: id,title,date,time,category,summary) + `daily_news_selection.csv`(하루 10건: 종목5/섹터3/경제2)
- ⚠️ **중요도 계산 방식은 설계서 미명시** → 휴리스틱(키워드 빈도·카테고리 가중 등)으로 구현하고 `Code_Status.md`에 기록. summary는 `processed_news.csv`에만 저장(News 설계 명시).

**4b/4c. 도구** — `agents/news_agent.py`
- `read_news(titles|ids)` → 본문 반환 (News §4.1)
- `search_news(fields[≤4])` → 최근 7일 키워드 매칭 상위 제목 (News §4.2, **키워드 기반** — 임베딩 불필요)

**4d. Depth flow**
- Depth 1: 일일 10건 + `read_news` 0~3
- Depth 2: + `search_news` → 추가 `read_news` 0~5
- LLM tool calling으로 "읽을지 말지"를 에이전트가 자율 결정. Depth는 페르소나 속성(분포는 config 파라미터; sys_100에 없으면 별도 부여 — Code_Status 기록).

**검토 기준**: read/search 입출력 JSON이 News 설계 포맷과 일치 / Depth별 읽기 예산 상한 준수 / 뉴스 없는 날 `[]` 처리.

---

### Step 5 — Exchange Market Agent (매칭 엔진)
**목적**: 주문을 받아 Phase에 따라 체결.
**참조**: Matching_System_Design.md **전체** (§4 Phase1, §5 Phase2/3, §6 일별처리)

**만들 것** — `agents/exchange_agent.py`
- `execute_warmup_orders(...)` (Phase1: 개별 제출가 즉시 체결, 종가=real_price)
- `calculate_anchored_price(...)` (Phase2/3: 서킷브레이커 클리핑 → target_price 체결가능 수량 → imbalance만큼 INSTITUTIONAL 주입 → 단일가 체결, 에이전트 우선)
- `process_daily_orders(orders, real_prices, last_real_prices, day_number, n_warmup)` → 종목별 분기
- 체결 결과 → `TradingDetails` 기록 (INSTITUTIONAL 포함)

**검토 기준** (Matching §8): Phase1 평단가 다양성 / Phase2/3 종가==실종가 / INSTITUTIONAL 방향(매수우세→inst 매도) / 에이전트 우선 체결 / 엣지(한쪽 없음·둘다없음).

---

### Step 6 — Belief 생성 (LLM Call #1 + Initial Belief)
**목적**: today_context로 6차원 CoT Belief 생성. 시작 전 Initial Belief(turn=0)도 생성.
**참조**: Overall §5(단계3 Initial), §6(Phase2), §7(Belief 상세)

**만들 것**
- `prompts/initial_belief.txt` — 페르소나만으로 6차원 초기 관점
- `prompts/update_belief.txt` — today_context 기반 6차원 CoT (미래방향/밸류에이션/거시/심리/뉴스해석/자기평가), 각 차원 글자수 제한
- `llm/belief.py` — 프롬프트 로드·주입·호출·파싱(6 dim + belief_summary + view_change) → Memory 저장
- 기존 `aicp_twinmarket/trader/prompts.py`·`init_belief.py`의 belief **차원 구조만 참조**해 한국어로 재작성(로직 복사 금지, Code_Status 기록)

**검토 기준**: turn=0 Initial 100명 생성 / 6차원+summary 채워짐 / 글자수 제한 / 다음날 previous_belief로 summary가 전달.

---

### Step 7 — Decision 생성 (LLM Call #2)
**목적**: today_belief + 포트폴리오 + 제약으로 거래 결정.
**참조**: Overall §4(LLM#2), §6(Phase3)

**만들 것**
- `prompts/make_decision.txt` — buy/sell/hold + 수량 + reason + risk_control
- `llm/decision.py` — `trading_constraints` 빌더(available_cash, current_quantity, current_price, commission_rate, min_order_unit) + 호출 + 파싱

**검토 기준**: 가용 현금 초과 매수 안 함 / hold도 정상(orders 빈 결과) / action_reason이 trade_log에 저장되고 다음날 전달.

---

### Step 8 — collect_context + 일별 사이클
**목적**: 서비스 모듈을 묶어 today_context 조립 + 하루 4단계 실행.
**참조**: Overall §3(하루 상호작용), §6(4 Phase)

**만들 것**
- `core/collect_context.py` — Memory(이전belief·포트폴리오·최근근거) + News + Fundamental → `today_context`(Overall §6 구조)
- `core/daily_cycle.py` — `run_agent_turn(agent, day)`: collect_context → update_belief → make_decision → (주문 반환). 체결은 Step9에서 배치 처리.

**검토 기준**: today_context 키 구조가 Overall §6과 일치 / 단일 에이전트 1턴 end-to-end 동작.

---

### Step 9 — 메인 시뮬레이션 루프 + Phase 전환
**목적**: 전체 기간×100명을 돌리고 Phase 분기·매칭·상태 업데이트를 엮는다.
**참조**: Overall §3(멀티데이), Matching §3(Phase 경계)

**만들 것** — `twinmarket_kr/simulation.py` + `scripts/03_run_simulation.py`
- 거래일 루프: 각 일에 100명 `run_agent_turn`을 **async 배치**(LLM 2콜씩) → 주문 수집
- `day_number`로 Phase 결정 → `process_daily_orders` 매칭 → 체결로 portfolio_state·trade_log·StockData 업데이트
- 진행상황 로그(일자·체결수·INSTITUTIONAL 방향)

**검토 기준**: smoke(예: 5명×3일) 무에러 완주 / Phase1→2 전환 시점 정확 / 종가 실데이터 고정 / 상태 누적 정합.

---

### Step 10 — 통합 검증 (End-to-End)
**목적**: 4개 문서의 검증 계획을 한 번에 점검.
**참조**: Overall §10, Persona §15, News·Matching 검증 절

**만들 것** — `scripts/99_validate.py`
- Belief 연속성(시계열 합리적 변화) / 결정 추적성(belief_summary↔action_reason↔다음날 전달) / 모듈 정합성(Memory·Fundamental·News 반환이 원천과 일치) / 포트폴리오 수치 일관성(현금·수량·총자산) / INSTITUTIONAL 방향 vs `elg_amount_net` / 페르소나 분포

**검토 기준**: 각 항목 PASS/리포트 출력.

---

## Part D. 의존성 & 실행 순서

```
Step 0 (스캐폴딩)
   ├─→ Step 1 (Persona, 독립적으로 sys_100 산출)
   ├─→ Step 2 (Memory) ─┐
   ├─→ Step 3 (Fundamental) ─┤
   ├─→ Step 4 (News) ───────┤
   └─→ Step 5 (Exchange) ────┤
                              ├─→ Step 6 (Belief LLM#1)
                              ├─→ Step 7 (Decision LLM#2)
                              └─→ Step 8 (collect_context+cycle)
                                       └─→ Step 9 (메인 루프)
                                                └─→ Step 10 (검증)
```

- **권장 진행**: Step0 → 1 → 2 → 3 → 5 → 4 → 6 → 7 → 8 → 9 → 10
  (News(4)는 tool calling이 복잡하므로 Fundamental(3)·Exchange(5) 같은 결정적 모듈을 먼저 끝내고 진입)
- **smoke 우선**: Step9에서 소수 에이전트×소수 거래일로 먼저 완주시킨 뒤 풀런.

---

## Part E. 진행 로그 (Step 완료 시마다 추가)

> 형식:
> ```
> ### ✅ Step N 완료 (YYYY-MM-DD)
> - 수행한 것:
> - 핵심 판단:
> - 발견한 문제:
> - 다음 Step 준비:
> ```

*(아직 코드 미착수 — Step 0부터 시작. 완료 노트는 여기에 누적한다.)*

### ✅ Step 0 완료 (2026-06-02)
- 수행한 것: `twinmarket_kr_project` 아래 프로젝트 구조를 만들고 `.env.example`, `.gitignore`, `requirements.txt`, `config.py`, DB 스키마/커넥션 헬퍼, OpenRouter async 클라이언트 골격을 생성했다. `outputs/sim.db`에 `belief_history`, `portfolio_state`, `trade_log`, `StockData`, `TradingDetails` 테이블을 생성해 확인했다.
- 핵심 판단: `python-dotenv`가 설치되지 않은 기본 환경에서도 검증할 수 있도록 `.env` 로딩은 optional fallback으로 처리했다. 실제 의존성은 `requirements.txt`에 유지한다.
- 발견한 문제: 로컬 기본 Python에는 `python-dotenv`가 없었다. OpenRouter ping은 API key가 없는 상태라 실행하지 않았다.
- 다음 Step 준비: `scripts/01_build_persona.py`로 persona 선발을 실행할 수 있다.

### ✅ Step 1 완료 (2026-06-02)
- 수행한 것: Persona 설계에 따라 고정 슬롯 로더/자동 생성, 14개 세그먼트, 한자값 매핑, 가중 선발, location/depth/persona_prompt 생성, `outputs/sys_100.db` 저장, 검증 리포트 생성을 구현했다. `data/sys_1000.csv` 입력으로 100명 `agents` 테이블을 생성했다.
- 핵심 판단: 제공 입력이 DB가 아니라 CSV이므로 `load_pool()`이 DB/CSV를 모두 지원하도록 했다. `fixed_slots.csv`는 설계 문서의 100개 슬롯에서 자동 생성한다. `news_depth`는 agents 컬럼에 저장했다.
- 발견한 문제: 첨부 `sys_1000.csv`는 이름과 달리 100명만 포함한다. 따라서 100명 전원을 100개 슬롯에 1회씩 배정해야 하며, 시드 선택이 세그먼트 coherence에 영향을 준다. 시드 2에서 젊은 남성 turnover 평균 2.2, 고령층 1.917로 검증 방향성을 만족했다.
- 다음 Step 준비: 다음 작업은 Step 2 Memory Agent 구현이다. `outputs/sys_100.db`와 `outputs/persona_validation_report.json`을 기준 입력으로 사용하면 된다.

### 🔁 Step 1 재실행 (2026-06-02)
- 수행한 것: 사용자가 수정한 `/Users/leeyujeong/Downloads/MD_File/sys_1000.csv`를 `data/sys_1000.csv`로 갱신하고 `scripts/01_build_persona.py`를 다시 실행해 `outputs/sys_100.db`를 재생성했다.
- 핵심 판단: 새 CSV는 헤더 포함 1001줄로 1000명 pool이 맞다. 기존 CSV/DB 겸용 로더와 동일한 시드 2를 사용했다.
- 발견한 문제: 없음. 최종 agents 100명, distinct source_user_id 100명, 성별/연령/자산 분포 편차 0, prompt 오류 0.
- 다음 Step 준비: Step 2는 재생성된 `outputs/sys_100.db`를 그대로 사용하면 된다.

### ✅ Step 2 완료 (2026-06-02)
- 수행한 것: `twinmarket_kr/agents/memory_agent.py`와 `scripts/02_init_memory.py`를 구현했다. `save_belief`, `get_previous_belief`, `init_portfolio_t000`, `update_portfolio`, `append_trade_log`, `get_last_action_reason`, `get_portfolio_summary`를 DB 왕복으로 검증했다. 현재 `outputs/sim.db`에는 turn=0 portfolio_state 100개가 있다.
- 핵심 판단: 포지션은 설계의 JSON 배열 구조를 유지하고, 체결 업데이트는 fill 리스트를 받아 평균단가/현금/실현손익/미실현손익을 계산한다.
- 발견한 문제: 병렬 검증 중 초기화와 업데이트가 동시에 실행되어 한 번 race가 발생했다. 이후 순차 실행으로 정상 확인했다.
- 다음 Step 준비: Step 8 context 조립에서 MemoryAgent를 그대로 사용할 수 있다.

### ✅ Step 3 코드 완료 (2026-06-02)
- 수행한 것: `twinmarket_kr/agents/fundamental_agent.py`와 `scripts/03_load_stock_data.py`를 구현했다. CSV 컬럼 탐지, `StockData` 적재, `ma5`, `ma20`, `pct_chg`, `volume_chg`, `volatility_20d` 파생 계산을 임시 fixture로 검증했다.
- 핵심 판단: 실제 파일 컬럼명이 설계와 다를 수 있어 date/close/volume/ma 계열 후보명을 탐지한다. `StockData`에 `volume_chg` 컬럼을 추가했다.
- 발견한 문제: 현재 `data/stock_data.csv`가 없어 실제 삼성전자 데이터 적재 검증은 대기 중이다.
- 다음 Step 준비: `data/stock_data.csv`가 들어오면 `python3 scripts/03_load_stock_data.py`를 실행한다.

### ✅ Step 5 완료 (2026-06-02)
- 수행한 것: `twinmarket_kr/agents/exchange_agent.py`를 구현했다. Phase 1 개별가 체결, Phase 2/3 실가격 앵커 집합경매, 서킷브레이커, 시장가 처리, INSTITUTIONAL one-shot injection, `TradingDetails` 저장 함수를 추가했다.
- 핵심 판단: 빈 주문일에도 `real_prices`에 있는 종목 결과를 반환하도록 구현했다.
- 발견한 문제: 없음. fixture 검증에서 매수 우세 시 INSTITUTIONAL sell 11주 주입, 빈 주문 volume=0, Phase1 day1 buy-only 처리를 확인했다.
- 다음 Step 준비: Step 9에서 일별 주문 묶음을 이 모듈로 넘기면 된다.

### ✅ Step 4 코드 완료 (2026-06-02)
- 수행한 것: `twinmarket_kr/agents/news_agent.py`와 `scripts/02_prepare_news.py`를 구현했다. pkl 원본 전처리, `processed_news.csv`, `daily_news_selection.csv`, `read_news`, `search_news`, 일일 제목 context를 임시 fixture로 검증했다.
- 핵심 판단: 카테고리는 `종목/섹터/경제`로 정규화하고, `산업`은 설계상 섹터로 처리한다. 중요도는 키워드/카테고리/제목 신호 기반 휴리스틱이다.
- 발견한 문제: 현재 `data/samsung_news_raw.pkl`이 없어 실제 뉴스 전처리는 대기 중이다.
- 다음 Step 준비: pkl 제공 후 `python3 scripts/02_prepare_news.py`를 실행한다.

### ✅ Step 6 코드 완료 + offline initial 생성 (2026-06-02)
- 수행한 것: `prompts/initial_belief.txt`, `prompts/update_belief.txt`, `twinmarket_kr/llm/belief.py`, `scripts/04_generate_initial_beliefs.py`를 구현했다. 현재 API 없이 offline 모드로 turn=0 initial belief 100개를 `outputs/sim.db`에 저장했다.
- 핵심 판단: 정식 LLM 생성과 별개로, API 키가 없을 때 파이프라인 검증을 위한 offline 템플릿 모드를 둔다.
- 발견한 문제: 현재 환경에는 `openai` 패키지와 API 키가 없어 실제 LLM 호출 검증은 대기 중이다.
- 다음 Step 준비: `.env` 설정과 `pip install -r requirements.txt` 후 offline 없이 초기 belief를 재생성할 수 있다.

### ✅ Step 7 코드 완료 (2026-06-02)
- 수행한 것: `prompts/make_decision.txt`, `twinmarket_kr/llm/decision.py`를 구현했다. 거래 제약 빌더와 JSON 파서에서 현금/보유수량/최소주문단위 초과를 방지한다.
- 핵심 판단: LLM 출력이 제약을 어겨도 파서 단계에서 buy/sell 수량을 클램프하고 불가능한 주문은 hold로 변환한다.
- 발견한 문제: 실제 LLM 호출 검증은 API 키/패키지 설치 후 가능하다.
- 다음 Step 준비: Step 8 `daily_cycle`에서 이 모듈을 호출한다.

### ✅ Step 8 코드 완료 (2026-06-02)
- 수행한 것: `core/collect_context.py`, `core/daily_cycle.py`를 구현했다. Memory/Fundamental/News를 묶어 Overall §6의 `today_context` 구조를 만들고, belief update → decision → order 반환까지 연결했다.
- 핵심 판단: 뉴스 tool-calling 자율 탐색은 LLM 통합 단계에서 확장하고, 현재 `NewsAgent.build_base_context()`는 일일 제목 10개와 빈 read contents를 반환한다.
- 발견한 문제: 실제 단일 에이전트 end-to-end는 `StockData`, 뉴스 CSV, OpenRouter 설정이 모두 있어야 실행 가능하다.
- 다음 Step 준비: 데이터와 API 설정 후 smoke run을 진행한다.

### ✅ Step 9/10 골격 완료 (2026-06-02)
- 수행한 것: `twinmarket_kr/simulation.py`, `scripts/05_run_simulation.py`, `scripts/99_validate.py`를 구현했다. validate 결과 현재 agents 100, persona pass true, portfolio_state 100, belief_history 100, stock/trade 데이터 0을 확인했다.
- 핵심 판단: 시뮬레이션은 `StockData` 날짜를 기준으로 루프를 돌며, async concurrency 상한을 둔다.
- 발견한 문제: 실제 smoke/full run은 `stock_data.csv`, 뉴스 전처리 결과, OpenRouter 설정이 없어 아직 실행하지 않았다.
- 다음 Step 준비: 누락 입력 파일과 `.env`가 준비되면 `scripts/03_load_stock_data.py`, `scripts/02_prepare_news.py`, `scripts/04_generate_initial_beliefs.py`, `scripts/05_run_simulation.py --max-agents 5 --max-days 3` 순서로 smoke를 수행한다.

---

*작성 기준: Overall_Framework_Design.md / Persona_Distribution_Design.md / News_System_Design.md / Matching_System_Design.md*
*임의 결정 기록은 Code_Status.md 참조.*
