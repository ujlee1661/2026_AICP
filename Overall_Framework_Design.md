# TwinMarket Korea — 에이전트 의사결정 프레임워크 최종 설계서

> **참조 문서:** 이 설계서는 아래 세 전문 설계서와 함께 사용한다.
> - `Persona_Distribution_First_Upgrade.md` — `sys_1000.db`(Profiles)에서 100명을 선발하여 `sys_100.db`(agents)를 구성하는 페르소나 배포 시스템
> - `News_System_Design.md` — 뉴스 처리 서브시스템 (Agentic RAG, Depth 1/2)
> - `Matching_System_Design.md` — 주문 매칭 엔진 (실가격 앵커 집합경매, Phase 1/2/3)

---

## 1. 시스템 목적 및 설계 동기

### 무엇을 만들고, 왜 만드는가

TwinMarket Korea는 LLM 기반 에이전트 100명이 삼성전자(005930) 단일 종목을 6개월간 거래하는 시장 시뮬레이션이다. 시스템의 목적은 실제 시장 가격을 재현하거나 에이전트의 수익률을 극대화하는 것이 아니다. 목적은 하나다. **에이전트 개개인이 어떤 정보를 받아 어떤 관점을 형성하고, 그 관점이 어떻게 거래 행동으로 이어지는지를 Micro한 수준에서 관찰하는 것이다.** 가격 동학(Macro Stylized Facts)은 실제 삼성전자 역사 데이터로 고정하고(Matching_System_Design.md 참조), 연구의 초점을 개별 에이전트의 행동 패턴과 그 이질성에 집중한다. 이 선택은 Matching_System_Design.md Q1 논지와 일치한다 — 에이전트가 가격을 만들어낼 수 있는지 검증하는 것이 아니라, 동일한 외생적 가격 환경에 에이전트들이 어떻게 다르게 반응하는지를 분석한다.

### 왜 BDI를 버리는가

기존 TwinMarket 코드는 BDI(Belief-Desire-Intention) 프레임워크를 기반으로 설계되어 있었다. BDI는 에이전트의 내부 상태를 계층적으로 분리한다는 점에서 이론적으로 정합하지만, 실제 구현에서는 두 가지 심각한 문제가 드러났다. 첫째, Desire와 Intention 레이어가 에이전트의 행동 집합을 사전에 명시적으로 정의함으로써 에이전트가 LLM의 자율적 판단 없이 정해진 경로를 따라가는 "연극적" 행동을 유발했다. 에이전트의 다양성과 창발적 행동이 실험의 핵심 가치인 시스템에서 이는 치명적이다. 둘째, 8~11번의 LLM 호출이 단계마다 같은 정보를 재가공하면서 불필요한 처리 비용을 낳았다. Belief가 Desire로, Desire가 Intention으로 변환되는 과정에서 최초 정보는 희석되고 에이전트의 결정은 점점 고정된 템플릿에 수렴했다.

### 새 프레임워크의 핵심 아이디어

새 프레임워크는 의사결정 구조를 세 단계로 단순화한다. **정보를 모으고, 관점을 형성하고, 행동을 결정한다.** 이 흐름은 인간 투자자의 실제 사고 과정과 훨씬 가깝다. 실제 투자자는 BDI처럼 추론하지 않는다. 오늘 뉴스를 보고, 시장 분위기를 느끼고, 자신의 기존 관점과 비교해 생각을 업데이트한 다음 행동을 결정한다. 이 과정에서 핵심 개념이 Belief다. Belief는 에이전트가 특정 시점에 가지고 있는 private 시장 관점이다. 거래 결정도, 커뮤니티 발화도 모두 이 Belief에서 출발한다. Belief가 매일 자유롭게 업데이트되기 때문에 에이전트는 경직된 틀에 갇히지 않으면서도 일관성 있는 행동 궤적을 유지한다.

### 서브시스템 분리의 설계 의도

Central Trading Agent 하나가 모든 것을 직접 처리하는 대신, 각 기능을 전문 서비스 모듈로 분리했다. 이 분리는 두 가지 이유에서 필요하다. 첫째, 책임 범위가 명확해진다. 뉴스 처리 로직이 변경되어도 매칭 엔진이나 Belief 생성 로직에 영향을 주지 않는다. 각 모듈은 독립적으로 개선할 수 있다. 둘째, 에이전트의 행동이 자율적으로 보인다. 에이전트는 필요한 정보를 능동적으로 요청하여 받아오는 구조로 표현된다. 처리 순서는 시스템이 정하지만, 각 단계에서 에이전트가 서브시스템과 상호작용한다는 표현 방식은 시뮬레이션의 현실성을 높인다. 각 서브시스템의 구체적 동작은 전문 설계서에서 정의하며, 이 문서는 서브시스템들이 어떤 인터페이스로 연결되는지를 정의한다.

---

## 2. 전체 에이전트 생태계 구조

시스템은 한 명의 **Central Trading Agent**와 네 개의 전문 서비스 모듈로 구성된다. 서비스 모듈은 LLM을 반드시 호출하지 않으며, DB 조회·데이터 계산·정보 가공을 수행한 후 구조화된 응답을 반환하는 기능 단위다.

### Central Trading Agent (개별 트레이더 에이전트)

시스템의 주체다. 100명의 에이전트 각각은 고유한 페르소나(성별, 나이, 지역, 투자 성향, 행동 편향)를 가진 인간 투자자를 모델링한다. 이 100명은 새로 만들어진 것이 아니라, 기존 TwinMarket 연구의 `sys_1000.db`(Profiles 테이블, 1000명 풀)에서 삼성전자 주주 통계와 행동 세그먼트 기준에 따라 선발된 결과다. 선발 과정은 100개의 인구통계 슬롯(agent_id A001~A100, 성별·나이·자산군 사전 확정)을 정의한 뒤, 각 슬롯이 요구하는 행동 프로파일과의 일치도를 가중치로 삼아 풀에서 확률적으로 1인 1슬롯 선발하는 방식이다. 선발된 에이전트의 행동 편향 칼럼(`bh_*_category`, `strategy` 등)은 풀에서 그대로 가져오되, 성별·나이·지역은 슬롯에서 새로 부여하고, 중국어로 저장된 값은 영문으로 매핑한다. 이렇게 구성된 최종 결과물이 `sys_100.db`(agents 테이블)이며, 시뮬레이션은 이 파일을 로드하여 시작한다. 각 에이전트는 매일 서비스 모듈들로부터 정보를 수집하고, 뉴스 해석, Belief 업데이트, 거래 전 시장 분석, 거래 결정을 위해 기본 4회 LLM 호출을 수행한 다음, Exchange Market Agent를 통해 주문을 체결한다. Depth 2 뉴스 심층 탐색이나 커뮤니티 기능이 추가되면 추가 호출이 발생한다. 선발 알고리즘, 100개 고정 슬롯 목록, 세그먼트 기준, `sys_100.db` 최종 스키마는 `Persona_Distribution_First_Upgrade.md`에서 정의한다.

### Memory Agent

에이전트의 상태 기억 전반을 관리하는 단일 진실 공급원(single source of truth)이다. 세 가지 데이터를 관리한다. **belief_history**: 에이전트가 매일 생성한 Belief를 날짜·턴별로 누적 저장한다. 다음날 collect_context에서 이전 Belief 반환 요청을 처리한다. **portfolio_state**: 거래 체결 시마다 보유 현금, 종목별 수량, 평균 매수 단가, 미실현 손익을 업데이트하고, 요청 시 포트폴리오 요약을 반환한다. **trade_log**: 매 거래 결정(매수/매도/보유)의 action_reason을 함께 저장하며, 다음날 "마지막 거래 시 어떤 이유로 그 결정을 내렸는가"를 반환한다. 이 세 가지 데이터는 시뮬레이션 분석의 핵심 원천이다.

### News Agent

에이전트의 페르소나와 오늘 날짜를 입력받아 뉴스 컨텍스트를 반환하는 서비스 모듈이다. 에이전트별 Depth(0, 1, 2)에 따라 반환하는 정보의 깊이가 달라진다. Depth 0은 일일 뉴스 제목 10개만 제공한다. Depth 1은 제목 10개와 해당 요약본 10개를 자동 제공한다. Depth 2는 Depth 1 정보에 더해 LLM이 추가 탐색 필요성과 키워드를 결정하고, 최근 7일 뉴스 풀에서 관련 요약본 10개를 검색해 반영한다. 뉴스 수집, 전처리, 일일 선정 로직의 세부 동작은 `News_System_Design.md`에서 정의한다.

### Fundamental Agent

삼성전자(005930)의 시장 데이터를 반환하는 서비스 모듈이다. 날짜를 입력받아 `Matching_System_Design.md`의 StockData 테이블에서 해당 일의 종가, 전일 대비 수익률, 거래량 변화율, 5일 이동평균, 20일 이동평균, 20일 변동성을 조회하여 반환한다. 이 데이터는 에이전트가 현재 시장의 기술적 상태를 파악하는 데 사용된다.

### Exchange Market Agent

주문 접수와 체결을 담당하는 서비스 모듈이다. Central Trading Agent로부터 주문(방향, 수량, 가격 유형)을 접수하고, 시뮬레이션 단계(Phase)에 따라 처리 방식이 달라진다. Day 1~3(Phase 1)은 개별 가격으로 즉시 체결하여 에이전트별 다양한 평단가를 형성하고, Day 4 이후(Phase 2/3)는 실가격 앵커 집합경매 방식으로 처리한다. 체결 결과를 반환하면 Memory Agent가 portfolio_state를 업데이트한다. 세부 알고리즘은 `Matching_System_Design.md`에서 정의한다.

### Community Agent (추후 추가 예정)

포럼 커뮤니티와의 상호작용을 담당하는 서비스 모듈이다. 커뮤니티 기능이 활성화된 경우에만 동작하며, 다른 에이전트의 포럼 글을 제공하거나 Central Trading Agent의 게시물을 처리한다. 현재 시뮬레이션에서는 비활성 상태로 설계에만 포함한다.

---

## 3. 전체 시스템 흐름

### 초기화 및 멀티데이 루프

```
╔══════════════════════════════════════════════════════════════════╗
║                  TwinMarket Korea — 전체 시스템 흐름               ║
╚══════════════════════════════════════════════════════════════════╝

[페르소나 선발: sys_1000.db → sys_100.db]   ← Persona_Distribution_First_Upgrade.md
(1000명 풀에서 100개 슬롯에 가중 선발, agents 테이블 생성)
        ↓
[시뮬레이션 시작]
        ↓
[sys_100.db 로드]
(100명 에이전트, 페르소나 + 행동 프로파일)
        ↓
[portfolio_state_t000 초기화]
(모든 에이전트: 보유 주식 없음, 현금 = ini_cash)
        ↓
[Initial Belief 생성]                ← 페르소나만 사용, 뉴스·시장 데이터 없음
(6차원 CoT 방식, 자연어 서술)
        ↓
┌────────────────────────────────────────────────────────────────┐
│  Day 1  [Phase 1: INDIVIDUAL_EXECUTION]                        │
│                                                                │
│  입력: initial_belief_i + portfolio_t000_i                     │
│       + news_t001 (News Agent) + market_t001 (Fundamental)    │
│            ↓                                                   │
│     collect_context (today_context 조립)                       │
│            ↓                                                   │
│     [LLM #1] update_belief → belief_t001                      │
│            ↓  belief_t001 → Memory Agent 저장                  │
│     [LLM #2] make_decision → trading_decision_t001            │
│            ↓                                                   │
│     execute_trade → Exchange Market Agent (Phase 1 체결)       │
│            ↓                                                   │
│     portfolio_state_t001 + trade_log_t001 → Memory Agent 저장  │
└──────────────────────────────┬─────────────────────────────────┘
                               ↓
┌────────────────────────────────────────────────────────────────┐
│  Day 2  [Phase 1 또는 2, day_number 기준]                       │
│                                                                │
│  입력: belief_t001_i + portfolio_t001_i + action_reason_t001   │
│       + news_t002 (News Agent) + market_t002 (Fundamental)    │
│            ↓                                                   │
│     collect_context → update_belief → make_decision           │
│            ↓                                                   │
│     execute_trade → portfolio_state_t002 저장                  │
└──────────────────────────────┬─────────────────────────────────┘
                               ↓
                         Day 3 ... 반복
                    (Day 4부터 Phase 2/3 전환)
```

### 하루 단위 에이전트 상호작용

```
Central Trading Agent  (에이전트 i, Day t, t ≥ 1)

  ┌────────────────────────────────────────────────────────────────────┐
  │                        collect_context                             │
  │                                                                    │
  │  → Memory Agent 요청 (3가지):                                      │
  │      ① 이전 Belief: belief_history[i][t-1]                         │
  │         (Day 1은 initial_belief 사용)                               │
  │      ② 포트폴리오 요약: portfolio_state[i][t-1]                    │
  │         (보유 현금, 종목, 수량, 평균 매수 단가, 미실현 손익, 수익률)  │
  │      ③ 최근 거래 결정 근거: trade_log[i][last_trade].action_reason  │
  │         (첫 거래 전 or hold 연속 시 null)                           │
  │                                                                    │
  │  → News Agent 요청:                                                │
  │      입력: agent_id, date, persona(Depth, 뉴스 민감도)              │
  │      출력: 일일 뉴스 제목 10개 + 에이전트 선택 본문 (0~3개)          │
  │      (Depth 2: 추가 search_news 결과 포함 가능)                     │
  │      → 상세: News_System_Design.md                                  │
  │                                                                    │
  │  → Fundamental Agent 요청:                                         │
  │      입력: stock_code="005930", date=t                              │
  │      출력: {close, pct_chg, volume_chg, ma5, ma20, volatility_20d} │
  │      → 데이터 소스: StockData (Matching_System_Design.md)           │
  │                                                                    │
  │  ← 위 세 응답을 today_context로 조립                                │
  └────────────────────────────────┬───────────────────────────────────┘
                                   ↓
                           [LLM Call #1]
                         update_belief
              입력: persona_prompt + today_context
              출력: today_belief (6차원 CoT → 통합 자연어 Belief)
                                   ↓
              → Memory Agent: belief_history[i][t] = today_belief
                                   ↓
                           [LLM Call #2]
                          make_decision
       입력: persona_prompt + today_belief
           + portfolio_summary + trading_constraints
              출력: trading_decision
                    (action, quantity, price, reason, risk_control)
                                   ↓
     → Exchange Market Agent: 주문 전달
       입력: {agent_id, stock_code, direction, quantity, price, timestamp}
       출력: {executed_price, executed_quantity, fee}
       → Phase 분기: Matching_System_Design.md Phase 시스템 참조
                                   ↓
     → Memory Agent 업데이트:
       · portfolio_state[i][t] (체결 결과 반영)
       · trade_log[i][t] (action, quantity, price, action_reason 저장)
```

---

## 4. LLM 호출 구조

에이전트당 하루 기본 2회의 LLM 호출이 이루어진다. 커뮤니티 기능이 활성화되면 포럼 게시 생성에 추가 호출이 발생한다.

```
에이전트 i, Day t

┌─────────────────────────────────────────────────────────────────┐
│  LLM Call #1 — update_belief                                    │
│                                                                 │
│  입력:  persona_prompt                                          │
│       + today_context {                                         │
│           previous_belief  : 이전 자연어 Belief 요약             │
│           portfolio_summary: 현금/보유/손익 구조화 텍스트         │
│           action_reason    : 마지막 거래 근거 (없으면 null)       │
│           news_context     : 제목 10개 + 선택 본문               │
│           market_features  : 종가/수익률/거래량/MA/변동성         │
│       }                                                         │
│                                                                 │
│  출력:  today_belief {                                          │
│           6개 차원 텍스트 (각 1-2문장)                           │
│           통합 belief_summary (1-3문장)                          │
│           view_change (이전 대비 방향 변화)                      │
│       }                                                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  LLM Call #2 — make_decision                                    │
│                                                                 │
│  입력:  persona_prompt                                          │
│       + today_belief (belief_summary)                           │
│       + portfolio_summary (현재 현금, 보유 수량, 평단가, 손익)   │
│       + trading_constraints {                                   │
│           available_cash   : 실제 사용 가능 현금                 │
│           current_quantity : 현재 보유 수량                      │
│           current_price    : 오늘 종가                           │
│           commission_rate  : 수수료율                            │
│           min_order_unit   : 최소 주문 단위                      │
│       }                                                         │
│                                                                 │
│  출력:  trading_decision {                                      │
│           action     : "buy" | "sell" | "hold"                  │
│           quantity   : 수량 (hold이면 0)                         │
│           order_type : "market" | "limit"                       │
│           price      : 지정가 (market이면 0)                    │
│           reason     : 결정 근거 자연어                          │
│           risk_control: 리스크 관리 방침                        │
│       }                                                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. 시뮬레이션 초기화

시뮬레이션이 시작되기 전 페르소나 선발과 세 가지 초기화가 순서대로 이루어진다.

### 단계 0: 페르소나 선발 (sys_1000.db → sys_100.db)

시뮬레이션 본 루프에 앞서, `Persona_Distribution_First_Upgrade.md`의 절차에 따라 `sys_1000.db`(Profiles 테이블, 1000명 풀)에서 100명을 선발하여 `sys_100.db`(agents 테이블)를 생성한다. 100개의 고정 슬롯(A001~A100, 성별·나이·자산군 사전 확정)을 정의하고, 각 슬롯의 성별·연령대·자산군 세그먼트가 요구하는 행동 프로파일과의 일치도를 가중치로 삼아 풀에서 가중 랜덤 선발한다(1인 1슬롯). 풀의 행동 편향 칼럼은 그대로 가져오고, 성별·나이·지역은 슬롯에서 새로 부여하며, 중국어 값(`高`/`中`/`低` 등)은 영문으로 매핑한다. 이 단계는 시뮬레이션마다 한 번만 실행되며, 결과 `sys_100.db`는 이후 단계의 입력이 된다.

### 단계 1: sys_100.db 로드

생성된 `sys_100.db`(agents 테이블)를 읽어 100명 에이전트의 페르소나를 메모리에 로드한다. 각 에이전트는 `agent_id`, `persona_prompt`, `bh_*_category`, `strategy`, `ini_cash`, `gender`, `age`, `location`, `user_type`, `fol_ind`, `trad_pro` 등의 정적 속성을 가진다. 이 값들은 시뮬레이션 전반에 걸쳐 변경되지 않는다.

### 단계 2: portfolio_state_t000 생성

모든 에이전트에 대해 초기 포트폴리오 상태를 생성한다. 보유 주식은 없고 현금만 있는 상태에서 시작한다.

```
portfolio_state_t000 (전 에이전트 공통):
  보유 주식  : 없음 (빈 포지션)
  보유 현금  : ini_cash (에이전트별 1억 or 10억)
  총 자산    : ini_cash
  누적 수익  : 0
  전일 수익  : null
```

### 단계 3: Initial Belief 생성

Day 1에는 이전 Belief가 존재하지 않는다. 이 문제를 해결하기 위해, 시뮬레이션 시작 직전에 각 에이전트의 persona_prompt만을 입력으로 사용하여 Initial Belief를 생성한다. 이 단계에서는 뉴스나 시장 데이터가 없으며, 오직 에이전트의 성격과 투자 성향만이 관점을 결정한다. 6차원 CoT 방식(Section 7 참조)으로 각 차원을 자연어로 서술하고, 이를 통합하여 하나의 Initial Belief 텍스트를 생성한다. 이 Initial Belief는 Day 1의 collect_context에서 "이전 Belief"로 전달되어, Day 1도 Day 2 이후와 동일한 파이프라인으로 처리된다.

---

## 6. 일별 처리 사이클 — 4단계 상세

### Phase 1: collect_context

collect_context는 Central Trading Agent가 하루를 시작하면서 가장 먼저 수행하는 단계다. 이 단계는 판단을 내리지 않는다. "오늘 매수해야 하는가?", "이 뉴스가 긍정적인가?"와 같은 해석은 하지 않는다. 이 단계의 유일한 역할은 판단에 필요한 모든 재료를 수집하고 today_context라는 하나의 구조화된 묶음으로 조립하는 것이다.

**Memory Agent 요청 (3가지)**

첫 번째로 이전 Belief를 요청한다. belief_history에서 이 에이전트의 t-1 Belief를 로드한다. Day 1은 Initial Belief를 사용한다. LLM에게는 이전 belief_summary 텍스트만 전달하며, 6차원 개별 서술은 분석 목적으로만 보존된다.

두 번째로 포트폴리오 요약을 요청한다. portfolio_state[t-1]에서 현재 상태를 구조화된 텍스트로 반환한다. 포함 항목: 보유 현금, 보유 종목 수량, 현재가 기준 평가액, 평균 매수 단가, 미실현 손익, 총 자산 대비 현금 비중, 누적 수익률. 에이전트는 자신의 재무 상태를 알아야 오늘 거래 여력과 한계를 파악할 수 있다.

세 번째로 최근 거래 결정 근거를 요청한다. trade_log에서 마지막 실제 매수 또는 매도의 action_reason을 반환한다. 이 정보는 에이전트가 자신의 직전 판단을 맥락으로 삼아 오늘 관점을 형성하는 데 사용된다. 이전 거래가 없거나 마지막 행동이 hold인 경우 null로 처리된다.

**News Agent 요청**

입력: agent_id, date, persona(Depth, 뉴스 민감도, 관심 분야)
출력: 일일 뉴스 제목 10개(제목·날짜·종류) + 에이전트가 선택하여 읽은 본문(0~3개)

News Agent는 이 에이전트의 Depth를 확인하고 적절한 뉴스 컨텍스트를 구성한다. Depth 1 에이전트는 일일 뉴스 제목 10개를 기본으로 받으며, `read_news` 도구로 최대 3개 본문을 추가 읽을 수 있다. Depth 2 에이전트는 여기에 `search_news` 도구를 통한 최근 7일 뉴스 탐색까지 가능하다. 에이전트가 어떤 뉴스를 읽을지 결정하는 주체는 LLM이다. 뉴스 전처리, 일일 선정 로직, Depth별 동작의 세부 사항은 `News_System_Design.md`를 참조한다.

**Fundamental Agent 요청**

입력: stock_code="005930", date=t
출력: {close, pct_chg, volume_chg, ma5, ma20, volatility_20d}

Matching_System_Design.md의 StockData 테이블에서 해당 일의 시장 데이터를 조회하여 반환한다. 반환되는 종가는 실제 삼성전자 종가다(Phase 2/3에서 체결 기준가가 되는 값과 동일).

**today_context 조립**

세 모듈로부터 받은 정보를 하나의 구조화된 객체로 패키징한다.

```
today_context = {
  "agent_id"         : "A001",
  "turn"             : 12,
  "date"             : "2026-01-15",

  "previous_belief"  : "어제 삼성전자에 대해 중립적 관점을 유지했다. 반도체
                        업황 개선 신호는 있으나 단기 가격 상승 부담이 있었다.",

  "action_reason"    : "10일 전 추가 매수 당시, 반도체 가격 반등 기대와
                        현금 비중이 충분하다는 판단에 근거했다.",  (null 가능)

  "portfolio_summary": "보유 현금 8,500만원, 삼성전자 200주 보유.
                        평균 매수 단가 72,500원, 현재가 73,500원 (미실현
                        손익 +200,000원). 총 자산 99,700,000원, 수익률 -0.3%.",

  "news_context"     : {
    "daily_titles"   : [10개 뉴스 제목·날짜·종류],
    "read_contents"  : [에이전트가 선택 읽기한 뉴스 본문 목록]
  },

  "market_features"  : {
    "ticker"       : "005930",
    "close"        : 73500,
    "pct_chg"      : 0.012,
    "volume_chg"   : 0.18,
    "ma5"          : 72800,
    "ma20"         : 71000,
    "volatility_20d": 0.021
  }
}
```

### Phase 2: update_belief (LLM Call #1)

update_belief는 today_context를 바탕으로 에이전트의 오늘 시장 관점, 즉 today_belief를 형성하는 단계다. 이 단계는 거래 결정을 내리지 않는다. "매수해야 한다", "오늘은 팔아야 한다"는 행동 지시는 today_belief에 포함되지 않는다.

**6차원 CoT 방식**

LLM은 여섯 가지 차원을 순서대로 자연어로 서술하는 Chain-of-Thought 방식으로 today_belief를 생성한다. 각 차원은 한두 문장의 자연어 텍스트로 서술되며, 앞의 차원이 뒤 차원의 서술에 자연스럽게 연결된다.

1. **미래 1개월 시장 방향**: 오늘 수집한 정보를 종합했을 때 향후 한 달간 삼성전자 주가가 어떤 방향으로 움직일 것으로 보이는지, 그 근거는 무엇인지를 서술한다.
2. **현재 시장 밸류에이션**: 현재 삼성전자 주가가 내재가치 대비 어느 수준에 있다고 보는지, 기술적 지표와 뉴스를 바탕으로 서술한다.
3. **향후 거시경제**: 금리, 환율, 반도체 업황, 글로벌 경기 흐름 등 거시적 환경이 삼성전자에 어떤 영향을 줄 것으로 보이는지 서술한다.
4. **현재 시장 심리**: 현재 시장 전체에 어떤 분위기가 지배적인지, 그것이 이 에이전트의 판단에 어떻게 작용하는지 서술한다.
5. **뉴스에 대한 본인의 생각**: 오늘 접한 주요 뉴스를 어떻게 해석하는지, 그것이 기존 관점을 강화하는지 혹은 바꾸는지 서술한다.
6. **자기 투자 능력 평가**: 자신이 현재 이 시장을 잘 판단하고 있는지, 최근 결정들을 돌아보며 확신 또는 불확실함을 느끼는지 서술한다.

여섯 차원을 채운 후 LLM은 이를 통합하여 하나의 belief_summary 단락을 완성한다. 이것이 다음날 "이전 Belief"로 전달되는 텍스트다.

**저장**

today_belief가 생성되면 즉시 Memory Agent를 통해 belief_history에 저장된다. 이 저장은 커뮤니티 기능 활성화 여부와 무관하게 항상 수행된다. 저장된 Belief는 생성 후 수정되지 않으며, 이후 모든 단계에서 읽기 전용으로만 참조된다.

### Phase 3: make_decision (LLM Call #2)

make_decision은 today_belief와 현재 포트폴리오 상태를 바탕으로 실제 거래 결정을 내리는 단계다. 이 단계는 Belief를 다시 해석하거나 요약하지 않는다. Belief는 이미 형성되어 있으며, make_decision은 그것을 읽어서 행동으로 번역하는 역할만 한다.

LLM은 persona_prompt, today_belief(belief_summary), portfolio_summary, trading_constraints를 입력받아 세 가지 행동 중 하나를 결정한다: 매수(buy), 매도(sell), 보유(hold). 매수 또는 매도를 결정한 경우 수량과 근거도 함께 결정한다. 보유를 결정한 경우에도 왜 오늘 행동하지 않기로 했는지 근거를 기술한다. 이 근거(action_reason)는 다음날 collect_context에서 Memory Agent를 통해 전달된다.

trading_constraints에는 available_cash, current_quantity, current_price, commission_rate, min_order_unit이 포함된다. LLM은 이 제약 안에서 수량을 결정하도록 자연스럽게 유도된다.

### Phase 4: execute_trade

execute_trade는 make_decision의 결과를 Exchange Market Agent에 전달하여 체결하는 단계다. 체결 방식은 시뮬레이션 단계(Phase)에 따라 달라진다.

| 시뮬레이션 Day | Phase | 체결 방식 |
|--------------|-------|---------|
| Day 1 ~ 3 | Phase 1 | 개별 제출가 즉시 체결 (에이전트별 다른 평단가 형성) |
| Day 4 ~ 7 | Phase 2 | 실가격 앵커 집합경매 (분석 제외 구간) |
| Day 8 ~ | Phase 3 | 실가격 앵커 집합경매 (본격 분석 구간) |

Phase 분기와 매칭 알고리즘(INSTITUTIONAL 주입, 서킷브레이커 처리 등)의 세부 사항은 `Matching_System_Design.md`를 참조한다.

체결이 완료되면 Memory Agent는 두 가지를 업데이트한다. **portfolio_state[i][t]**: 매수 시 현금 감소·수량 증가, 매도 시 수량 감소·현금 증가, 보유 시 수량 변화 없음·미실현 손익만 재계산. **trade_log[i][t]**: 체결 방향, 수량, 가격, 수수료, action_reason을 함께 기록. hold 결정도 거래 없음 레코드로 기록되어 결정의 근거가 보존된다.

---

## 7. Belief 시스템 상세

### Belief란 무엇인가

Belief는 에이전트의 private 시장 관점이다. 특정 시점에 이 에이전트가 삼성전자와 주식 시장 전반에 대해 어떤 생각을 가지고 있는지를 자연어로 명시화한 내면 상태다. Belief는 외부에 공개되지 않으며, 에이전트의 모든 행동이 참조하는 공통 근거다.

Belief가 시스템에 필요한 이유는 세 가지다. 첫째, 행동의 일관성을 부여한다. Belief가 없으면 에이전트는 매일 백지 상태에서 뉴스에 즉각 반응하는 단순 자극-반응 기계가 된다. Belief가 있으면 어제의 생각 위에서 오늘의 생각을 발전시키며 인간다운 행동 궤적을 만든다. 둘째, 행동의 근거를 추적할 수 있게 한다. 어떤 에이전트가 특정 날 매수했다면, 그 날의 Belief를 조회하여 어떤 시장 관점이 그 결정을 이끌었는지 소급할 수 있다. 셋째, 거래 행동과 커뮤니티 행동을 하나의 일관된 "뇌"로 묶는다. 에이전트가 포럼에 쓰는 글도, 매매 결정도 같은 Belief에서 출발하기 때문에 발화와 행동 사이의 일관성 또는 불일치를 분석할 수 있다.

### Belief 객체 구조

```
belief_history 레코드:
  belief_id      : "belief_A001_t012" (에이전트 ID + 턴 번호)
  agent_id       : "A001"
  turn           : 12
  date           : "2026-01-15"

  dim_1_market_direction  : "반도체 업황 개선 기대로 향후 한 달 내 완만한
                             상승 가능성이 있다고 본다. 단 단기 과열 신호가
                             상승 폭을 제한할 것이다." (최대 150자)

  dim_2_valuation         : "현재 주가는 PBR 기준 역사적 평균 대비 소폭
                             고평가 구간으로, 추가 매수에 신중해야 한다." (최대 100자)

  dim_3_macro             : "글로벌 금리 인하 기대와 원화 강세가 외국인
                             수급에 긍정적으로 작용할 것으로 예상한다." (최대 100자)

  dim_4_market_sentiment  : "시장 심리는 중립과 낙관 사이로, 추가 악재
                             없이는 현 수준에서 지지될 가능성이 높다." (최대 100자)

  dim_5_news_interpretation: "오늘 HBM 수요 증가 뉴스는 긍정적이나, 이미
                              주가에 상당 부분 반영된 것으로 해석한다." (최대 100자)

  dim_6_self_assessment   : "최근 판단의 정확도는 보통 수준. 추가 매수보다
                             관망이 적합하다고 스스로 평가한다." (최대 100자)

  belief_summary : 위 6개 차원을 통합한 1-3문장 자연어 단락
                   (다음날 collect_context에서 "이전 Belief"로 전달되는 값)

  view_change    : "neutral_to_slightly_positive" (이전 대비 방향 변화 설명)
```

### Belief 업데이트 원칙

Belief는 덮어쓰기가 아닌 누적 방식으로 저장된다. 매일의 Belief가 belief_history에 독립적인 레코드로 저장되며, 이전 날의 Belief는 삭제되지 않는다. 다음날 collect_context에서는 직전 턴의 belief_summary만 이전 Belief로 제공되지만, 전체 history는 분석 목적으로 보존된다.

Belief는 update_belief 단계에서만 생성되고 저장된다. make_decision 단계나 포럼 글 작성 단계에서 Belief는 읽기 전용으로 참조될 뿐이며, 수정이나 덮어쓰기는 발생하지 않는다.

### Initial Belief와 일반 Belief의 차이

Initial Belief는 시뮬레이션 시작 전 페르소나만으로 생성된다. 뉴스, 시장 데이터, 포트폴리오 정보 없이 6차원 CoT를 수행하기 때문에 각 차원의 서술은 에이전트의 기본 투자 성향을 반영한 초기 상태를 기술한다. 이 Initial Belief는 belief_history에 turn=0으로 저장되며, Day 1의 collect_context에서 이전 Belief로 사용된다. Day 1부터 정상적인 LLM Call #1이 실행되어 첫 번째 실제 Belief(turn=1)가 생성된다.

---

## 8. 데이터 저장 구조 참고 형식

이 섹션은 에이전트 의사결정 프레임워크가 생성하고 유지하는 핵심 테이블의 개념적 스키마를 정의한다. 매칭 엔진이 관리하는 TradingDetails와 StockData는 `Matching_System_Design.md`를 참조한다. 페르소나 테이블은 `sys_100.db`의 `agents` 테이블이며(원천 풀은 `sys_1000.db`의 Profiles 테이블), 선발 절차와 최종 스키마는 `Persona_Distribution_First_Upgrade.md`를 참조한다.

### belief_history 테이블

```
belief_history:
  belief_id        TEXT  PRIMARY KEY   "belief_{agent_id}_t{turn}"
  agent_id         TEXT                에이전트 식별자 (A001~A100)
  turn             INTEGER             시뮬레이션 턴 번호 (0=Initial, 1~)
  date             TEXT                날짜 (YYYY-MM-DD)
  dim_1            TEXT                미래 시장 방향 차원 텍스트
  dim_2            TEXT                밸류에이션 차원 텍스트
  dim_3            TEXT                거시경제 차원 텍스트
  dim_4            TEXT                시장 심리 차원 텍스트
  dim_5            TEXT                뉴스 해석 차원 텍스트
  dim_6            TEXT                자기 평가 차원 텍스트
  belief_summary   TEXT                통합 자연어 요약 (다음날 전달값)
  view_change      TEXT                이전 대비 관점 변화 서술
  created_at       TIMESTAMP           저장 시각

  특성: 생성 후 불변. 읽기 전용.
```

### portfolio_state 테이블

```
portfolio_state:
  state_id         TEXT  PRIMARY KEY   "ps_{agent_id}_t{turn}"
  agent_id         TEXT                에이전트 식별자
  turn             INTEGER             시뮬레이션 턴 번호
  date             TEXT                날짜
  cash             REAL                보유 현금 (원)
  positions        JSON                [{stock_code, quantity, avg_cost, current_price,
                                         unrealized_pnl, unrealized_pnl_rate}]
  total_value      REAL                총 자산 (현금 + 보유 주식 평가액)
  realized_pnl     REAL                누적 실현 손익
  total_return_rate REAL               초기 자산 대비 누적 수익률
  updated_at       TIMESTAMP           업데이트 시각

  특성: 매 턴 end-of-day 기준 스냅샷. turn=0은 초기 상태.
```

### trade_log 테이블

```
trade_log:
  log_id           TEXT  PRIMARY KEY   "tl_{agent_id}_t{turn}"
  agent_id         TEXT                에이전트 식별자
  turn             INTEGER             시뮬레이션 턴 번호
  date             TEXT                날짜
  action           TEXT                "buy" | "sell" | "hold"
  stock_code       TEXT                종목 코드 (005930 고정)
  quantity         INTEGER             수량 (hold이면 0)
  executed_price   REAL                체결가 (hold이면 null)
  trade_value      REAL                거래 금액 (hold이면 null)
  fee              REAL                수수료 (hold이면 0)
  action_reason    TEXT                결정 근거 자연어 (다음날 전달)
  risk_control     TEXT                리스크 관리 방침

  특성: hold도 기록됨. action_reason은 hold 시 다음날 전달 안 됨.
```

---

## 9. 엣지 케이스 처리

**Day 1 — Initial Belief 기반 처리**: Day 1의 이전 Belief는 시뮬레이션 시작 전 페르소나 기반으로 생성된 Initial Belief(turn=0)다. Day 1의 최근 거래 결정 근거는 없으므로 null로 처리된다. 이를 통해 Day 1도 Day 2 이후와 동일한 파이프라인으로 처리된다.

**보유(Hold) 결정**: make_decision의 출력이 hold인 경우에도 명시적인 결정으로 trade_log에 기록된다. hold의 action_reason은 trade_log에는 저장되지만, 다음날 collect_context에서 "최근 거래 결정 근거"로 전달되지는 않는다. 이 항목은 마지막 실제 매수 또는 매도의 근거만 해당한다.

**현금 부족으로 매수 불가**: make_decision의 입력인 trading_constraints에 available_cash가 명시되기 때문에, LLM은 가용 현금 범위 내에서 수량을 결정하도록 자연스럽게 유도된다. 현금이 최소 주문 단위(1주 × 현재가 + 수수료)에 미치지 못하면 매수 불가 상황임을 trading_constraints에 명시하고, LLM은 hold 결정을 내리도록 안내된다.

**전량 매도 후 포지션 없음**: 에이전트가 모든 주식을 매도한 경우 portfolio_state의 positions는 빈 배열이다. 다음날 collect_context의 portfolio_summary에 "현재 보유 종목 없음, 전액 현금 보유"가 명시된다. 이 정보를 바탕으로 LLM은 신규 매수 여부를 판단한다.

**매칭 엔진 관련 엣지 케이스**: 서킷브레이커 범위 이탈 주문, INSTITUTIONAL 주입 실패, Phase 전환 시점 처리 등은 `Matching_System_Design.md`의 엣지 케이스 섹션을 참조한다.

---

## 10. 검증 계획

**Belief 연속성 확인**: 특정 에이전트의 belief_history를 시계열로 조회했을 때, 관점이 합리적으로 진화하는지 확인한다. 강한 호재 뉴스가 있는 날 이후 dim_1(시장 방향)이 긍정 방향으로 이동하거나, Initial Belief에서 Day 1 Belief로의 변화가 페르소나와 일관성 있는 방향인지 샘플 검증한다.

**결정 추적성 확인**: 특정 거래(예: A030이 Day 15에 매수)에 대해 해당 날의 belief_summary와 trade_log의 action_reason이 논리적으로 일치하는지 확인한다. 또한 다음날 collect_context에 해당 action_reason이 올바르게 전달되었는지 검증한다.

**서비스 모듈 응답 정합성 확인**: Memory Agent가 반환하는 이전 Belief가 belief_history[t-1] 레코드와 동일한지, Fundamental Agent가 반환하는 종가가 Matching_System_Design.md의 StockData 테이블 값과 일치하는지, News Agent가 반환하는 뉴스가 해당 날짜의 processed_news에서 선별된 것인지 검증한다.

**포트폴리오 수치 일관성 확인**: 전 기간에 걸쳐 각 에이전트의 포트폴리오 상태가 수학적 정합성을 유지하는지 확인한다. 거래 전후 현금 변화량이 체결 금액 및 수수료와 일치하는지, 보유 수량이 누적 매수에서 누적 매도를 뺀 값과 일치하는지, 총 자산이 현금과 보유 주식 평가액의 합과 일치하는지를 전수 검증한다.

**서브시스템 연동 검증**: 이 문서의 각 단계가 참조 설계서와 정확히 인터페이스되는지 확인한다. collect_context → News Agent 요청의 입출력이 News_System_Design.md의 도구 명세와 일치하는지, execute_trade → Exchange Market Agent 주문 전달 형식이 Matching_System_Design.md의 order 객체 구조와 일치하는지, sys_1000.db에서 선발되어 생성된 sys_100.db의 페르소나 칼럼이 Persona_Distribution_First_Upgrade.md의 최종 스키마(agents 테이블)와 일치하는지를 통합 테스트로 검증한다. 추가로, 선발 직후 100명의 성별·연령대·자산군 분포가 고정 슬롯 정의와 정확히 일치하는지(편차 0)도 함께 확인한다.

---

*이 문서는 TwinMarket Korea 에이전트 의사결정 프레임워크의 최종 설계서다. 뉴스 처리 세부사항은 `News_System_Design.md`, 주문 매칭 엔진은 `Matching_System_Design.md`, 에이전트 페르소나 구성은 `Persona_Distribution_First_Upgrade.md`를 참조한다.*
