# 05. 문제점 및 개선 필요 사항 보고서

> **분석 기준 실행:** simulation_20260609_154102  
> **작성일:** 2026-06-10  
> **우선순위 기준:** 🔴 즉시 수정 필요 / 🟡 중요하지만 유예 가능 / 🟢 개선 권고

---

## 요약 — 발견된 주요 이슈 목록

| # | 카테고리 | 이슈 | 우선순위 |
|---|---|---|---|
| R-01 | 버그 | sim.db 재실행 시 데이터 섞임 / TradingDetails 중복 누적 | 🔴 |
| R-02 | 버그 | trade_log가 LLM 결정 기준으로 저장 — 실제 체결 결과 미반영 | 🔴 |
| B-01 | 버그 | 미실현 손익(unrealized_pnl) 계산 오류 — current_price 미업데이트 | 🔴 |
| B-02 | 설계 | 동시호가 시스템 미인식 + 미체결 피드백 부재 | 🟡 |
| B-03 | 버그 | 전액 투자 허용 — trading_constraints 최대 비율 제한 없음 | 🔴 |
| D-02 | 설계 | Depth 0/1/2 재설계 필요 — 현행 Depth 구조 및 뉴스 처리 방식 전면 개선 | 🔴 |
| D-03 | 설계 | 일일 뉴스 10개 선정 방식 — 고정 비율(5:3:2) → 해당일 풀 랜덤 선정으로 변경 | 🟡 |
| R-03 | 버그 | 보고서 수익률 계산이 1억 원으로 하드코딩 | 🟡 |
| D-04 | 문서 | 설계서 LLM 호출 횟수 기술 오류 (2회 → 실제 4회) | 🟢 |
| D-05 | 문서 | news_depth 칼럼이 Persona 설계서에 미반영 | 🟢 |
| V-02 | 검증 | Depth 2 에이전트 실제 동작 미검증 | 🟡 |
| V-03 | 검증 | INSTITUTIONAL 방향 vs 실제 기관 데이터 비교 (추후 데이터 확보 후 수행) | 🟢 |

---

## 🔴 즉시 수정 필요

### R-01: sim.db 재실행 시 데이터 섞임

**증상:**
`init_sim_db()`는 테이블을 CREATE IF NOT EXISTS만 수행하고 기존 데이터를 정리하지 않는다. `belief_history`, `portfolio_state`, `trade_log`는 `INSERT OR REPLACE`라 일부 덮어써지지만, `TradingDetails`는 계속 append된다. 같은 DB로 재실행하면 체결 내역이 이전 실행 것과 섞이거나 중복된다.

**영향:**
- 분석 시 여러 실행의 체결 내역이 하나의 TradingDetails에 뒤섞여 올바른 시뮬레이션 결과 해석 불가
- run_id가 없으면 어느 실행의 데이터인지 구분 불가

**수정 방향 (우선순위 순):**

옵션 A (권장): 실행 시작 시 새 `sim_{run_id}.db` 파일 생성
```python
# simulation.py 또는 05_run_simulation.py
db_path = f"outputs/sim_{run_id}.db"
```

옵션 B: 모든 핵심 테이블에 `run_id` 컬럼 추가 후 조회 시 항상 WHERE 조건 적용

옵션 C (최소): 시뮬레이션 시작 전 해당 테이블 레코드 명시적 삭제
```python
conn.execute("DELETE FROM TradingDetails")
conn.execute("DELETE FROM belief_history")
conn.execute("DELETE FROM portfolio_state")
conn.execute("DELETE FROM trade_log")
```

---

### R-02: trade_log가 실제 체결 결과를 반영하지 않음

**증상:**
현재 `trade_log`는 LLM의 거래 결정 직후 저장된다. 따라서 `action=buy, quantity=100`이어도 실제로 미체결일 수 있고, `executed_price`, `trade_value`는 계속 NULL로 남는다. 실제 체결 정보는 `TradingDetails`나 `exchange_fills.csv`에 따로 존재한다.

**실제 예시:**
- 2025-01-08 A012, A022, A047: `trade_log`에는 `action=buy`로 기록되지만 실제 체결 0건
- 분석에서 `trade_log`만 참조하면 미체결 주문을 실제 거래로 오해함

**영향:**
- 에이전트 행동 분석이 왜곡됨
- `collect_context`에서 이전 거래 이유를 참고할 때 미체결 주문이 "거래 성공"으로 전달됨

**수정 방향:**
체결 결과가 확정된 후 `trade_log`를 업데이트하거나 초기 저장 시 status를 pending으로 기록:

```python
# 1단계: LLM 결정 후 pending으로 저장
trade_log.append({..., "status": "pending", "filled_quantity": 0, "executed_price": None})

# 2단계: Exchange 체결 후 업데이트
trade_log.update(agent_id, turn, {
    "status": "filled" | "unfilled",
    "filled_quantity": actual_qty,
    "executed_price": fill_price
})
```

또는 `collect_context`에서 이전 trade_log 조회 시 `TradingDetails`와 JOIN하여 실제 체결 여부를 포함한 정보를 LLM에 전달.

---

### B-01: 미실현 손익(unrealized_pnl) 계산 오류

**증상:**
A011은 Day 1에 53,400원으로 1,872주 매수. Day 3 (2025-01-06) 종가 55,900원 기준 이론적 미실현 이익은 **(55,900 - 53,400) × 1,872 = 4,681,200원**. 그러나 실제 로그에는 `"unrealized_pnl": 0.0, "unrealized_pnl_rate": 0.0`으로 기록됨.

**위치:** `twinmarket_kr/agents/memory_agent.py` — `update_portfolio()` 함수

**예상 원인:**
- `positions`의 `current_price`가 매수 당시 가격으로 고정되어 매일 업데이트되지 않음
- 또는 `unrealized_pnl = (current_price - avg_cost) × quantity` 계산 시 `current_price` 조회가 실패하여 avg_cost와 같은 값으로 처리됨

**영향:**
- LLM이 잘못된 포트폴리오 손익 정보를 기반으로 의사결정 수행
- A011의 Turn 4, 5 Belief 업데이트에 "미실현 손익 0원"이 반영되어 결정 왜곡 가능성

**수정 방향:**
```python
# memory_agent.py: update_portfolio 또는 get_portfolio_summary 호출 시
# 매일 Fundamental Agent에서 당일 종가를 받아 current_price 갱신
for pos in positions:
    today_close = fundamental_agent.get_close_price(date, pos['stock_code'])
    pos['current_price'] = today_close
    pos['unrealized_pnl'] = (today_close - pos['avg_cost']) * pos['quantity']
    pos['unrealized_pnl_rate'] = pos['unrealized_pnl'] / (pos['avg_cost'] * pos['quantity'])
```

---

### B-03: 전액 투자 허용 — trading_constraints 최대 비율 제한 없음

**증상:**
A011이 Day 1에 현금 100,000,000원의 99.98%를 단 한 번에 매수 (1,872주 × 53,400원 = 99,964,800원). 잔액 20,205원 → 이후 4일간 현금 부족으로 강제 HOLD.

**현재 상태:**
`trading_constraints`는 `available_cash`와 `min_order_unit`만 확인함. 1,872주 × 53,400원이 available_cash 내에 있어 기술적으로 허용됨.

**설계 문서 확인 필요:**
`Overall_Framework_Design.md` §7 (Edge Case)에 전액 투자 제한 규정 존재 여부 확인 후 처리.

**수정 방향:**
에이전트 페르소나 프롬프트(`update_belief.txt` 또는 `make_decision.txt`)에 "현금 관리 원칙: 단일 거래에 보유 현금의 XX% 이상 투자 금지"를 행동 편향 속성으로 반영하거나, `build_trading_constraints()`에서 상한 수량을 직접 클램핑:

```python
# llm/decision.py build_trading_constraints()
MAX_SINGLE_TRADE_RATIO = 0.5  # 단일 거래 최대 50% (조정 가능)
max_quantity_by_cash = int(available_cash * MAX_SINGLE_TRADE_RATIO / current_price)
max_allowed_quantity = min(max_quantity_by_cash, position_limit)
```

---

## 🟡 중요하지만 유예 가능

### B-02: 동시호가 시스템 미인식 + 미체결 피드백 부재

**증상:**
Day 5 (Phase 2)에서 A012, A022, A047이 실 종가(57,300원)보다 낮은 지정가(56,500~57,200원)로 매수 주문을 제출하여 전량 미체결.

| 에이전트 | 제출가 | 실종가 | 차이 |
|---|---|---|---|
| A012 | 57,200원 | 57,300원 | -100원 |
| A022 | 57,000원 | 57,300원 | -300원 |
| A047 | 56,500원 | 57,300원 | -800원 |

**근본 원인 — 두 가지 층위:**

**① 동시호가(Call Auction) 시스템 미인식**
에이전트 프롬프트에 이 시장이 동시호가(단일가) 방식으로 운영된다는 정보가 전달되지 않고 있을 가능성이 높음. 에이전트가 연속매매(continuous trading) 방식으로 주문을 내듯 "저가 지정매수"를 시도하면 Phase 2 이후에는 구조적으로 미체결이 된다.

> **조사 항목:** `make_decision.txt` 및 `market_analysis.txt` 프롬프트에 "동시호가", "단일가", "call auction" 등의 개념이 포함되어 있는지 확인. 없다면 에이전트의 내재 지식(LLM이 한국 주식시장 동시호가 개념을 알고 있는지)을 먼저 검토. 내재 지식만으로 충분하다면 별도 명시 불필요.

**② 미체결 피드백 부재**
현재 미체결이 발생해도 에이전트는 다음날 "내 주문이 어제 체결되지 않았다"는 사실을 알지 못함. `collect_context`에서 이전 거래 결과를 참조할 때 체결 여부 정보가 포함되지 않음.

**개선 방향:**
`collect_context` 또는 `Memory Agent.get_trade_summary()`에서 이전 거래일 미체결 정보를 포함:
```
어제 제출한 주문: 005930 매수 100주 지정가 57,200원
체결 결과: 미체결 (당일 종가: 57,300원 / 제출가: 57,200원)
```
구체적인 체결 조건은 명시하지 않고 종가와 제출가의 차이만 제공하여 에이전트 스스로 원인을 파악하도록 유도. "주문가 ≥ 종가 조건"을 직접 명시하는 것은 불필요 (내재 지식으로 처리 가능).

---

### D-02: Depth 0/1/2 재설계 — 뉴스 툴 구조 전면 점검 및 Depth 2 Flow 개선

**현행 문제점 요약:**
- Depth 1 에이전트가 모든 구간에서 `read_news_count=3` 고정으로 관찰됨 — 자율적 선택 없음
- Depth 2 에이전트 없이 실행되어 검증 불가
- Depth 1 → 2 전환 시 에이전트 내부 사고 흐름이 로그에 전혀 남지 않음
- **설계서의 "Agentic Tool Calling"이 코드에 실제로 구현되지 않음** (아래 상세 분석)

---

---

#### 현행 Tool 구현 상태 분석 — 설계서 vs 코드 정합성 검토

**설계서(News_System_Design.md §4)의 의도:**
> "`read_news`와 `search_news` 두 가지 도구. 시스템은 읽기 예산과 사용 가능한 도구만 정의하고, 어떤 뉴스를 읽을지는 에이전트가 자신의 상황에 맞게 판단하도록 한다."

설계서가 말하는 "Agentic Tool Calling"은 **LLM이 실시간으로 도구를 호출(function call)하며 스스로 검색 전략을 결정하는 구조**다.

**실제 코드가 구현한 방식:** (`daily_cycle.py` + `news_agent.py`)

```
[현재 코드 흐름 — 진짜 Tool Calling이 아님]

1. interpret_news(LLM 호출) → JSON 반환
   출력: { "selected_news": ["제목A", "제목B", "제목C"], ... }

2. Python 코드가 selected_news를 받아서 news_agent.read_news() 직접 호출
   (LLM이 read_news를 호출하는 것이 아님, Python이 대신 실행)

3. Depth 2인 경우: Python이 _depth2_search_fields() 자동 생성
   (LLM의 판단 없이 DEFAULT_DEPTH2_FIELDS 하드코딩 키워드로 결정)
   DEFAULT_DEPTH2_FIELDS = [
     {"field": "HBM", "keywords": ["HBM", "메모리", "고대역폭"]},
     {"field": "파운드리", "keywords": ["파운드리", "2나노", "수주"]},
     {"field": "반도체 업황", "keywords": ["반도체", "업황", "수출", "장비"]},
     {"field": "거시 수급", "keywords": ["금리", "환율", "외국인", "코스피"]},
   ]

4. Python이 search_news() 자동 실행 → 결과를 context에 append
```

**핵심 문제: LLM은 search를 "결정"하지 않는다.**
- `_depth2_search_fields()`: 읽은 뉴스 본문에 HBM/파운드리/반도체 등 키워드가 포함되어 있으면 해당 필드를 자동 선택. LLM이 "이 분야가 더 궁금하다"고 판단하는 것이 아님.
- Depth 2 에이전트가 어떤 검색을 했는지 LLM은 모름. Python이 뒤에서 처리한 것.

**현행 도구별 구현 상태 정리:**

| 도구 | 설계 의도 | 실제 구현 | 정합성 |
|---|---|---|---|
| `read_news` | LLM이 읽고 싶은 뉴스를 자율 선택해 호출 | LLM이 selected_news JSON으로 제목 반환 → Python이 호출 | ⚠️ 방식은 다르나 결과는 유사 |
| `search_news` | LLM이 궁금한 분야를 키워드로 결정해 호출 | Python이 `_depth2_search_fields()`로 자동 생성 → 자동 호출 | ❌ LLM 관여 없음 |
| `news_agent.txt` 프롬프트 | 도구 스키마/사용 방법을 LLM에게 알려주는 프롬프트 | 단 5줄, 도구 스키마 없음 | ❌ 사실상 미구현 |

**`search_news` 반환값 구조 문제:**
현재 `search_news`는 분야별(field_name)로 그룹핑된 결과를 반환하고, 각 분야당 **제목만** 반환(본문 없음). 이후 `read_news`를 추가로 호출해야 본문을 얻는다.

```python
# 현재 search_news 반환 구조
{
  "HBM": [{"id": ..., "title": ..., "date": ..., "type": ...}, ...],  # 제목만
  "파운드리": [...],
  ...
}
# → 이후 search_read_contents = read_news(titles=..., max_items=5) 추가 호출
```

**신규 요구: category 무관, 키워드 관련도 기준 flat 랭킹**
사용자 요구사항: *"Depth 2 검색은 섹터와 상관없이 검색한 것 중 쿼리/키워드 검색에 관련 있는 뉴스를 가져와야 한다."*

→ field 분류를 제거하고, 키워드 관련도 점수 기준으로 전체 풀을 flat 랭킹하여 상위 10개 요약 반환.

---

#### 신규 설계: Depth 0 / 1 / 2 3단계 정의

| Depth | 설명 | 뉴스 처리 방식 |
|---|---|---|
| **Depth 0** | 헤드라인 스캔 | 일일 뉴스 10개 제목만 수신. 요약·본문 없음. Belief 업데이트 → 결정 |
| **Depth 1** | 요약본 전독 | 10개 헤드라인 + 10개 요약본 **자동 전체 제공** (선택 없이 시스템이 전달). Belief 업데이트 → 결정 |
| **Depth 2** | 심층 탐색 | Depth 1과 동일하게 10개 요약본 수신 후, **Agentic Search**로 최근 7일 풀에서 추가 10개 요약 획득. 통합 Belief 업데이트 → 결정 |

**공통 기반 (Depth 0/1/2 전부 동일):**
매일 D-03에서 정의한 카테고리별 랜덤 샘플링으로 확정된 **10개 헤드라인**을 모든 에이전트가 공통으로 받는다. Depth에 따라 그 위에 얼마나 깊이 파고드는지만 달라진다.

---

#### Depth 1 변경 사항

- **기존**: 헤드라인 10개 → LLM이 read_news 호출 여부를 자율 결정 (최대 3개)
- **신규**: 헤드라인 10개 + **10개 요약본 전체를 시스템이 자동 전달** (LLM이 read_news를 별도 호출할 필요 없음)
- 결과적으로 `read_news_count=10`이 고정되며 이것이 정상 동작
- LLM은 받은 요약본을 바탕으로 Belief를 업데이트하고 거래 결정을 내림

---

#### Depth 2 내부 Flow — 단계별 상세 설계

Depth 2의 핵심은 **읽고 나서 무슨 생각이 생겼는지, 어디가 더 궁금한지, 어떤 키워드로 어떻게 찾았는지, 찾고 나서 생각이 어떻게 바뀌었는지**를 연결된 흐름으로 기록하는 것이다.

```
╔══════════════════════════════════════════════════════════════════╗
║              Depth 2 에이전트 — 하루 뉴스 처리 전체 Flow           ║
╚══════════════════════════════════════════════════════════════════╝

[Step 1] 공통 기반 수신 (Depth 0/1/2 동일)
  ├─ 오늘 날짜의 10개 헤드라인 수신
  └─ 10개 뉴스 요약본 자동 수신 (시스템 제공)

         ↓

[Step 2] 1차 독해 및 Pre-Search Thinking  ← LLM 내부 추론
  ├─ 오늘 뉴스에서 핵심적으로 파악한 내용은 무엇인가?
  ├─ 현재 Belief와 비교했을 때 새롭게 확인된 것은?
  ├─ 불확실하거나 더 알고 싶은 부분이 있는가?
  └─ 추가 탐색이 필요하다면 어떤 방향으로 찾아야 하는가?

         ↓  (추가 탐색 필요 없다고 판단하면 Step 5로 스킵)

[Step 3] 검색 실행  ← search_news 도구 호출
  ├─ 탐색 분야/주제 결정 (LLM 자율)
  ├─ 키워드 조합 생성
  ├─ search_news(keywords, date_range=7일) 호출
  └─ 최근 7일 뉴스 풀에서 관련 뉴스 10개 요약본 수신

         ↓

[Step 4] Post-Search Thinking  ← LLM 내부 추론
  ├─ 추가로 읽은 내용에서 무엇을 새로 알게 되었나?
  ├─ 기존 생각이 강화/수정/반전되었나?
  ├─ Step 2에서 궁금했던 것이 해소되었나, 아니면 새로운 의문이 생겼나?
  └─ 최종적으로 통합된 관점은 무엇인가?

         ↓

[Step 5] 통합 Belief 업데이트
  기본 10개 요약 + (검색 10개 요약) 전체를 컨텍스트로
  6차원 CoT Belief 업데이트 → 거래 결정
```

---

#### Depth 2 전용 로그 구조 (신규 추가)

현재 `agent_turns.jsonl`에 없는 항목. Depth 2 에이전트에 한해 아래 필드를 추가 기록해야 한다.

```jsonl
{
  "run_id": "simulation_...",
  "date": "2025-01-03",
  "agent_id": "A007",
  "news_depth": 2,

  "depth2_flow": {
    "step1_base": {
      "headline_count": 10,
      "summary_count": 10
    },

    "step2_pre_search_thinking": {
      "key_findings": "HBM 테마 강세와 목표주가 하향이 동시에 나타나고 있어 단기 불확실성 존재. CES 모멘텀은 긍정적이나 실제 수요 전환 속도가 불명확.",
      "curiosity_points": [
        "HBM 시장에서 삼성전자와 엔비디아의 실제 협력 현황",
        "4분기 실적 부진의 구체적 원인 — 재고 조정인지 수요 감소인지"
      ],
      "search_needed": true,
      "search_rationale": "단기 목표주가 하향의 원인이 일시적 재고 조정인지 구조적 수요 감소인지 파악해야 매수/관망 결정 가능"
    },

    "step3_search": {
      "queries": [
        {
          "topic": "HBM 삼성-엔비디아 협력",
          "keywords": ["HBM", "엔비디아", "삼성전자", "납품"],
          "result_count": 5
        },
        {
          "topic": "삼성전자 4분기 실적 원인",
          "keywords": ["삼성전자", "4분기", "재고", "수요"],
          "result_count": 5
        }
      ],
      "total_search_result_count": 10
    },

    "step4_post_search_thinking": {
      "new_findings": "HBM3E 납품 재개 협상이 진행 중이며 1분기 중 성과 가능성. 4분기 부진은 범용 DRAM 가격 하락이 주요인으로 HBM과 별개 요인.",
      "view_change": "강화",
      "view_change_detail": "단기 부진이 HBM과 무관한 외부 요인임을 확인. 중장기 HBM 성장 스토리에 대한 확신이 높아짐. 단기 변동성을 매수 기회로 볼 수 있음.",
      "unresolved_questions": ["HBM3E 납품 재개 시점이 구체적으로 언제인지 아직 불명확"]
    }
  }
}
```

---

---

#### search_news 신규 인터페이스 설계 (Depth 2용)

**현재 인터페이스 (폐기 또는 분리):**
```python
search_news(fields=[{"field": "HBM", "keywords": [...]}], ...)
→ dict[field_name, list[제목only]]  # field별 그룹, 본문 없음
```

**신규 인터페이스 (Depth 2 LLM 연동용):**
```python
search_news_flat(
    keywords: list[str],      # LLM이 결정한 검색 키워드 (category 무관)
    current_date: str,
    lookback_days: int = 7,
    top_n: int = 10,          # 상위 10개 요약 반환
) -> list[dict]
```

**반환 구조:**
```json
[
  {
    "id": "news_20250103_섹터_0020",
    "title": "얇을수록 저항 줄어드는 신물질 개발…미래 반도체 공정 돌파구 될까",
    "date": "2025-01-03",
    "category": "섹터",
    "summary": "...200자 요약...",
    "relevance_score": 4.5
  },
  ...
]
```

**핵심 변경 사항:**
- `category` 필터 없음 — 종목/섹터/경제 구분 없이 전체 7일 풀에서 탐색
- field별 그룹핑 제거 → 관련도 점수(relevance_score) 기준 flat 랭킹
- **요약본(summary) 포함** 반환 — `read_news` 추가 호출 불필요
- 검색 키워드는 LLM(Step 2 Pre-Search Thinking)이 직접 결정

**`_depth2_search_fields()` 하드코딩 로직 제거:**
```python
# 삭제 대상 (news_agent.py:334-348)
@staticmethod
def _depth2_search_fields(read_contents, daily_titles):
    # DEFAULT_DEPTH2_FIELDS 기반 자동 생성 — LLM 관여 없음
    ...
```

---

#### Depth 2 LLM 연동 흐름 — 진짜 Agentic 구조로 전환

현재는 Python이 알아서 검색하는 방식. 신규 설계는 LLM이 검색 판단과 키워드를 직접 결정하는 단계를 명시적 LLM 호출로 분리한다.

**`llm/analysis.py`에 추가할 함수:**
```python
async def depth2_pre_search(agent, base_news_context, *, client) -> dict:
    """
    10개 요약 읽은 후 추가 탐색 여부와 키워드를 결정하는 LLM 호출.
    출력:
    {
      "search_needed": true/false,
      "key_findings": "읽고 파악한 핵심 내용",
      "curiosity_points": ["더 알고 싶은 것 1", "..."],
      "search_rationale": "왜 추가 탐색이 필요한지",
      "search_keywords": ["HBM", "엔비디아", "납품 일정"]  ← Python이 이걸로 search_news_flat 호출
    }
    """

async def depth2_post_search(agent, base_news_context, search_results, pre_thinking, *, client) -> dict:
    """
    추가 검색 결과를 읽고 나서 생각이 어떻게 변했는지 LLM 호출.
    출력:
    {
      "new_findings": "새로 알게 된 것",
      "view_change": "강화 | 수정 | 반전 | 유지",
      "view_change_detail": "구체적 설명",
      "unresolved_questions": ["아직 불명확한 것"]
    }
    """
```

**`prompts/news_agent.txt` 전면 개정 필요:**

현재 (5줄, 사실상 미구현):
```
당신은 삼성전자 개인투자자의 뉴스 탐색을 돕는 에이전트입니다.
Depth 1은 일일 뉴스 제목 10개 중 최대 3개만 읽을 수 있습니다.
...
```

필요한 내용 (추가):
1. Depth 0/1/2별 에이전트의 역할 구분 명시
2. Depth 2 Pre-Search Thinking 출력 JSON 스키마
3. `search_keywords` 생성 방법 안내 (LLM이 키워드를 어떻게 결정해야 하는지)
4. Post-Search Thinking 출력 JSON 스키마

**`prompts/news_interpretation.txt` 수정 필요:**

현재 `selected_news`를 "최대 3개" 반환하도록 지시 → Depth 0/1/2 분기 처리 필요:
- Depth 0: selected_news 없음 (헤드라인만)
- Depth 1: selected_news 자체가 의미 없음 (10개 전부 자동 제공)
- Depth 2: Pre-Search Thinking 단계에서 별도 처리

---

#### 구현 체크리스트

**news_agent.py:**
- [ ] `search_news_flat(keywords, current_date, lookback_days=7, top_n=10)` 신규 메서드 추가
  - category 무관 flat 랭킹, relevance_score 포함, summary 반환
- [ ] `_depth2_search_fields()` 하드코딩 로직 제거 또는 비활성화
- [ ] `expand_context_from_selection()` — Depth별 분기 재설계:
  - Depth 0: `read_contents = []` (아무것도 읽지 않음)
  - Depth 1: `read_contents = read_news(all_daily_ids)` (10개 전부 자동)
  - Depth 2: Depth 1 처리 후 별도 flow

**llm/analysis.py:**
- [ ] `depth2_pre_search(agent, base_news_context, *, client)` 추가
- [ ] `depth2_post_search(agent, base_news_context, search_results, pre_thinking, *, client)` 추가

**core/daily_cycle.py:**
- [ ] Depth 2 전용 Step 2→3→4 순차 호출 블록 추가:
  ```python
  if agent['news_depth'] >= 2:
      pre = await depth2_pre_search(agent, base_context, client=client)
      if pre['search_needed']:
          search_results = news_agent.search_news_flat(
              keywords=pre['search_keywords'], current_date=date
          )
          post = await depth2_post_search(agent, base_context, search_results, pre, client=client)
      # pre, post를 context에 추가 → update_belief로 전달
  ```

**prompts/:**
- [ ] `news_agent.txt` — Pre-Search / Post-Search 출력 스키마 포함하도록 전면 재작성
- [ ] `news_interpretation.txt` — Depth 0/1에서 selected_news 불필요하게 된 부분 정리

**logging:**
- [ ] `run_logger.py`: `depth2_flow` 필드 추가 (step2 pre, step3 search, step4 post)
- [ ] `agent_turns.jsonl`: Depth 2 에이전트에 한해 `depth2_flow` 블록 포함
- [ ] `agent_turns.csv`: `depth2_search_keywords`, `depth2_search_result_count`, `depth2_view_change` 컬럼 추가

**테스트:**
- [ ] `05_run_simulation.py`: Depth 2 에이전트 최소 1명 포함 강제
```python
depth2_agents = [a for a in agents if a['news_depth'] == 2]
if not depth2_agents:
    raise RuntimeError("테스트 실행에 Depth 2 에이전트가 최소 1명 필요 — sys_100.db 확인")
```

---

### D-03: 일일 뉴스 10개 선정 방식 — 카테고리별 일일 풀에서 랜덤 샘플링

**현행 방식 (문제):**
`news_agent.py`의 `prepare_news()`에서 카테고리별로 중요도(importance_score) **상위 N개**를 고정 선정:
```python
# 현재 코드 (news_agent.py:143-155)
for category, target in CATEGORY_TARGETS.items():
    picks = [row for row in rows if row["category"] == category][:target]
    # → 매일 같은 상위 뉴스가 반복 선정됨
```
결과적으로 중요도 기준 상위 5개 종목 뉴스가 매번 같은 뉴스로 고정될 가능성이 높음.

**신규 설계: 카테고리별 일일 풀에서 랜덤 샘플링**

카테고리 비율(5:3:2)은 유지하되, **매일 해당 날짜에 수집된 카테고리별 뉴스 풀에서 랜덤 샘플링**하여 선정한다. 확정된 10개는 그날 모든 에이전트(Depth 0/1/2)가 공통으로 받는 헤드라인 기반이 된다.

```
[오늘 수집된 카테고리별 뉴스]
  종목 풀: N개 (당일 수집 전체, importance 무관)
  섹터 풀: M개
  경제 풀: K개
          ↓
[카테고리별 랜덤 샘플링]
  종목: random.sample(종목 풀, min(5, N))  → 5개
  섹터: random.sample(섹터 풀, min(3, M))  → 3개
  경제: random.sample(경제 풀, min(2, K))  → 2개
          ↓
[오늘 확정된 10개 헤드라인]  (날짜별로 매번 다른 조합)
  ← Depth 0/1/2 에이전트 전원 공통 수신
```

**근거:**
- 카테고리 비율(5:3:2)은 설계 의도대로 유지
- 같은 날에도 어떤 뉴스가 뽑히는지 실행마다 달라짐 → 현실적 정보 랜덤성 반영
- 카테고리 풀이 부족한 날(경제 뉴스 1개뿐인 경우)은 `min()` 처리로 자연 대응

**수정 위치:** `news_agent.py` `prepare_news()` 내 선별 로직 + `02_prepare_news.py`
```python
import random as _random

def _select_daily(rows: list[dict], seed=None) -> list[dict]:
    rng = _random.Random(seed)  # seed=None이면 실행마다 다름
    targets = {"종목": 5, "섹터": 3, "경제": 2}
    selected, used_ids = [], set()
    for category, n in targets.items():
        pool = [r for r in rows if r["category"] == category and r["id"] not in used_ids]
        k = min(n, len(pool))
        picks = rng.sample(pool, k)
        selected.extend(picks)
        used_ids.update(r["id"] for r in picks)
    # 10개 미달 시 나머지로 보충
    if len(selected) < 10:
        remains = [r for r in rows if r["id"] not in used_ids]
        selected.extend(rng.sample(remains, min(10 - len(selected), len(remains))))
    return selected
```

**주의:** `daily_news_selection.csv`는 시뮬레이션 전에 1회 생성되어 고정으로 사용됨. 랜덤 결과의 재현성이 필요하면 `seed`를 고정하거나, 재실행 시 동일 CSV를 재사용하도록 처리 필요.

---

### R-03: 보고서 수익률 계산이 1억 원으로 하드코딩

**증상:**
`generate_run_report_pdf.py` 또는 보고서 스크립트에서 최종 수익률을 `(총자산 - 100_000_000) / 100_000_000`으로 계산함. 이번 5명은 모두 초기 현금 1억이라 문제없지만, `INI_CASH_LARGE = 1_000_000_000` 설정이나 에이전트별 `ini_cash`가 다른 경우 수익률이 틀어짐.

**수정 방향:**
```python
# sys_100.db 또는 portfolio_state turn=0에서 에이전트별 초기 자산 조회
initial_value = get_portfolio_state(agent_id, turn=0)['total_value']
return_rate = (final_value - initial_value) / initial_value
```

---

## 🟢 개선 권고

### D-04: 설계서 LLM 호출 횟수 기술 오류

`Overall_Framework_Design.md` §4: "하루 기본 2회 LLM 호출"  
실제 구현: **4회** (`interpret_news` + `update_belief` + `analyze_market` + `make_decision`)

`Code_Status.md` D-17에서 `analyze_market` 추가를 기록하였으나 설계서 본문은 미반영 상태.

**수정:** `Overall_Framework_Design.md` §4 업데이트 (D-17 결정 사항 통합)

---

### D-05: news_depth 칼럼 Persona 설계서 미반영

`Persona_Distribution_Design.md`에 `news_depth` 칼럼 정의 없음.  
`Code_Status.md` D-07/D-13에만 기록됨.

**수정:** `Persona_Distribution_Design.md` agents 테이블 스키마 섹션에 `news_depth INTEGER` 칼럼 및 설명 추가.

---

### V-02: Depth 2 에이전트 실제 동작 미검증

**상태:** Depth 2 관련 코드 (`news_agent.search_news`, `expand_context_from_selection` Depth 분기) 구현은 존재하나, D-02 재설계 후 실제 동작 검증이 필요.

**검증 항목:**
1. 테스트 실행에 Depth 2 에이전트 최소 1명 포함
2. `depth2_search_trigger` 로그 생성 확인
3. `search_read_count > 0` 및 `depth2_search_result_count == 10` 확인
4. Depth 2 에이전트의 Belief가 Depth 1 에이전트보다 더 풍부한 뉴스 컨텍스트를 반영하는지 비교

---

### V-03: INSTITUTIONAL 방향 vs 실제 기관 데이터 비교 (추후 수행)

실제 삼성전자 기관/외국인 매매 데이터를 확보한 후, 6개월 전체 시뮬레이션 완료 시점에 INSTITUTIONAL 방향 일치율을 검증. 현재는 데이터 미확보 상태로 보류.

---

## 종합 우선순위 로드맵

### 즉시 (다음 실행 전 — 코드 수정 필수)
1. **R-01** sim.db 재실행 격리 — run_id 기반 새 DB 또는 테이블 초기화
2. **R-02** trade_log 체결 결과 업데이트 — pending → filled/unfilled 상태 관리
3. **B-01** `memory_agent.py` 미실현 손익 `current_price` 매일 갱신
4. **D-02** Depth 0/1/2 구조 재설계 및 구현 (Depth 2 로그 포함)
5. **B-03** `build_trading_constraints()`에 단일 거래 최대 비율 추가 검토

### 단기 (1~2주 내)
6. **B-02** 미체결 피드백 — `collect_context`에 이전 주문 체결 여부 포함
7. **B-02** 동시호가 인식 여부 프롬프트 검토
8. **D-03** 일일 뉴스 선정 랜덤화 (`02_prepare_news.py` 수정)
9. **R-03** 보고서 수익률 ini_cash 하드코딩 제거
10. **V-02** Depth 2 포함 테스트 재실행 및 로그 검증

### 문서화
11. **D-04** `Overall_Framework_Design.md` LLM 호출 횟수 4회로 수정
12. **D-05** `Persona_Distribution_Design.md` news_depth 칼럼 추가

### 추후 (데이터 확보 후)
13. **V-03** INSTITUTIONAL 방향 vs 실제 기관 데이터 Pearson 상관 계산
