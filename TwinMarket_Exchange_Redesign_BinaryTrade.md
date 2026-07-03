# TwinMarket 거래소 메커니즘 전면 개편안
## 공시가 기반 이진 매매 (Announced-Price Binary Trading) 방식 도입

> 참조 문서: `TwinMarket_Improvement_Proposal.md`, `TwinMarket_Code_Plan.md`
> 이 문서는 위 두 문서의 **항목 3(호가 존중 체결)**과 **항목 4(4시간봉 도입 + 하루 2번 거래)**를 완전히 대체하는 새로운 거래 메커니즘의 설계 문서다.
> 이 문서 하나만으로 체결 엔진을 처음부터 다시 구현할 수 있어야 한다.

---

## 0. 이 문서의 위치와 기존 문서와의 관계

### 0.1 무엇을 대체하는가

| 기존 항목 | 상태 | 사유 |
|---|---|---|
| Proposal 항목 3 (에이전트 호가 존중 체결) | **폐기, 본 문서로 대체** | 에이전트가 더 이상 호가(price)를 제출하지 않으므로 "호가를 존중한다"는 개념 자체가 사라짐 |
| Proposal 항목 4 (4시간봉 + 하루 2번 거래) | **부분 대체** | 하루 2턴(AM/PM) 구조는 유지하지만, 13:00 중간가(mid) 앵커 개념과 "제출가 vs 목표가 매칭" 체결 로직은 전면 폐기 |
| Code Plan 항목 3 (체결가 = 에이전트 제출 호가) | **폐기** | 위와 동일 사유. 이제 체결가는 항상 시장에서 공시된 실제 가격(시가/종가) 하나뿐이며, 에이전트별로 다른 체결가가 존재하지 않음 |
| Code Plan 항목 4 (4시간봉 로직) | **재작성** | AM/PM 구조·뉴스 시간 분기는 유지, 가격 앵커링·`calculate_anchored_price()`·COUNTERSIDE 매칭은 전면 재작성 |
| Proposal/Plan 항목 1 (콜옥션 규칙 명시 + 주문 이력) | **의미 소멸, 축소된 형태로만 유지 권장** | "내 호가가 왜 체결 안 됐는가"라는 질문 자체가 사라짐. 대신 "왜 내 주문이 거부됐는가(현금/보유 부족)"라는 훨씬 단순한 질문만 남음. §10 참고 |
| Proposal/Plan 항목 2 (CoT 흐름: 방향→가격보정) | **가격보정 단계 삭제** | 가격을 정하지 않으므로 Step 3(호가 보정)이 사라지고 Step 1(방향)+Step 2(수량)만 남음 |
| Proposal/Plan 항목 5 (방향 검증 지표) | **유지, 용어만 조정** | balanced accuracy, recall 등 지표 로직은 그대로 유효함. §10.5 참고 |
| Proposal/Plan 항목 7 (deep analysis report) | **차트 2번만 수정, 나머지 유지** | "호가 편차" 차트는 더 이상 존재하지 않는 데이터이므로 대체 필요. §10.6 참고 |
| COUNTERSIDE 개념 전체 | **완전 삭제 대상** | §6.3 참고 |
| N_WARMUP / execute_warmup_orders() / Day1 특수분기 | **완전 삭제 대상** | §3.4 참고 |

### 0.2 문서 구성

이 문서는 Proposal(왜 바꾸는가)과 Code Plan(어떻게 바꾸는가)의 형식을 하나로 합쳐서 작성했다. 각 섹션은 "배경 → 설계 → 구현 지침 → 검증 체크리스트" 순서를 따른다.

---

## 1. 배경: 기존 방식이 가진 근본적인 문제

### 1.1 기존 체결 흐름 요약 (변경 전)

1. **초기 상태**: 모든 에이전트는 `portfolio_state t000`에서 `cash = ini_cash`, `positions = []`로 시작한다. (`twinmarket_kr/agents/memory_agent.py:62`)
2. **Day 1**: `execute_warmup_orders()`가 매수 주문만 대상으로 잡는다(매도 제외). 각 매수 주문은 지정가가 전일 기준 상하한 범위 안에 있으면 상대 매도자 없이도 그대로 체결되고, 체결가는 에이전트의 지정가다. 하지만 그날의 `closing_price`는 주문과 무관하게 `real_price`를 그대로 반환한다. (`twinmarket_kr/agents/exchange_agent.py:55`)
3. **Day 2~3**: 여전히 워밍업 구간(`N_WARMUP = 3`)이다. 매수/매도 주문을 모두 받지만 서로 매칭하지 않고, 조건만 맞으면 각 주문이 자기 지정가로 개별 체결된다. 가격 형성은 실제 데이터 앵커이지만 체결가는 에이전트별 지정가로 제각각이다.
4. **AM/PM 2턴 구조**: `simulation.py`에서 AM은 13:00 가격, PM은 종가를 `target_price`로 넘긴다. 워밍업 중이면 이 값이 그대로 `closing_price`가 된다. (`twinmarket_kr/simulation.py:373`)
5. **Day 4 이후**: `calculate_anchored_price()`로 실제 가격을 `target_price`로 삼고, 매수/매도 수급 불균형은 `COUNTERSIDE`라는 가상의 거래주체가 메운다. 최종 `closing_price`는 기본적으로 실제 가격 앵커다.

### 1.2 문제점

- **단계별로 체결 로직이 다르다.** Day 1, Day 2~3(워밍업), Day 4+(정상)가 서로 다른 코드 경로를 타기 때문에 코드 복잡도가 높고, 초반 3거래일의 포트폴리오 형성 과정이 이후와 이질적이다.
- **에이전트가 가격을 "맞혀야" 한다는 부담이 실제 개인 투자자의 행동과 괴리된다.** 삼성전자처럼 초대형주·초고유동성 종목을 거래하는 개인 투자자는 사실상 가격을 결정하는 주체(price maker)가 아니라, 시장가에 그대로 응하는 가격 수용자(price taker)에 가깝다. LLM 에이전트가 "종가를 예측해서 그보다 몇 원 더 높게/낮게 부른다"는 행동을 학습하도록 설계하는 것은 실제 리테일 투자자 행동을 재현하는 것이 아니라, 존재하지 않는 "호가 전략 게임"을 학습시키는 것에 가깝다.
- **COUNTERSIDE라는 인위적 장치가 필요하다.** 에이전트들의 매수/매도 수량이 정확히 일치할 수 없기 때문에 가상의 거래상대방이 차액을 메워야 하고, 이 존재는 통계에서 매번 제외 처리해야 하는 예외 처리 부담을 만든다.
- **미체결의 원인이 이중적이다.** 현재는 "가격을 잘못 불러서" 미체결되는 경우와 "자금/보유 수량이 부족해서" 미체결되는 경우가 섞여 있어, 에이전트 행동을 분석할 때 어떤 실패가 어떤 원인인지 분리하기 어렵다.

### 1.3 새로운 설계 철학

> **에이전트는 가격을 정하지 않는다. 거래소가 그날의 실제 공시 가격(시가 또는 종가)을 알려주고, 에이전트는 "이 가격에 살 것인가, 팔 것인가"와 "얼마나"만 결정한다. 관망(아무것도 안 함)은 선택지에 없으며, 매 턴 반드시 매수 또는 매도 중 하나를 최소 1주 이상 실행해야 한다.**

이렇게 하면:
- 체결 여부는 오직 **자금(현금)** 과 **보유 수량**이라는 명확하고 단일한 제약 조건으로만 결정된다.
- 체결가는 항상 실제 삼성전자 시가/종가와 동일하므로, 포트폴리오 손익이 실제 시장 가격 흐름을 그대로 반영한다.
- COUNTERSIDE, 호가 매칭, 워밍업 특수분기가 모두 불필요해져 시스템이 훨씬 단순해진다.
- 분석의 초점이 "에이전트가 가격을 잘 맞히는가"에서 "에이전트가 실제 개인 투자자처럼 매수/매도 타이밍과 방향을 잘 재현하는가"로 명확해진다. 이는 원래 TwinMarket이 검증하고자 하는 목표(개인 투자자 행동 재현)에 더 부합한다.

---

## 2. 새로운 하루 흐름 (전체 그림)

하루는 기존과 동일하게 **AM Turn**과 **PM Turn** 2개의 서브턴으로 구성된다. 다만 각 턴에서 에이전트가 받는 질문의 형태와 체결 로직이 완전히 달라진다.

```
[전일 장마감]
     │
     ▼
┌─────────────────────────────────────────────┐
│ AM Turn                                      │
│ 제공 정보: 전일 종가, "오늘 시가 = X원"(공시),   │
│            전일 마감~오늘 09:00 이전 뉴스/커뮤니티 │
│ 질문: "오늘 시가 X원에 매수할지 매도할지 선택,    │
│        수량은?"                               │
│ 체결: 결정 즉시 시가(X원)로 체결                 │
└─────────────────────────────────────────────┘
     │ (포트폴리오 즉시 갱신)
     ▼
┌─────────────────────────────────────────────┐
│ PM Turn                                      │
│ 실행 시점: 15:30 장마감 및 종가 확정 이후          │
│ 제공 정보: 오늘 시가(참고용), AM 체결 후 포트폴리오,│
│            기존 코드 흐름에 따른 뉴스 시간 분기,     │
│            의사결정 시점 이전 community_log,       │
│            "오늘 종가 = Y원"(확정 공시)            │
│ 질문: "오늘 종가 Y원에 매수할지 매도할지 선택,    │
│        수량은?"                               │
│ 체결: 결정 즉시 종가(Y원)로 체결                 │
└─────────────────────────────────────────────┘
     │ (포트폴리오 즉시 갱신)
     ▼
[다음 거래일로 이동]
```

핵심 변화: 기존 항목 4의 3개 가격 포인트(09:00 시가 / 13:00 중간가 / 15:30 종가)에서 **13:00 중간가를 완전히 제거**하고, 시가와 종가 2개 포인트만 사용한다. AM Turn은 "시가에 살지 말지"를 묻고 **그 자리에서 시가로 체결**하며, PM Turn은 **15:30 장마감 및 종가 확정 이후** 실행되어 "확정 공시된 종가에 살지 팔지"를 묻고 **그 자리에서 종가로 체결**한다. 에이전트는 종가를 예측하지 않으며, 이미 공시된 확정 종가를 수용 가격으로 받아 buy/sell 및 수량만 결정한다.

뉴스 시간 분기는 기존 코드 흐름을 그대로 유지한다. 커뮤니티 정보도 기존 코드와 동일하게 해당 의사결정 시점 이전에 생성된 `community_log`만 사용한다. PM 체결 이후 생성되는 게시글/반응은 당일 PM 의사결정에는 사용하지 않고, 이후 턴의 context에 반영한다.

---

## 3. 의사결정 스키마 (에이전트 → 거래소)

### 3.1 기존 스키마 (폐기)

```json
{
  "action": "buy",
  "price": 221000,
  "quantity": 10,
  "reasoning": "..."
}
```

### 3.2 새 스키마 — `hold`(관망) 옵션 없음

> **중요한 설계 변경**: `hold`(관망)는 선택지에서 완전히 제외한다. 에이전트는 매 턴 반드시 `buy` 또는 `sell` 중 하나를 선택해야 하며, 최소 1주 이상 거래해야 한다. "아무것도 하지 않는다"는 선택 자체가 존재하지 않는다.

```json
{
  "action": "buy",       // "buy" | "sell"   ("hold" 없음)
  "quantity": 10,        // 최소값 1. 0 또는 음수는 허용하지 않음
  "reasoning": "..."
}
```

`price` 필드는 완전히 제거한다. 에이전트는 애초에 가격을 입력할 수 없다(프롬프트에도 가격 입력란을 주지 않는다).

### 3.3 강제 매매 원칙과 방향 제약

매 턴, 에이전트는 반드시 거래 방향(buy/sell)과 수량(≥1)을 결정해야 한다. 다만 방향 선택은 무제한이 아니라 다음 제약을 받는다:

| 상황 | 허용되는 action |
|---|---|
| 보유 수량 = 0 (매도 불가) | `buy`만 가능 |
| 매수 가능 최대 수량 = 0, 즉 현금 < 공시가 1주 값 (매수 불가) | `sell`만 가능 |
| 둘 다 가능 (보유 수량 > 0 이고 현금 ≥ 공시가) | `buy`, `sell` 둘 다 가능 — 에이전트가 자유롭게 선택 |
| 둘 다 불가능 (보유 수량 = 0 이고 현금 < 공시가) | **비정상 상황(§3.5 참고)** |

이 제약은 `collect_context()`가 매 턴 `allowed_actions` 리스트로 계산하여 프롬프트에 명시적으로 전달한다(§6.3, §6.5). 에이전트가 허용되지 않은 방향을 출력하거나 수량 제약을 위반하면 decision 검증 단계에서 재시도한다. 재시도 후에도 유효하지 않으면 임의로 `allowed_actions[0]` 같은 방식으로 강제 치환하지 않고, 오류 로그를 남긴 뒤 해당 턴을 실패 처리한다. 거래소는 검증을 통과한 유효한 `action`과 `quantity`만 받는다.

### 3.4 수량 결정 시 참고 정보

에이전트가 수량을 합리적으로 정할 수 있도록 `collect_context()`가 다음 정보를 미리 계산해서 제공한다(이건 에이전트에게 "힌트"를 주는 것이지 체결 로직에 영향을 주지 않는다):

- `max_affordable_quantity`: 현재 현금으로 이 가격에 최대 몇 주까지 매수 가능한지
- `holding_quantity`: 현재 보유 수량 (매도 가능한 최대 수량)
- `cash_after_max_buy`, `min_cash_reserve` 등 기존 `trading_constraints`에 있던 제약은 그대로 유지
- 거래 수수료는 제거한다. 매수 가능 수량과 현금 차감/증가는 `announced_price * quantity`만 기준으로 계산한다.

### 3.5 비정상 상황: 매수도 매도도 불가능한 경우

이론상 `보유 수량 = 0`이면서 동시에 `현금 < 공시가 1주 값`인 상황이 발생하면, `buy`도 `sell`도 낼 수 없어 "무조건 1주 이상 거래"라는 원칙이 깨진다. 이 상황은 다음과 같이 방지/처리한다:

- **예방**: `ini_cash`(초기 자금)를 시뮬레이션 전 기간 중 삼성전자 최고가 1주 값보다 충분히 크게 설정하여, 최소 1주는 항상 매수 가능하도록 보장한다. 이 조건은 시뮬레이션 시작 전 자동 검증(assert)한다.
- **방어 코드**: 그럼에도 위 상황이 발생하면(예: 초기 자금 설정 실수), 해당 턴은 예외적으로 거래를 생략하고 경고 로그를 남긴다. 이는 정상적인 `hold`가 아니라 **시스템 설정 오류에 대한 방어적 예외 처리**이며, 정상 시뮬레이션에서는 발생해서는 안 된다.

### 3.6 Day 1 / 워밍업 특수분기 완전 제거

새 메커니즘에서는 주문 간 매칭이 없고 각 주문이 순수하게 "현금/보유 수량 충분한가"만으로 판정되므로, Day 1이라고 해서 특별히 다르게 처리할 이유가 없다:

- Day 1 AM Turn에서 `positions = []`이므로 `allowed_actions = ["buy"]`만 계산되어 에이전트는 애초에 매수만 선택할 수 있다(§3.3). 별도의 "Day 1은 매수만 허용" 같은 하드코딩된 분기가 필요 없다 — `allowed_actions` 계산 로직 하나로 모든 날짜에 동일하게 적용된다.
- Day 1 매수 결정은 다른 날과 동일하게 "오늘 시가"로, 최소 1주 이상 즉시 체결된다. 전일 기준 상하한선 검사, 상대 매도자 존재 여부 확인 같은 워밍업 전용 로직이 필요 없다.

**삭제 대상**:
- `N_WARMUP` 상수
- `execute_warmup_orders()` 함수 전체
- `day_number == 1` 관련 특수 분기
- "전일 기준 상하한 범위" 검사 로직 (더 이상 지정가 자체가 없으므로 상하한 검사 대상이 없음)

---

## 4. 체결 로직 상세 (핵심)

### 4.1 체결 조건

| action | 조건 | 결과 |
|---|---|---|
| `buy` | `announced_price * quantity <= available_cash` | 전량 체결, `executed_price = announced_price` |
| `buy` | `announced_price * quantity > available_cash` | decision 검증 실패. 재시도 후에도 실패하면 해당 턴 실패 처리 |
| `sell` | `quantity <= holding_quantity` | 전량 체결, `executed_price = announced_price` |
| `sell` | `quantity > holding_quantity` | decision 검증 실패. 재시도 후에도 실패하면 해당 턴 실패 처리 |

`hold`는 선택지에 없으므로 체결 조건 표에도 등장하지 않는다(§3.2). 기존과 달리 "가격 조건"(bid ≥ target, ask ≤ target)도 존재하지 않는다. 거래소는 프롬프트와 decision 검증 단계를 통과한 최종 유효 주문만 받아 공시가에 전량 체결한다.

### 4.2 요청 수량 검증 — 부분 체결 없음

이 시스템에서는 `partial` 또는 clipping을 거래소 단계에서 구현하지 않는다. 에이전트가 가능한 범위를 넘는 수량을 출력하지 않도록 프롬프트에서 `max_affordable_quantity`와 `holding_quantity`를 명확히 제공하고, decision 검증 단계에서 최종 수량이 가능한 범위 안에 있는지 확인한다.

```python
if action == "buy":
    max_qty_by_cash = int(available_cash // announced_price)
    assert 1 <= quantity <= max_qty_by_cash
elif action == "sell":
    assert 1 <= quantity <= holding_quantity
```

검증을 통과한 주문은 거래소에서 항상 전량 체결한다. 검증 실패 시에는 decision 생성/파싱 단계에서 재시도하고, 재시도 후에도 실패하면 임의 보정 없이 오류 로그를 남긴다. 따라서 정상 체결 로그에는 `partial` 상태가 존재하지 않는다.

### 4.3 COUNTERSIDE 완전 삭제

새 메커니즘에는 매수/매도 수량을 서로 매칭시키는 절차 자체가 없다. 각 에이전트의 주문은 서로 독립적으로, 오직 자신의 현금/보유 수량 제약만으로 판정된다. 따라서:

- 수급 불균형이라는 개념 자체가 존재하지 않는다 (거래소가 실제 시장의 무한 유동성을 상수처럼 제공한다고 가정 — 이는 삼성전자 같은 초고유동성 종목에서는 합리적인 가정이다).
- `COUNTERSIDE` 관련 코드(주문 생성, 통계 제외 필터, 로그 마스킹 등)를 **모두 삭제**한다.
- 관련 삭제 대상: `exchange_agent.py` 내 COUNTERSIDE 주문 생성 로직, `validate_trading_direction.py` 및 `generate_deep_analysis_report.py` 내 `user_id == "COUNTERSIDE"` 필터링 코드.

### 4.4 fill 레코드 구조

```python
fill = {
    "agent_id": order["agent_id"],
    "date": date,
    "subturn": subturn,              # "am" | "pm"
    "action": order["action"],       # "buy" | "sell"  ("hold" 없음)
    "quantity": order["quantity"],   # 검증 완료된 최종 유효 수량
    "executed_price": announced_price,
    "status": "filled",
}
```

`executed_price`는 이제 그 턴의 모든 체결 건에서 동일한 값(그날의 시가 또는 종가)이다. 에이전트마다 다른 체결가가 존재하지 않는다 — 이것이 기존 방식과의 가장 큰 차이다.

거래 수수료는 제거한다. fill 레코드에는 `fee`를 기록하지 않으며, 포트폴리오 업데이트에서도 수수료 차감/가산을 하지 않는다.

---

## 5. 데이터 요구사항

### 5.1 신규 데이터 파일: `data/stock_data_daily.csv`

기존 `stock_data_4h.csv`(open/mid/close 3포인트)에서 **mid를 제거**하고 open/close 2포인트만 사용한다.

```csv
date,open_price,close_price
2026-04-24,219000,219500
2026-04-25,219500,221000
...
```

이미 `stock_data_4h.csv`가 수집되어 있다면 굳이 새 파일을 만들지 않고 `open`, `close` 두 `time_slot`만 읽고 `mid`는 무시하는 방식으로 로더를 구현해도 된다. 둘 중 하나를 선택하되, 문서/코드에는 어떤 파일을 쓰는지 명확히 주석으로 남긴다.

### 5.2 로더 함수 (`twinmarket_kr/agents/fundamental_agent.py`)

```python
def load_daily_price_csv(csv_path: str) -> dict:
    """date -> {"open": price, "close": price} 딕셔너리 반환"""
    result = {}
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result[row["date"]] = {
                "open": float(row["open_price"]),
                "close": float(row["close_price"]),
            }
    return result
```

기존 `load_stock_data_csv()` / 4h 로더(`load_4h_data_csv()`)는 더 이상 mid를 참조하는 곳이 없으므로, 위 함수로 완전히 대체하거나 mid 필드를 무시하도록 축소한다.

---

## 6. 파일별 구현 지침

### 6.1 `twinmarket_kr/agents/exchange_agent.py`

**삭제**:
- `calculate_anchored_price()` (더 이상 "목표가"라는 개념이 없음 — 공시가 자체가 곧 체결가)
- 매수/매도 매칭 루프, COUNTERSIDE 주문 생성부
- `override_price` 관련 파라미터 전달 체계 (있다면 `announced_price`라는 명확한 이름으로 대체)

**신규 함수**:

```python
def get_allowed_actions(portfolio: dict, announced_price: float) -> list[str]:
    """§3.3: 이번 턴에 이 에이전트가 낼 수 있는 방향 목록"""
    can_buy = portfolio["cash"] >= announced_price          # 최소 1주 살 돈이 있는가
    can_sell = portfolio["position"] >= 1                    # 최소 1주 보유하고 있는가
    allowed = []
    if can_buy:
        allowed.append("buy")
    if can_sell:
        allowed.append("sell")
    return allowed   # 정상 시나리오에서는 항상 길이 >= 1 (§3.5)


def execute_binary_orders(
    self,
    orders: list[dict],
    announced_price: float,
    portfolios: dict,           # agent_id -> {"cash": float, "position": int, ...}
) -> list[dict]:
    """
    orders: [{"agent_id": str, "action": "buy"|"sell", "quantity": int}, ...]
             quantity는 항상 1 이상이어야 한다 ("hold"는 존재하지 않음)
    announced_price: 그 턴에 공시된 실제 가격 (AM=시가, PM=종가)
    반환: fill 레코드 리스트
    """
    fills = []
    for order in orders:
        agent_id = order["agent_id"]
        action = order["action"]
        quantity = int(order["quantity"])
        portfolio = portfolios[agent_id]

        allowed = get_allowed_actions(portfolio, announced_price)

        if not allowed:
            # §3.5의 예외 상황: 초기 자금 설정 오류 등으로 매수/매도 모두 불가능
            self._log_no_feasible_action(agent_id, action, quantity)
            continue

        if action not in allowed:
            # 강제 치환 금지. decision 검증 단계에서 걸러져야 하는 오류다.
            raise ValueError(f"invalid action for portfolio state: {agent_id} {action} not in {allowed}")

        if action == "buy":
            max_affordable = int(portfolio["cash"] // announced_price)   # allowed 이므로 >= 1
            if quantity < 1 or quantity > max_affordable:
                raise ValueError(f"invalid buy quantity: {agent_id} quantity={quantity} max={max_affordable}")
        else:  # "sell"
            holding = portfolio["position"]                              # allowed 이므로 >= 1
            if quantity < 1 or quantity > holding:
                raise ValueError(f"invalid sell quantity: {agent_id} quantity={quantity} holding={holding}")

        exec_price = announced_price
        fills.append(self._make_fill(agent_id, action, quantity, exec_price, "filled"))

    return fills
```

### 6.2 `twinmarket_kr/core/daily_cycle.py`

```python
def run_daily_turn(date, agents, exchange, memory_agents, stock_daily, news_data, ...):
    open_price  = stock_daily[date]["open"]
    close_price = stock_daily[date]["close"]

    # ── AM Turn: 시가 공시 → 시가로 즉시 체결 ─────────────
    am_orders = []
    for agent in agents:
        ctx = collect_context(
            agent, turn, date, memory_agents[agent.id], news_data,
            subturn="am", announced_price=open_price,
        )
        decision = run_agent_decision(agent, ctx)   # {"action", "quantity", "reasoning"}
        am_orders.append({"agent_id": agent.id, **decision})

    am_fills = exchange.execute_binary_orders(
        am_orders, announced_price=open_price, portfolios=get_portfolios(memory_agents)
    )
    update_portfolios(am_fills, memory_agents)

    # ── PM Turn: 종가 공시 → 종가로 즉시 체결 ─────────────
    pm_orders = []
    for agent in agents:
        ctx = collect_context(
            agent, turn, date, memory_agents[agent.id], news_data,
            subturn="pm", announced_price=close_price,
        )
        decision = run_agent_decision(agent, ctx)
        pm_orders.append({"agent_id": agent.id, **decision})

    pm_fills = exchange.execute_binary_orders(
        pm_orders, announced_price=close_price, portfolios=get_portfolios(memory_agents)
    )
    update_portfolios(pm_fills, memory_agents)
```

`N_WARMUP`, `execute_warmup_orders()` 호출부는 완전히 삭제한다. Day 1도 위 루프를 그대로 탄다.

### 6.3 `twinmarket_kr/core/collect_context.py`

```python
def collect_context(agent, turn, date, memory_agent, news_data,
                     subturn: str,          # "am" | "pm"
                     announced_price: float):

    portfolio = memory_agent.get_portfolio_summary(agent.id, turn - 1)

    if subturn == "am":
        news_context = filter_news_by_time(news_data, date, end_time="09:00")
        price_label = "오늘 시가"
    else:  # "pm"
        news_context = filter_news_by_time(news_data, date, start_time="09:00", end_time="15:30")
        price_label = "오늘 종가"

    max_affordable_qty = int(portfolio["cash"] // announced_price)
    holding_qty = portfolio.get("position", 0)

    allowed_actions = get_allowed_actions(portfolio, announced_price)  # §6.1 참고, ["buy"] / ["sell"] / ["buy","sell"]
    assert allowed_actions, "매수도 매도도 불가능한 비정상 상황 — §3.5 참고, ini_cash 설정을 점검할 것"

    return {
        "price_label": price_label,
        "announced_price": announced_price,
        "max_affordable_quantity": max_affordable_qty,
        "holding_quantity": holding_qty,
        "allowed_actions": allowed_actions,     # 프롬프트에 그대로 노출 — 에이전트가 선택 가능한 방향
        "portfolio_summary": portfolio,
        "news_context": news_context,
        # community_records 등 기존 키는 동일하게 유지.
        # 단, 기존 코드와 동일하게 의사결정 시점 이전에 생성된 community_log만 사용한다.
        # PM 체결 이후 생성되는 게시글/반응은 당일 PM 의사결정에는 사용하지 않는다.
    }
```

뉴스 시간 분기(`filter_news_by_time`)는 기존 코드 흐름을 그대로 유지한다. Depth 2 에이전트의 추가 검색(search) 기능은 시간대 제약 없이 이전 날짜까지 검색 가능하다는 규칙도 그대로 유지한다. 커뮤니티 정보는 기존 코드와 동일하게 해당 의사결정 시점 이전에 생성된 `community_log`만 사용한다. PM 체결 이후 생성되는 게시글/반응은 당일 PM 의사결정에는 사용하지 않고, 이후 턴의 context에 반영한다.

### 6.4 `twinmarket_kr/agents/memory_agent.py`

- `N_WARMUP` 상수 삭제
- `execute_warmup_orders()` 삭제
- 포트폴리오 업데이트 함수는 그대로 사용 가능하나, `avg_cost` / `realized_pnl` 계산 시 `executed_price`가 이제 해당 턴의 공시가(시가/종가)와 항상 동일하다는 점만 반영되면 된다(계산식 자체는 변경 없음).
- 거래 수수료는 제거한다. 매수 시 현금 차감은 `executed_price * quantity`, 매도 시 현금 증가는 `executed_price * quantity`만 사용한다.
- (선택) 항목 1을 축소된 형태로 유지한다면 `get_recent_order_history()`를 다음처럼 단순화한다:

```python
def get_recent_order_decision_history(self, agent_id: str, last_n: int = 5) -> list[dict]:
    """가격 편차 없이 최근 buy/sell 결정과 체결 결과만 반환"""
    ...
    result.append({
        "date": date,
        "action": action,
        "quantity": quantity,
        "status": status,   # 정상 체결은 filled. 검증 실패는 별도 오류 로그에 기록.
    })
    return result
```

### 6.5 `prompts/make_decision.txt`

**삭제**: 호가 관련 안내 문구, `{order_history}`의 가격 편차 서술 전체.

**신규 삽입** (가격 공시 안내):

```
[오늘 {price_label} 공시]
{price_label}는 {announced_price}원으로 확정되었습니다.
이 가격은 협상 대상이 아닙니다. 당신은 반드시 이 가격에 "매수"하거나 "매도"해야 하며,
아무것도 하지 않는 선택지(관망)는 없습니다. 최소 1주 이상 거래해야 합니다.

당신이 이번 턴에 선택할 수 있는 방향은 다음 중 하나로 제한됩니다: {allowed_actions}
- "buy"만 가능한 경우: 현재 보유 수량이 0이라 매도할 수 없습니다. 반드시 매수하십시오.
- "sell"만 가능한 경우: 현재 현금이 {price_label} 1주 값보다 적어 매수할 수 없습니다. 반드시 매도하십시오.
- 둘 다 가능한 경우: 매수/매도 중 자유롭게 선택하십시오.

- 매수(buy) 선택 시: 현재 현금으로 최대 {max_affordable_quantity}주까지 매수할 수 있습니다.
- 매도(sell) 선택 시: 현재 보유 수량 {holding_quantity}주 이내에서 매도할 수 있습니다.
```

**출력 스키마 지시문 수정**:

```
다음 JSON 형식으로만 답하십시오. price 필드는 존재하지 않으며, "hold"는 유효한 값이 아닙니다.
action은 반드시 {allowed_actions} 중 하나여야 합니다.
quantity는 1 이상의 정수이며, buy는 {max_affordable_quantity}주 이하, sell은 {holding_quantity}주 이하만 허용됩니다.
{
  "action": "buy" | "sell",
  "quantity": <int, 최소 1>,
  "reasoning": "<string>"
}
```

**CoT 지시문 (기존 항목 2 대체)**:

```
Step 1. 오늘의 신념(belief_summary)과 시장 분석(market_analysis), 그리고 공시된 {price_label}({announced_price}원)를
        검토하여 매수 / 매도 중 하나의 방향을 결정한다. (관망은 선택할 수 없다)
        단, 선택 가능한 방향은 {allowed_actions}로 제한되어 있으므로 이 범위 내에서 결정한다.

Step 2. 포트폴리오 상태(portfolio_summary)와 거래 제약(trading_constraints),
        그리고 매수 가능 최대 수량({max_affordable_quantity}) / 매도 가능 최대 수량({holding_quantity})을 참고하여
        1주 이상의 구체적인 수량을 결정한다.

Step 3. 위 내용을 종합하여 action, quantity, reasoning을 JSON으로 출력한다.
```

호가 보정 단계(기존 Step 3)는 완전히 삭제된다.

---

## 7. 포트폴리오 업데이트 로직

체결가가 항상 공시가와 동일하다는 점을 제외하면 계산식은 기존과 동일하다.

**매수 체결 시**:
```python
cost = quantity * executed_price
portfolio["cash"] -= cost
new_total_qty = portfolio["position"] + quantity
portfolio["avg_cost"] = (
    (portfolio["avg_cost"] * portfolio["position"] + cost) / new_total_qty
    if new_total_qty > 0 else 0
)
portfolio["position"] = new_total_qty
```

**매도 체결 시**:
```python
proceeds = quantity * executed_price
realized_pnl = quantity * (executed_price - portfolio["avg_cost"])
portfolio["cash"] += proceeds
portfolio["position"] -= quantity
portfolio["realized_pnl_cumulative"] += realized_pnl
# position이 0이 되면 avg_cost는 0으로 초기화
```

거래 수수료는 적용하지 않는다. 즉 수수료로 인한 추가 현금 차감, 매도 대금 차감, `fee` 로그는 생성하지 않는다.

각 서브턴(AM/PM) 체결 직후 즉시 포트폴리오에 반영하여, PM Turn 의사결정 시점에는 AM Turn 체결 결과가 이미 반영된 `cash`/`position`을 기준으로 `max_affordable_quantity`, `holding_quantity`가 계산되도록 한다.

---

## 8. 로그/CSV 스키마 변경

### 8.1 `submitted_orders.csv`

변경 전: `date, agent_id, subturn, action, price, quantity`
변경 후: `date, agent_id, subturn, action, quantity` (**price 컬럼 삭제**)

### 8.2 `exchange_fills.csv`

변경 전: `date, agent_id, direction, quantity, executed_price, ...`
변경 후:
```
date, agent_id, subturn, action, quantity, executed_price, status
```
`status` 값은 정상 체결의 경우 `filled`만 사용한다. 스키마 위반, `allowed_actions` 위반, 수량 범위 위반, `no_feasible_action` 같은 비정상 상황은 체결 로그가 아니라 별도 오류 로그에 기록한다.

### 8.3 `daily_exchange_summary.csv`

AM/PM 각 행에는 실제 체결 공시가를 `announced_price`로 기록한다. 하루 단위 종가가 필요한 요약 컬럼은 `close_price`라는 이름을 사용한다. 기존 `closing_price` 명칭은 새 구조에서는 사용하지 않는다.

---

## 9. 초기 상태 및 첫날 동작 재확인

- `portfolio_state t000`: `cash = ini_cash`, `positions = []` — **변경 없음**.
- Day 1 AM Turn: 시가 공시 → `allowed_actions = ["buy"]`만 계산되므로 모든 에이전트는 `buy`만 선택 가능하다(매도는 보유 수량 0이라 애초에 선택지에 없음, 별도 분기 코드 불필요). `buy` 결정은 현금 범위 내에서 시가로 즉시 체결되며 최소 1주 이상이다.
- Day 1 PM Turn: 종가 공시 → AM 체결 결과가 반영된 포트폴리오를 기준으로 `allowed_actions`가 다시 계산되고(AM에서 매수했다면 이제 `sell`도 선택 가능), 그 범위 내에서 매수/매도 판단.
- Day 2 이후: 완전히 동일한 코드 경로. "워밍업"이라는 별도 개념이 존재하지 않는다.

---

## 10. 기존 문서 항목별 후속 처리

### 10.1 항목 1 (콜옥션 규칙 명시 + 주문 이력)
가격 편차 기반 서술은 전부 삭제. 이 시스템에서는 프롬프트와 decision 검증 단계에서 가능한 수량 범위 안의 결정만 거래소로 전달하므로, 체결 실패 이력을 프롬프트에 제공할 필요는 낮다. 프롬프트에는 매 턴 `max_affordable_quantity`/`holding_quantity`를 제공하는 것만으로 충분할 수 있다. 과거 이력까지 필요한지는 실험 후 결정한다.

### 10.2 항목 2 (CoT 흐름)
§6.5에 반영 완료. 가격 보정 단계 삭제, 방향 결정 → 수량 결정 2단계로 축소.

### 10.3 항목 3 (호가 존중 체결)
본 문서 전체로 대체.

### 10.4 항목 4 (4시간봉)
AM/PM 2턴 구조, 뉴스 시간 분기(§6.3)는 유지. 13:00 중간가 앵커, `calculate_anchored_price()`, COUNTERSIDE는 삭제(§4.3, §6.1).

### 10.5 항목 5 (방향 검증 지표)
`compute_direction_metrics()` 로직(balanced accuracy, buy/sell recall)은 그대로 유효하다. 다만 입력 데이터 정의를 다음과 같이 조정한다:
- `llm_net_buy`: 그날 전체 에이전트의 (매수 quantity 합) - (매도 quantity 합)
- 기존과 동일한 방식으로 실제 순매수(real_net_buy)와 비교

추가로 새로운 지표를 도입할 것을 권장한다:
- **decision validation error rate**: `allowed_actions` 위반, 수량 범위 위반, JSON 스키마 위반 등으로 재시도 또는 오류 처리된 비율. 너무 높으면 프롬프트에 `max_affordable_quantity`/`holding_quantity`를 더 명확히 강조할 필요가 있음을 뜻한다.
- **`no_feasible_action` 발생 여부**: 정상 시뮬레이션에서는 0이어야 한다. 1건이라도 발생하면 `ini_cash` 설정을 재점검한다(§3.5).

### 10.6 항목 7 (deep analysis report)
5개 차트 중 **"2. 호가 편차 + 체결 범위"** 차트는 더 이상 존재하지 않는 데이터(호가 자체가 없음)이므로 삭제하거나, 다음으로 대체한다:
- **대체안**: "매수/매도 의사결정 분포 + 검증 오류 비율" — 날짜별 buy/sell 비율과, decision validation error 비율을 함께 표시.

나머지 4개 차트(거래량 vs 수익률, Disposition Effect, 거래량 클러스터링, Gini+Lorenz)는 `exchange_fills.csv`의 `quantity`, `executed_price` 필드를 그대로 사용할 수 있으므로 로직 변경이 거의 없다(컬럼명만 맞추면 됨).

---

## 11. 전체 삭제 대상 코드 요약 (체크리스트)

- [ ] `exchange_agent.py`: `calculate_anchored_price()` 삭제
- [ ] `exchange_agent.py`: COUNTERSIDE 주문 생성/매칭 로직 삭제
- [ ] `exchange_agent.py`: 매수/매도 가격 조건 비교(`bid >= target`, `ask <= target`) 로직 삭제
- [ ] `memory_agent.py`: `N_WARMUP`, `execute_warmup_orders()` 삭제
- [ ] `daily_cycle.py` / `simulation.py`: `override_price`, mid_price(13:00) 관련 파라미터 삭제
- [ ] `fundamental_agent.py`: mid 가격을 참조하던 로직 삭제, `load_daily_price_csv()`로 교체
- [ ] `make_decision.txt`: price 입력 필드, 호가 보정 CoT 단계 삭제
- [ ] `validate_trading_direction.py`, `generate_deep_analysis_report.py`: `user_id == "COUNTERSIDE"` 필터링 코드 삭제 (더 이상 COUNTERSIDE 데이터가 생성되지 않음)
- [ ] `submitted_orders.csv` 스키마: `price` 컬럼 삭제
- [ ] `exchange_fills.csv` 스키마: `quantity`, `executed_price`, `status` 필드 사용. 정상 체결은 `status=filled`, `executed_price`는 턴 내 전 에이전트 동일값

## 12. 전체 신규 구현 체크리스트

- [ ] `data/stock_data_daily.csv` (또는 기존 4h 파일에서 open/close만 사용) 준비 완료
- [ ] `fundamental_agent.load_daily_price_csv()` 구현
- [ ] `exchange_agent.get_allowed_actions()`, `execute_binary_orders()` 구현 (부분 체결 없음, hold 없음, 유효 주문 전량 체결)
- [ ] `daily_cycle.run_daily_turn()`이 AM=시가, PM=종가로 공시가를 주입하고 즉시 체결
- [ ] `collect_context()`가 `announced_price`, `max_affordable_quantity`, `holding_quantity`, `allowed_actions`를 매 턴 계산해서 반환
- [ ] `make_decision.txt`에서 에이전트가 더 이상 price를 출력하지 않고, `action`이 `"hold"`를 절대 반환하지 않으며, `allowed_actions` 범위 내에서만 응답하는지 확인 (스키마 검증)
- [ ] LLM이 `allowed_actions`에 없는 방향을 출력했을 때 강제 치환하지 않고 decision 검증 오류로 처리되는지 확인
- [ ] 모든 체결 건에서 `quantity >= 1`인지 확인 (§3.5 예외 상황 제외)
- [ ] Day 1부터 워밍업 특수분기 없이 동일 코드 경로로 동작하는지, Day 1 AM에서 전원이 `buy`만 선택했는지 확인
- [ ] `exchange_fills.csv`에서 같은 날 같은 서브턴의 모든 체결 건이 동일한 `executed_price`를 갖는지 확인
- [ ] 자금 부족/보유 부족을 초래하는 수량이 거래소로 전달되지 않고 decision 검증 단계에서 걸러지는지 확인
- [ ] `no_feasible_action`이 실제로는 발생하지 않는지 확인
- [ ] 시뮬레이션 시작 전 `ini_cash >= max(daily_price) * 1`이 검증(assert)되는지 확인 (§3.5)
- [ ] `validate_trading_direction.py`가 새 `exchange_fills.csv` 스키마로 정상 작동하는지 확인
- [ ] `generate_deep_analysis_report.py`의 차트 2번이 새 데이터(매수/매도 분포·검증 오류 비율)로 대체되었는지 확인

---

## 13. 요약: 기존 방식 vs 새 방식 한눈에 비교

| 구분 | 기존 방식 | 새 방식 |
|---|---|---|
| 에이전트 출력 | action(buy/sell/hold), **price**, quantity | action(**buy/sell만, hold 없음**), quantity (**price 없음**) |
| 거래 의무 | 관망(hold) 가능, 거래 안 해도 됨 | **매 턴 반드시 1주 이상 매수 또는 매도** |
| 체결가 결정 | 에이전트 호가 or 목표가(실제가) 혼합 | 항상 그 턴의 실제 공시가(시가/종가) 단일값 |
| 체결 조건 | 가격 조건(bid≥target 등) | 자금/보유 수량 조건만 + `allowed_actions`로 방향 제한 |
| 수급 불균형 처리 | COUNTERSIDE가 메움 | 존재하지 않음 (매칭 자체가 없음) |
| Day 1 처리 | 워밍업 특수 로직 | 특수 처리 없음, 동일 코드 경로(`allowed_actions=["buy"]`로 자연히 처리) |
| 하루 가격 포인트 | 시가/13:00/종가 (3개) | 시가/종가 (2개) |
| 수량 부족 시 처리 | 미체결 or 지정가 매칭 실패 | decision 검증 단계에서 차단. 거래소는 유효 수량만 전량 체결 |
| 분석 초점 | 호가 전략의 정교함 | 매수/매도 방향·타이밍의 현실성 |
