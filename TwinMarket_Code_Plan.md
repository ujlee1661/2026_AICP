# TwinMarket 코드 수정 계획서

> 참조 문서: `TwinMarket_Improvement_Proposal.md`
> 이 문서는 Proposal의 각 항목을 **구체적인 코드 변경 지침**으로 변환한 실행 계획서다.

---

## 이 파일을 읽는 방법

코드 수정을 시작하기 전에 다음 순서로 파일을 파악하라.

**Step 1. Proposal 읽기**
`TwinMarket_Improvement_Proposal.md`를 먼저 읽어 각 항목의 배경, 목적, 설계 의도를 이해한다.
"왜 바꾸는가"에 대한 설명은 모두 Proposal에 있다. 이 계획서에는 중복하지 않는다.

**Step 2. 구현 순서 파악**
항목 1 → 2 → 3 → 5 → 7 순으로 구현한다.
항목 4는 다른 항목보다 범위가 크므로(멀티파일, 멀티턴 구조 변경) 1~3 완료 후 착수한다.
항목 6은 코드 변경 없이 문서 작성으로 완결되며, 이미 `System_Logic.md`로 별도 생성돼 있다.

**Step 3. 파일 수정 전 원본 읽기**
이 계획서에 예시 코드가 있더라도, 반드시 실제 코드 파일을 먼저 열어 함수 시그니처와 기존 구조를 파악한 뒤 수정하라. 예시는 패턴을 보여주기 위한 것이지 실제 코드가 아니다.

**Step 4. 항목 완료 시 검증**
각 항목 끝의 체크리스트로 구현이 올바른지 확인한다.

---

## 핵심 파일 위치 (twinmarket_community/ 기준)

| 역할 | 경로 |
|---|---|
| 에이전트 의사결정 프롬프트 | `prompts/make_decision.txt` |
| 메모리(DB) 에이전트 | `twinmarket_kr/agents/memory_agent.py` |
| 컨텍스트 수집 | `twinmarket_kr/core/collect_context.py` |
| 일별 시뮬레이션 루프 | `twinmarket_kr/core/daily_cycle.py` |
| 거래소(체결 엔진) | `twinmarket_kr/agents/exchange_agent.py` |
| 주가 데이터 로더 | `twinmarket_kr/agents/fundamental_agent.py` |
| 방향 검증 스크립트 | `validation/validate_trading_direction.py` |
| 로그 출력 경로 | `outputs/logs/{run_id}/` |

---

## 항목 1: 콜옥션 규칙 명시 + 과거 주문 내역 컨텍스트 추가

**목적 요약**: 에이전트가 "내 주문이 왜 체결되지 않았는가"를 스스로 파악하게 한다.
이를 위해 체결 규칙을 프롬프트에 명시하고, 과거 주문 이력(제출가 vs 실제 종가)을 컨텍스트로 제공한다.

---

### 변경 파일 ①: `twinmarket_kr/agents/memory_agent.py`

**추가할 메서드**: `get_recent_order_history(agent_id, last_n=5)`

`trade_log` 테이블에서 해당 에이전트의 최근 N턴 거래 이력을 조회한다.
각 건에 대해 제출 호가, 체결 여부, 당일 실제 종가를 포함한 딕셔너리 리스트를 반환한다.

```python
def get_recent_order_history(self, agent_id: str, last_n: int = 5) -> list[dict]:
    conn = self._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            tl.date,
            tl.action,
            tl.submitted_price,
            tl.status,
            tl.executed_price,
            tl.filled_quantity,
            des.closing_price AS actual_close
        FROM trade_log tl
        LEFT JOIN daily_exchange_summary des ON tl.date = des.date
        WHERE tl.agent_id = ?
          AND tl.action IN ('buy', 'sell')
        ORDER BY tl.turn DESC
        LIMIT ?
    """, (agent_id, last_n))
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        date, action, submitted_price, status, executed_price, filled_qty, actual_close = row
        filled = (status == 'filled' and filled_qty and filled_qty > 0)
        result.append({
            "date": date,
            "action": action,
            "submitted_price": submitted_price,
            "filled": filled,
            "executed_price": executed_price if filled else None,
            "actual_close": actual_close,
        })
    return result
```

**주의**: `daily_exchange_summary` 테이블이 에이전트 DB가 아닌 별도 CSV에 있을 경우,
`closing_price`를 CSV에서 `dict`로 로드한 뒤 Python 레벨에서 매핑하는 방식으로 대체한다.

---

### 변경 파일 ②: `twinmarket_kr/core/collect_context.py`

**수정 위치**: `collect_context()` 함수 내부, `portfolio_summary` 조회 직후

아래 코드를 삽입한다:

```python
# 기존 코드 (유지)
portfolio_summary = memory_agent.get_portfolio_summary(agent_id, turn - 1)

# ─── 추가 시작 ───────────────────────────────────────────
raw_history = memory_agent.get_recent_order_history(agent_id, last_n=5)

order_history_lines = []
for h in raw_history:
    price_str = f"{h['submitted_price']:,.0f}원" if h['submitted_price'] else "N/A"
    close_str = f"{h['actual_close']:,.0f}원"    if h['actual_close']  else "N/A"
    if h['filled']:
        exec_str = f"{h['executed_price']:,.0f}원" if h['executed_price'] else "체결"
        line = (f"{h['date']}: {h['action']} {price_str} 제출 → "
                f"체결 (당일 종가 {close_str}, 체결가 {exec_str})")
    else:
        if h['submitted_price'] and h['actual_close']:
            dev = (h['submitted_price'] - h['actual_close']) / h['actual_close'] * 100
            line = (f"{h['date']}: {h['action']} {price_str} 제출 → "
                    f"미체결 (당일 종가 {close_str}, 편차 {dev:+.1f}%)")
        else:
            line = f"{h['date']}: {h['action']} {price_str} 제출 → 미체결"
    order_history_lines.append(line)

order_history_text = (
    "\n".join(order_history_lines) if order_history_lines else "이전 주문 이력 없음"
)
# ─── 추가 끝 ────────────────────────────────────────────
```

**반환 딕셔너리에 키 추가**:

```python
context = {
    ...기존 키들...,
    "order_history": order_history_text,   # ← 신규 추가
}
```

---

### 변경 파일 ③: `prompts/make_decision.txt`

두 블록을 추가한다.

**추가 ①: 체결 규칙 안내** — 프롬프트 상단 또는 `{trading_constraints}` 설명 직후에 삽입:

```
[체결 규칙 안내]
오늘 제출한 주문은 장 마감 시점에 삼성전자 실제 종가를 기준으로 일괄 심사된다.
- 매수 주문: 제출 호가 ≥ 실제 종가 → 체결 / 미만이면 미체결
- 매도 주문: 제출 호가 ≤ 실제 종가 → 체결 / 초과이면 미체결
현재 제공되는 current_price는 전일 종가이므로, 오늘 종가를 스스로 추정하여 호가를 결정해야 한다.
매수를 원하면 예상 종가보다 충분히 높게, 매도를 원하면 충분히 낮게 주문해야 체결 가능성이 높다.
```

**추가 ②: `{order_history}` 변수** — `{portfolio_summary}` 와 CoT 지시문 사이에 삽입:

```
[최근 주문 이력]
{order_history}
```

**CoT 지시문 수정** — 기존 단계 지시 말미에 다음 문단을 추가한다:

```
호가를 결정하기 전, 최근 주문 이력을 참고하여 미체결 주문이 있다면
그 원인(제출가 vs 종가 편차)을 간략히 파악하고 오늘 호가 보정에 반영하라.
단, 이 단계는 Belief와 시장 분석을 통해 이미 결정한 매수/매도 방향을
"어느 가격에" 낼지 정밀화하는 것이며, 방향 자체를 바꾸는 단계가 아니다.
```

#### 검증

- [ ] 시뮬레이션 실행 후 `agent_turns.jsonl`의 `make_decision_input` 필드에 `order_history` 텍스트가 포함되는지 확인
- [ ] `submitted_orders.csv`에서 상승일 기준 매수 호가가 이전 실험 대비 상승 분포로 이동하는지 확인

---

## 항목 2: make_decision 내 CoT 흐름 정비

**목적 요약**: Belief 기반 방향 결정을 1순위로, 주문 이력 기반 가격 보정을 보조 단계로 명확히 구분한다.
항목 1에서 `{order_history}` 와 체결 규칙 설명이 추가된 이후에 적용한다.

---

### 변경 파일: `prompts/make_decision.txt`

기존 CoT 단계 지시문을 아래 순서로 재작성한다.
새로운 API 호출이나 파일이 필요 없다. 프롬프트 텍스트 수정만으로 완결된다.

**CoT 최종 단계 순서**:

```
Step 1. 오늘의 신념(belief_summary)과 시장 분석(market_analysis)을 검토하여
        매수 / 매도 방향을 결정한다. 방향은 이 단계에서 확정한다.

Step 2. 포트폴리오 상태(portfolio_summary)와 거래 제약(trading_constraints)을 확인하여
        거래 가능한 수량 범위를 파악한다.

Step 3. 최근 주문 이력(order_history)을 검토한다.
        미체결 주문이 있다면 제출가와 당일 종가의 편차를 확인하고,
        오늘 호가를 어느 방향으로 얼마나 보정할지 결정한다.
        (방향은 Step 1에서 이미 결정됐으므로 이 단계에서 바꾸지 않는다.)

Step 4. 위 분석을 종합하여 action, quantity, price를 결정하고 JSON으로 출력한다.
```

#### 검증

- [ ] `agent_turns.jsonl`의 action_reason에서 Step 1 (방향 판단), Step 3 (호가 보정) 근거가 각각 구분되어 기술되는지 확인

---

## 항목 3: 체결가를 에이전트 제출 호가로 변경

**목적 요약**: 현재는 모든 에이전트 체결이 종가(target_price)로 기록된다.
에이전트가 낸 호가대로 체결가를 기록해야 포트폴리오 계산(avg_cost, realized_pnl)이 현실적이 된다.

---

### 변경 파일: `twinmarket_kr/agents/exchange_agent.py`

**수정 위치**: 체결 루프에서 fill 딕셔너리를 생성하는 부분 (`executed_price` 할당 부분)

현재 패턴:

```python
for order in matched_orders:
    fill = {
        "user_id": order["user_id"],
        "direction": order["direction"],
        "quantity": order["quantity"],
        "executed_price": target_price,   # ← 모든 주문이 종가로 기록됨
        ...
    }
```

변경 후:

```python
for order in matched_orders:
    # COUNTERSIDE는 수급 보정 목적이므로 기존 방식 유지
    if order.get("user_id") == "COUNTERSIDE":
        exec_price = target_price
    else:
        exec_price = order["price"]   # 에이전트 제출 호가로 체결

    fill = {
        "user_id": order["user_id"],
        "direction": order["direction"],
        "quantity": order["quantity"],
        "executed_price": exec_price,
        ...
    }
```

**체결 조건 (변경 없음)**:
- 매수: `order["price"] >= target_price` → 체결 (체결가는 `order["price"]`)
- 매도: `order["price"] <= target_price` → 체결 (체결가는 `order["price"]`)

**포트폴리오 업데이트**: `exchange_fills.csv`의 `executed_price` 변경이 avg_cost, cash, realized_pnl 계산에 자동 반영된다. 별도 수정 불필요.

#### 검증

- [ ] `exchange_fills.csv`에서 COUNTERSIDE가 아닌 에이전트의 `executed_price` ≠ `closing_price` 인 행이 존재하는지 확인
- [ ] 같은 날 다른 가격으로 체결된 에이전트들이 서로 다른 avg_cost를 가지는지 `portfolio_updates.jsonl`에서 확인

---

## 항목 4: 4시간봉 도입 + 하루 2번 거래 (대형 변경)

**목적 요약**: 하루 1번 체결에서 AM(→13:00 체결)과 PM(→15:30 체결) 2번으로 확장하여
실제 장 중 정보 흐름을 반영한다.

> **선행 조건**: 항목 1~3 구현 및 검증 완료 후 착수. `data/stock_data_4h.csv` 사전 수집 필요.

---

### 신규 데이터 파일: `data/stock_data_4h.csv`

yfinance 또는 KIS Open API에서 005930.KS의 4h 봉 데이터를 수집해 아래 포맷으로 저장한다.

```
date,time_slot,price
2026-04-24,open,219000
2026-04-24,mid,221000
2026-04-24,close,219500
```

각 날짜마다 `open`(09:00), `mid`(13:00), `close`(15:30) 3개 행. 총 행수 = 거래일 수 × 3.

---

### 변경 파일 ①: `twinmarket_kr/agents/fundamental_agent.py`

4h 데이터 로드 함수를 추가한다:

```python
def load_4h_data_csv(csv_path: str) -> dict:
    """date → {"open": price, "mid": price, "close": price} 딕셔너리 반환"""
    result = {}
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = row["date"]
            if date not in result:
                result[date] = {}
            result[date][row["time_slot"]] = float(row["price"])
    return result
```

---

### 변경 파일 ②: `twinmarket_kr/agents/exchange_agent.py`

`calculate_anchored_price()` 함수가 외부에서 체결 기준가를 주입받을 수 있도록 시그니처를 변경한다:

```python
# 변경 전
def calculate_anchored_price(self, date: str) -> float:
    return self.real_prices[date]

# 변경 후
def calculate_anchored_price(self, date: str, override_price: float = None) -> float:
    if override_price is not None:
        return override_price
    return self.real_prices[date]
```

---

### 변경 파일 ③: `twinmarket_kr/core/collect_context.py`

`collect_context()` 함수에 `subturn` 파라미터를 추가한다:

```python
def collect_context(agent, turn, date, memory_agent, news_data,
                    subturn: str = "full",   # "am" | "pm" | "full"
                    open_price: float = None,
                    mid_price: float = None):

    if subturn == "am":
        # AM Turn: 전일 종가 + 시초가 + 장 전 뉴스 (09:00 이전)
        market_features = get_market_features_with_open(date, open_price)
        news_context = filter_news_by_time(news_data, date, end_time="09:00")
    elif subturn == "pm":
        # PM Turn: 오전봉 가격 + 09:00~15:30 뉴스
        market_features = get_market_features_with_mid(date, mid_price)
        news_context = filter_news_by_time(news_data, date,
                                           start_time="09:00", end_time="15:30")
    else:
        # 기존 방식 (full day)
        market_features = get_market_features(date)
        news_context = filter_news_by_time(news_data, date)
    ...
```

**뉴스 필터 함수** (뉴스 로딩 모듈에 추가):

```python
def filter_news_by_time(news_data, date, start_time=None, end_time=None):
    day_news = [n for n in news_data if n["date"] == date]
    if start_time:
        day_news = [n for n in day_news
                    if n.get("published_time", "00:00") >= start_time]
    if end_time:
        day_news = [n for n in day_news
                    if n.get("published_time", "23:59") <= end_time]
    return day_news
```

뉴스 데이터에 `published_time` 필드(HH:MM)가 없으면 사전 처리에서 추가한다.
Depth 2 추가 검색은 시간 제약 없이 이전 날짜까지 검색하므로 위 필터가 적용되지 않는다.

---

### 변경 파일 ④: `twinmarket_kr/core/daily_cycle.py`

`run_daily_turn(date)` 함수를 AM/PM 서브턴으로 분리한다:

```python
def run_daily_turn(date, agents, exchange, memory_agents, stock_4h, ...):
    open_price  = stock_4h[date]["open"]
    mid_price   = stock_4h[date]["mid"]
    close_price = stock_4h[date]["close"]

    # ── AM Turn: 시초가 + 장 전 뉴스 → 13:00 기준 체결 ─────────────
    am_orders = []
    for agent in agents:
        ctx = collect_context(agent, turn, date, memory_agents[agent.id],
                              news_data, subturn="am", open_price=open_price)
        decision = run_agent_decision(agent, ctx)
        am_orders.append(decision)

    am_fills = exchange.process_orders(
        am_orders, override_price=mid_price  # 13:00 기준 체결
    )
    update_portfolios(am_fills, memory_agents)

    # ── PM Turn: 오전봉 + 장 중 뉴스 → 15:30 기준 체결 ─────────────
    pm_orders = []
    for agent in agents:
        ctx = collect_context(agent, turn, date, memory_agents[agent.id],
                              news_data, subturn="pm", mid_price=mid_price)
        decision = run_agent_decision(agent, ctx)
        pm_orders.append(decision)

    pm_fills = exchange.process_orders(
        pm_orders, override_price=close_price  # 15:30 종가 기준 체결
    )
    update_portfolios(pm_fills, memory_agents)
```

#### 검증

- [ ] `submitted_orders.csv`에 동일 날짜, 동일 에이전트의 주문이 2건(am/pm) 존재하는지 확인
- [ ] am 체결이 mid_price 기준으로, pm 체결이 close_price 기준으로 이루어지는지 확인
- [ ] 뉴스 필터로 am에서는 장 전 뉴스만, pm에서는 장 중 뉴스가 포함되는지 확인

---

## 항목 5: validate_trading_direction.py 검증 지표 개선

**목적 요약**: 누적 Pearson은 상승장 + 단일가 구조에서 구조적 역전이 발생해 부정확한 평가를 한다.
방향 예측력을 제대로 측정하는 Balanced Accuracy와 Recall 지표를 Primary Metric으로 추가한다.

---

### 변경 파일: `validation/validate_trading_direction.py`

**추가할 함수**:

```python
def compute_direction_metrics(llm_net_buy: list, real_net_buy: list) -> dict:
    """일별 순매수 방향 일치율 및 Recall 계산"""
    n = len(llm_net_buy)
    assert n == len(real_net_buy)

    tp_buy  = sum(1 for l, r in zip(llm_net_buy, real_net_buy) if l > 0 and r > 0)
    fn_buy  = sum(1 for l, r in zip(llm_net_buy, real_net_buy) if l <= 0 and r > 0)
    tp_sell = sum(1 for l, r in zip(llm_net_buy, real_net_buy) if l < 0 and r < 0)
    fn_sell = sum(1 for l, r in zip(llm_net_buy, real_net_buy) if l >= 0 and r < 0)

    direction_match = sum(
        1 for l, r in zip(llm_net_buy, real_net_buy)
        if (l > 0 and r > 0) or (l < 0 and r < 0)
    ) / n

    buy_recall  = tp_buy  / (tp_buy  + fn_buy)  if (tp_buy  + fn_buy)  > 0 else 0.0
    sell_recall = tp_sell / (tp_sell + fn_sell) if (tp_sell + fn_sell) > 0 else 0.0
    balanced_accuracy = (buy_recall + sell_recall) / 2

    return {
        "direction_match_rate": round(direction_match, 4),
        "buy_recall":           round(buy_recall, 4),
        "sell_recall":          round(sell_recall, 4),
        "balanced_accuracy":    round(balanced_accuracy, 4),
    }
```

**`summary_metrics.json` 출력 구조 변경**:

기존 Pearson 지표를 `reference_metrics`로 이동하고, 새 지표를 `primary_metrics`로 배치한다.

```json
{
  "primary_metrics": {
    "balanced_accuracy": 0.75,
    "buy_recall": 0.50,
    "sell_recall": 1.00,
    "direction_match_rate": 0.667
  },
  "reference_metrics": {
    "pearson_daily": 0.412,
    "pearson_cumulative": -0.872,
    "note": "누적 Pearson은 상승장 + 단일가 체결 구조상 구조적 역전이 발생할 수 있음"
  }
}
```

#### 검증

- [ ] `summary_metrics.json`에 `primary_metrics.balanced_accuracy` 키 존재 확인
- [ ] buy_recall + sell_recall이 균형을 이루는지 (일방적으로 0이면 레이블 불균형 점검)
- [ ] `reference_metrics.note` 문자열이 포함됐는지 확인

---

## 항목 7: generate_deep_analysis_report.py

**목적 요약**: 시뮬레이션 로그를 읽어 5개 분석 차트를 생성하고 PDF 보고서로 저장한다.

**파일 위치**: `scripts/generate_deep_analysis_report.py` (이미 생성됨)

**실행 방법**:
```bash
python scripts/generate_deep_analysis_report.py --run-id simulation_20260701_180626
```

**출력 위치**: `outputs/reports/deep_analysis_{run_id}.pdf`

**5개 분석 차트 요약**:

| 차트 | 분석 내용 | 사용 데이터 |
|---|---|---|
| 1. 에이전트 거래량 vs 수익률 | 많이 거래한 에이전트가 수익이 더 좋은가? | exchange_fills.csv + portfolio_updates.jsonl |
| 2. 호가 편차 + 체결 범위 | 상승/하락일별 체결 패턴과 미체결 편차 분포 | submitted_orders.csv + exchange_fills.csv + daily_exchange_summary.csv |
| 3. Disposition Effect | 이익 실현 vs 손실 지속 성향 | exchange_fills.csv + portfolio_updates.jsonl |
| 4. 거래량 클러스터링 | volume_t vs volume_{t-1} 자기상관 | daily_exchange_summary.csv |
| 5. Gini + Lorenz Curve | 에이전트 간 거래 집중도 불균형 | exchange_fills.csv |

상세 구현은 `scripts/generate_deep_analysis_report.py` 파일을 참고한다.

---

## 전체 검증 체크리스트

- [ ] **항목 1**: 프롬프트 컨텍스트에 `order_history` 텍스트 포함 확인
- [ ] **항목 1**: 상승일 매수 호가 분포가 종가 방향으로 이동
- [ ] **항목 2**: CoT 내 방향 결정 → 가격 보정 순서가 유지되는지 확인
- [ ] **항목 3**: 에이전트 `executed_price` = 제출 호가 (≠ 종가)
- [ ] **항목 4**: 하루 2건 로그 (am/pm) 존재, 각각 다른 체결 기준가
- [ ] **항목 5**: `summary_metrics.json`에 Primary Metric 4종 모두 존재
- [ ] **항목 7**: PDF 정상 생성 및 5개 섹션 렌더링