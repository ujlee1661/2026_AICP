# 주문 매칭 엔진 설계서 — 실가격 앵커 집합경매 시스템

---

## 1. 시스템 목적 및 설계 동기

### 왜 실제 가격을 anchor로 사용하는가

에이전트 기반 시장 시뮬레이션의 근본적인 한계는 **에이전트만으로 시장 가격을 완전히 재현할 수 없다**는 점이다. 실제 주식 시장의 가격은 개인 투자자뿐만 아니라 기관투자자, 외국인 투자자, 프로그램 매매, 파생상품 헤지 등 수백만 명의 참여자가 상호작용하여 형성된다. 1000명의 LLM 에이전트만으로 이 복잡한 가격 형성 과정을 완전히 모사하는 것은 현실적으로 불가능하다.

따라서 이 시스템은 **가격을 시뮬레이션 내부에서 발견하려 하지 않는다**. 대신 이미 역사적으로 결정된 실제 종가를 그대로 사용하며, 에이전트들의 주문이 그 가격에서 체결되도록 시장 구조를 설계한다. 이렇게 하면 Macro 레벨의 Stylized Facts(수익률 분포, 변동성 클러스터링, 두꺼운 꼬리 분포 등)는 실제 데이터에서 자연스럽게 재현되므로, 그것을 에이전트로 설명해야 한다는 부담이 없어진다. 연구의 초점을 **에이전트들의 개별 행동 패턴과 시장 미시구조(market microstructure)** 로 좁힐 수 있다.

### 수량 보정 시스템의 근거 — 기관/외국인 투자자 모델

실가격을 anchor로 사용하면 새로운 문제가 생긴다. 에이전트들의 매수/매도 주문이 반드시 해당 가격에서 균형을 이루지는 않는다는 것이다. 어떤 날은 매수가 압도적이고, 어떤 날은 매도가 압도적일 수 있다. 이 불균형을 그냥 두면 가격을 실가격에 고정시키는 것 자체가 불가능해진다.

이 불균형을 메우는 존재가 바로 **기관/외국인 투자자**다. 실제 시장에서도 개인 투자자들이 한 방향으로 쏠릴 때 기관이나 외국인이 반대 포지션을 취하는 현상은 매우 잘 알려져 있다. 개인이 패닉 매도할 때 기관이 저가 매수하고, 개인이 과열 매수할 때 기관이 물량을 소화하는 구조다. 따라서 에이전트 주문의 불균형을 기관/외국인이 반대 방향으로 흡수한다는 설정은 단순한 기술적 편의가 아니라 실제 시장 메커니즘을 반영한 합리적인 가정이다.

이렇게 설계하면 시스템에서 매일 기록되는 `INSTITUTIONAL` 주문의 방향과 규모를 실제 기관/외국인 매매 데이터와 비교하여 **시스템의 타당성을 검증**할 수 있다. 개인(에이전트)들이 순매수할 때 INSTITUTIONAL이 순매도 방향으로 집계된다면, 이는 실제 시장에서도 관찰되는 패턴이므로 시뮬레이션의 현실성을 간접 지지하는 근거가 된다.

### 초기 Warm-up 기간의 필요성

시뮬레이션 첫날에는 모든 에이전트가 주식을 전혀 보유하지 않은 상태에서 시작한다. 이 상태 그대로 집합경매(단일가)를 진행하면 모든 에이전트가 동일한 단일 가격에 매수하게 되어 **전원이 동일한 평단가**를 갖게 된다. 이는 실제 시장과 전혀 다른 인위적인 출발점이다.

실제 시장의 투자자들은 각자 다른 시점에, 다른 가격에 매수하여 고유한 평단가를 형성하고 있다. 에이전트들도 이와 유사한 상태에서 시뮬레이션이 시작되어야 각자의 손익 상황에 따라 다른 매매 결정을 내릴 수 있다. **평단가가 모두 같다면 에이전트 간의 행동 다양성이 크게 줄어든다**.

따라서 초반 3일(warm-up) 동안은 **각 에이전트의 주문이 자기가 제출한 가격으로 그대로 체결**되도록 한다. 같은 종목을 매수하더라도 누군가는 10.1달러에, 누군가는 10.5달러에 체결되어 자연스럽게 서로 다른 평단가가 형성된다. 이 기간의 거래 자체는 연구 분석에서 제외한다.

중요한 점은 warm-up 기간에도 **시가/종가의 기준은 실제 시장 가격을 그대로 사용**한다는 것이다. 서킷브레이커 범위, 다음 날 프롬프트에 들어가는 시장 정보, StockData에 기록되는 종가 모두 실가격 기준으로 유지된다. 체결 방식만 개별 가격으로 처리될 뿐이다.

---

## 2. 전체 시스템 흐름

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                     주문 매칭 엔진 — 전체 흐름                                ║
╚══════════════════════════════════════════════════════════════════════════════╝

[입력]
  에이전트 주문 리스트  ←──  simulation.py (LLM 매매 결정)
  실제 종가 데이터     ←──  StockData DB (오늘의 real_close_price)
  전일 실제 종가       ←──  StockData DB (서킷브레이커 기준)
  day_number          ←──  simulation.py (현재 시뮬레이션 날짜)

           │
           ▼
┌──────────────────────────┐
│   Phase 분기 판단         │
│                          │
│  day ≤ 3  → Phase 1      │
│  day ≤ 7  → Phase 2      │
│  day > 7  → Phase 3      │
└────────────┬─────────────┘
             │
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
[Phase 1]         [Phase 2/3]
개별 가격 체결     실가격 앵커 집합경매
    │                 │
    │            ┌────┴──────────────────┐
    │            │  서킷브레이커 필터링    │
    │            │  (±30% 범위 밖 제거)   │
    │            └────────────┬──────────┘
    │                         │
    │            ┌────────────┴──────────┐
    │            │  target_price 기준    │
    │            │  buy_vol / sell_vol   │
    │            │  계산                 │
    │            └────────────┬──────────┘
    │                         │
    │            ┌────────────┴──────────┐
    │            │  imbalance 계산        │
    │            │  INSTITUTIONAL 주입   │
    │            │  (one-shot injection) │
    │            └────────────┬──────────┘
    │                         │
    └──────────┬──────────────┘
               │
               ▼
    ┌──────────────────────┐
    │  체결 기록 생성        │
    │  transactions list   │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │  DB 저장              │
    │  · TradingDetails    │
    │  · StockData 종가     │
    │  · Profiles 잔고      │
    └──────────────────────┘
```

---

## 3. Phase 시스템

```
Day 1 ~ 3   : Phase 1 — INDIVIDUAL_EXECUTION
              (warm-up, 개별 제출가 즉시 체결, 평단가 다양화)

Day 4 ~ 7   : Phase 2 — CALL_AUCTION_ANCHORED  [분석 제외]
              (실가격 앵커 집합경매, 포지션 안정화)

Day 8 ~     : Phase 3 — CALL_AUCTION_ANCHORED  [분석 활성화]
              (실가격 앵커 집합경매, 본격 연구 분석)

CLI 파라미터:
  --n_warmup      default=3   (Phase 1 기간)
  --n_transition  default=4   (Phase 2 기간)
```

---

## 4. Phase 1 — INDIVIDUAL_EXECUTION 알고리즘

**목적**: 에이전트별 다양한 평단가 형성. 체결 방식만 개별 가격이며, 종가/시가 기준은 실가격 유지.

```python
def execute_warmup_orders(buy_orders, sell_orders, day_number, real_price, last_real_price):
    """
    real_price      : 오늘의 실제 시장 종가 (StockData — 이 날의 기준가)
    last_real_price : 전일 실제 종가 (서킷브레이커 기준)
    """

    upper_limit = last_real_price * 1.3
    lower_limit = last_real_price * 0.7

    transactions = []

    # Day 1: 매수만 허용 (전 에이전트 보유 주식 없음)
    target_orders = buy_orders if day_number == 1 else buy_orders + sell_orders

    for order in target_orders:

        # 시장가 주문(price=0) → 실제 종가로 대체
        exec_price = real_price if order.price == 0 else order.price

        # 서킷브레이커 범위 밖 주문 제거
        if not (lower_limit <= exec_price <= upper_limit):
            continue

        # 전량 즉시 체결 (수량 제한 없음)
        transactions.append({
            "stock_code"        : order.stock_code,
            "user_id"           : order.user_id,
            "direction"         : order.direction,
            "executed_price"    : exec_price,       # 각자 다른 가격
            "executed_quantity" : order.quantity,
            "timestamp"         : order.timestamp,
        })

    # 종가는 실가격으로 기록 (체결가와 무관)
    closing_price = real_price
    volume = sum(t["executed_quantity"] for t in transactions)

    return closing_price, volume, transactions
```

**핵심 특징**:
- 체결가는 각 에이전트의 제출가 → 에이전트마다 평단가가 다름
- `closing_price = real_price` → 다음 날 에이전트 프롬프트에 실가격이 전달됨
- 전량 체결 보장 (미체결 주문 없음)
- INSTITUTIONAL 주입 없음

---

## 5. Phase 2/3 — CALL_AUCTION_ANCHORED 알고리즘

**목적**: 실가격을 단일 체결가로 고정하고, 불균형은 기관/외국인(INSTITUTIONAL)이 흡수.

```python
def calculate_anchored_price(buy_orders, sell_orders, target_price, last_real_price):
    """
    target_price    : 오늘의 실제 시장 종가 (체결 기준가)
    last_real_price : 전일 실제 종가 (서킷브레이커 기준)
    """

    # ── STEP 1: 서킷브레이커 클리핑 ──────────────────────────────────
    upper_limit  = last_real_price * 1.3
    lower_limit  = last_real_price * 0.7
    target_price = max(lower_limit, min(upper_limit, target_price))

    # 서킷브레이커 범위 밖 에이전트 주문 제거
    buy_orders  = [o for o in buy_orders  if lower_limit <= o.price <= upper_limit
                                          or o.price == 0]
    sell_orders = [o for o in sell_orders if lower_limit <= o.price <= upper_limit
                                          or o.price == 0]

    # ── STEP 2: 시장가 주문(price=0) 처리 ────────────────────────────
    for o in buy_orders:
        if o.price == 0:
            o.price = upper_limit   # 매수 시장가 → 상한가에 배치 (무조건 체결 의도)
    for o in sell_orders:
        if o.price == 0:
            o.price = lower_limit   # 매도 시장가 → 하한가에 배치

    # ── STEP 3: target_price 기준 체결 가능 수량 계산 ─────────────────
    buy_vol  = sum(o.quantity for o in buy_orders  if o.price >= target_price)
    sell_vol = sum(o.quantity for o in sell_orders if o.price <= target_price)

    # ── STEP 4: 불균형 → INSTITUTIONAL one-shot injection ────────────
    imbalance = buy_vol - sell_vol

    if imbalance > 0:
        # 에이전트 매수 우세 → 기관/외국인이 매도로 흡수
        institutional = Order(
            stock_code = stock_code,
            price      = target_price,   # target_price에 정확히 배치
            quantity   = imbalance,      # 불균형만큼 정확히
            user_id    = "INSTITUTIONAL",
            direction  = "sell",
            timestamp  = max_agent_timestamp + 1ms   # 에이전트보다 늦은 우선순위
        )
        sell_orders.append(institutional)

    elif imbalance < 0:
        # 에이전트 매도 우세 → 기관/외국인이 매수로 흡수
        institutional = Order(
            stock_code = stock_code,
            price      = target_price,
            quantity   = abs(imbalance),
            user_id    = "INSTITUTIONAL",
            direction  = "buy",
            timestamp  = max_agent_timestamp + 1ms
        )
        buy_orders.append(institutional)

    # imbalance == 0: 주입 없음 (완벽 균형)

    # ── STEP 5: 단일가 체결 (closing_price = target_price) ───────────
    # 정렬: 매수(-price, timestamp), 매도(+price, timestamp)
    # → INSTITUTIONAL은 timestamp가 가장 늦으므로 에이전트 주문이 먼저 소진됨

    matched_volume = max(buy_vol, sell_vol)  # injection 후 buy_vol == sell_vol
    transactions   = []
    remaining      = matched_volume

    for order in sorted(buy_orders,  key=lambda o: (-o.price, o.timestamp)):
        if order.price >= target_price and remaining > 0:
            qty = min(order.quantity, remaining)
            transactions.append({executed_price: target_price, executed_quantity: qty, ...})
            remaining -= qty

    remaining = matched_volume
    for order in sorted(sell_orders, key=lambda o: (o.price, o.timestamp)):
        if order.price <= target_price and remaining > 0:
            qty = min(order.quantity, remaining)
            transactions.append({executed_price: target_price, executed_quantity: qty, ...})
            remaining -= qty

    # ── STEP 6: 반환 ──────────────────────────────────────────────────
    return target_price, matched_volume, transactions
```

### 엣지 케이스

| 상황 | 처리 |
|------|------|
| buy_orders 없음 | INSTITUTIONAL이 sell_vol 전량 매수 주입 |
| sell_orders 없음 | INSTITUTIONAL이 buy_vol 전량 매도 주입 |
| 둘 다 없음 | last_real_price 반환, volume=0 |
| 모든 에이전트 주문이 target_price 미접촉 | buy_vol=sell_vol=0 → 주입 없음, volume=0 |

---

## 6. 전체 일별 처리 함수 흐름

```python
def process_daily_orders(orders, real_prices, last_real_prices, current_date, day_number, n_warmup):
    """
    orders           : 모든 에이전트 주문 리스트
    real_prices      : {stock_code: 오늘의 실제 종가}   — StockData에서 조회
    last_real_prices : {stock_code: 전일 실제 종가}     — 서킷브레이커 기준
    day_number       : 시뮬레이션 경과 일수 (1부터 시작)
    n_warmup         : warm-up 기간 (default=3)
    """

    # 종목별로 buy/sell 분류
    stock_orders = defaultdict(lambda: {"buy": [], "sell": []})
    for order in orders:
        stock_orders[order.stock_code][order.direction].append(order)

    results = {}

    for stock_code, {buy, sell} in stock_orders.items():

        real_price      = real_prices[stock_code]
        last_real_price = last_real_prices[stock_code]

        if day_number <= n_warmup:
            # Phase 1: 개별 가격 즉시 체결
            closing_price, volume, transactions = execute_warmup_orders(
                buy, sell, day_number, real_price, last_real_price
            )
        else:
            # Phase 2/3: 실가격 앵커 집합경매
            closing_price, volume, transactions = calculate_anchored_price(
                buy, sell, real_price, last_real_price
            )

        results[stock_code] = {
            "closing_price" : closing_price,   # 항상 real_price (Phase 1 포함)
            "volume"        : volume,
            "transactions"  : transactions,
        }

    return results
```

---

## 7. DB 기록 방식 (참고)

### TradingDetails 테이블 — 체결 내역 기록

체결된 모든 거래는 INSTITUTIONAL 포함하여 그대로 기록한다.

```
TradingDetails 기록 항목:
  date              : 거래일
  stock_id          : 종목 코드
  user_id           : 에이전트 ID 또는 "INSTITUTIONAL"
  trading_direction : "buy" / "sell"
  price             : 체결 가격
  volume            : 체결 수량

Phase 1: user_id = 에이전트 ID, price = 각자의 제출가
Phase 2/3: user_id = 에이전트 ID 또는 "INSTITUTIONAL", price = real_price (단일가)
```

### StockData 테이블 — 일별 종가 기록

```
Phase 1, 2, 3 모두:
  close_price = real_price  (실제 시장 종가)
  pct_chg     = (real_price - last_real_price) / last_real_price
```

### Profiles 테이블 — 에이전트 자산 업데이트

```
체결된 transactions 기준으로:
  current_cash     : 매수 시 차감, 매도 시 증가
  cur_positions    : 종목별 보유 수량 업데이트
  total_value      : current_cash + Σ(cur_positions × close_price)
  return_rate      : (total_value - initial_value) / initial_value
```

### INSTITUTIONAL 검증 쿼리

```sql
SELECT date, stock_id,
       SUM(CASE WHEN trading_direction='buy'  THEN volume ELSE 0    END) AS inst_buy,
       SUM(CASE WHEN trading_direction='sell' THEN volume ELSE 0    END) AS inst_sell,
       SUM(CASE WHEN trading_direction='buy'  THEN volume ELSE -volume END) AS inst_net
FROM TradingDetails
WHERE user_id = 'INSTITUTIONAL'
GROUP BY date, stock_id
ORDER BY date, stock_id;
-- inst_net이 실제 기관/외국인 순매수 방향과 양의 상관관계인지 검증
```

---

## 8. 검증 계획

1. **평단가 다양성**: Day 1~3 동일 종목에서 에이전트별 체결가가 서로 다른지 확인
2. **종가 고정**: Phase 2/3에서 `closing_price == real_close_price` 를 전 거래일에 걸쳐 확인
3. **INSTITUTIONAL 방향**: 에이전트 매수 우세일 때 inst_net < 0 (매도), 매도 우세일 때 inst_net > 0 (매수) 확인
4. **에이전트 우선 체결**: INSTITUTIONAL이 잔여 물량만 소화하고 에이전트 주문이 먼저 소진되는지 확인
5. **외부 상관 검증**: inst_net vs 실제 기관/외국인 순매수 시계열 데이터 Pearson Correlation

---

## 9. 설계 타당성 Q&A

이 섹션은 설계 과정에서 제기된 방법론적 질문들과 그에 대한 반론, 그리고 각 반론의 타당성 평가를 기록한다.

---

### Q1. 실가격을 입력으로 쓰면 동어반복(tautology) 아닌가?

**질문 요지**

에이전트들이 매일 실가격을 보고 Belief를 업데이트하고, 실가격을 보고 매매 결정을 내리며, 결과 종가도 실가격으로 기록된다. 이 구조에서 에이전트 행동이 실제 시장 흐름과 상관관계를 보인다면, 그것이 에이전트가 합리적이어서인지 동일한 입력(실가격)에 의한 결과인지 구별할 수 없다.

**설계자 반론**

이 시스템의 연구 목적은 에이전트 행동의 합리성을 검증하거나 가격을 내생적으로 재현하는 것이 아니다. 목적은 **이 시뮬레이션 환경 안에서 LLM 에이전트들이 어떻게 행동하는가를 관찰**하는 것이다. 실가격은 에이전트들이 반응하는 외생적 시장 현실이며, 그 현실에 대한 반응 패턴(Belief 진화, 커뮤니티 전파, 전략 유형별 차이)이 연구 대상이다. 이는 실험경제학에서 피험자에게 외부 가격 환경을 주고 행동을 관찰하는 방식과 동일한 구조다. Macro Stylized Facts 재현의 부담을 덜어내고 연구 초점을 Micro 행동으로 좁히기 위해 의도적으로 선택한 설계다.

**평가: 반론 타당함**

동어반복 비판은 "에이전트들이 실제 가격을 만들어낼 수 있는가"를 연구 목적으로 가정할 때 성립한다. 이 시스템은 그런 주장을 하지 않는다. 다만 연구 결과를 해석할 때 한 가지는 주의해야 한다. "에이전트들이 가격 상승 시 낙관적 Belief를 가진다"는 수준의 발견은 실가격 입력에 의한 자명한 결과이므로 연구 기여로 보기 어렵다. **의미 있는 발견은 동일한 실가격 입력에 대해 에이전트 간 반응이 어떻게 다른지, 즉 이질성(heterogeneity)과 상호작용 패턴에서 나와야 한다.** 이 점을 염두에 두고 분석 설계를 하면 비판은 충분히 방어 가능하다.

---

### Q2. INSTITUTIONAL이 단일가에 수량을 집어넣는 방식이 회계 항등식 아닌가? 가격을 분산시키는 게 나을까?

**질문 요지**

INSTITUTIONAL의 방향은 `sign(buy_vol - sell_vol)`으로 수학적으로 결정된다. 이는 기관투자자의 행동을 모델링한 것이 아니라 잔차를 처리하는 회계 항등식이다. 또한 하나의 가격(target_price)에 거대한 단일 주문을 집어넣는 방식이 현실적인지, 아니면 여러 가격 레벨에 분산시키는 것이 더 나은지 의문이다.

**설계자 반론**

INSTITUTIONAL이 회계 항등식의 성격을 갖는다는 것은 인정한다. 그러나 이 시스템에서 INSTITUTIONAL의 역할은 기관투자자 행동을 정밀 모사하는 것이 아니라 **에이전트 외부에 존재하는 시장 참여자 전체(기관, 외국인, 프로그램 매매 등)의 집합적 효과를 단순화한 균형 조정 장치**다. 가격 분산의 필요성에 대해서는: 집합경매에서 체결가는 항상 target_price로 고정되므로, INSTITUTIONAL 주문이 target_price에 있든 target_price - X에 있든 체결 결과는 동일하다. 가격을 분산시켜도 연구 결론에 실질적 차이가 없다. 오히려 중요한 것은 **방향(매수/매도)과 규모(금액)**이며, 이것은 에이전트 불균형에서 직접 도출되므로 실제 기관/외국인 매매 데이터의 방향·규모와 비교·검증하는 데 충분히 활용 가능하다.

**평가: 반론 타당함, 단 논문 표현에 주의 필요**

단일가 주입이 메커니즘적으로 옳다는 반론은 정확하다. 집합경매 구조상 가격 분산은 체결 결과에 영향을 주지 않는다. 검증 방법으로서 매수/매도 방향과 금액 규모를 실제 기관 데이터와 비교하는 접근도 타당하다. 단, 논문에서 INSTITUTIONAL을 "기관투자자 행동 모델"로 표현하면 비판받을 수 있다. **"에이전트 외부 시장 참여자들의 집합적 잔차 효과(aggregate residual effect)"** 로 정의하는 것이 방어 가능한 표현이다. 검증 시에도 방향 일치율과 금액 Correlation을 함께 보고하면 타당성이 높아진다.

---

### Q3. 에이전트의 가격 결정이 결과에 영향을 주지 않는다 — 가격 경쟁이 무력화되지 않는가?

**질문 요지**

Phase 2/3에서 에이전트가 어떤 가격을 제출하든 체결가는 target_price다. LLM이 정교하게 생성한 target_price가 실질적 결과에 아무 영향을 미치지 않는다면, 에이전트 설계의 상당 부분이 이 매칭 엔진에서 의미를 잃는다.

**설계자 반론**

실시간 Ask/Bid 호가창 방식으로 가격 경쟁을 구현하려면 LLM 호출을 순차적으로 실시간 처리해야 하며, 매 주문마다 호가창을 갱신하는 API 연동이 필요하다. 현재 구조(1000명을 병렬 배치 처리)에서는 기술적으로 불가능하다. 동시호가 시스템은 이 제약 안에서 선택할 수 있는 최선의 구조다.

**평가: 실용적 제약으로서 타당, 단 한계로 명시 필요**

제약 조건에 의한 선택이라는 점은 수용 가능하다. 그러나 이 한계는 논문의 limitation 섹션에 명시되어야 한다. 한편 에이전트가 제출한 가격 분포 자체(평균이 실가격 대비 높은지 낮은지, 분산 크기, 낙관/비관 분포)는 집합경매 체결가와 무관하게 **독립적인 분석 지표**로 활용할 수 있다. 즉 "에이전트들이 매수 시 얼마나 높은 가격을 써내는가"는 Belief의 낙관도를 측정하는 별도 지표가 될 수 있다. 이 점을 연구 설계에 반영하면 가격 경쟁 무력화의 약점을 부분적으로 보완할 수 있다.

---

### Q4. Phase 1에서 체결가와 종가 간 괴리가 에이전트 자산 계산을 왜곡하지 않는가?

**질문 요지**

Phase 1에서 에이전트가 10.5달러에 매수했는데 기록된 종가가 10.0달러(실가격)라면, 에이전트는 Day 1부터 미실현 손실 상태로 시뮬레이션에 진입한다. 이것이 이후 행동을 비정상적으로 왜곡할 수 있다.

**설계자 반론**

이 괴리는 의도된 결과다. 목적 자체가 에이전트들을 서로 다른 평단가, 즉 서로 다른 손익 상태에서 분석 기간으로 진입시키는 것이다. 어떤 에이전트는 이익, 어떤 에이전트는 손실 상태로 시작함으로써 실제 시장의 투자자 분포를 모사한다. 평단가가 모두 동일한 상태보다 훨씬 현실적인 초기 조건이다. 이 기간의 거래는 연구 분석에서 제외되므로 분석 결과에 직접적인 영향도 없다.

**평가: 반론 타당함, 설계 의도와 완전히 일치**

이 괴리는 설계 목적의 직접적 결과이므로 약점이 아니라 기능이다. 미실현 손익 상태의 다양성이 에이전트 행동 이질성의 초기 조건을 만들어주며, 이것이 warm-up 기간의 핵심 역할이다. 비판 철회가 맞다.
