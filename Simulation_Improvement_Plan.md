# Simulation Improvement Plan

작성일: 2026-06-25

이 문서는 다음 실험 전에 반영할 코드 수정 사항을 정리한다. 핵심 목표는 현재 시뮬레이션을 크게 갈아엎기보다, 기존 동작은 최대한 보존하면서 비교 가능한 실험 모드를 추가하고, 보고서와 검증 지표를 현재 연구 질문에 맞게 정리하는 것이다.

## 1. 실행 병렬화 개선

### 문제 인식

현재 실행 체감상 한 에이전트의 LLM 호출과 처리 흐름이 끝난 뒤 다음 에이전트가 진행되는 것처럼 느리게 보인다. 이미 `--concurrency` 옵션이 존재하지만, 실제 daily cycle 내부에서 다음 작업들이 충분히 병렬화되어 있는지 확인이 필요하다.

- 에이전트별 context 수집
- 뉴스 해석 LLM 호출
- belief 업데이트 LLM 호출
- decision LLM 호출
- 주문 제출 전후 로깅

### 수정 목표

같은 거래일 안에서 서로 독립적인 에이전트 작업은 가능한 한 병렬 실행한다.

### 확인할 코드 위치

- `scripts/05_run_simulation.py`
- `twinmarket_kr/simulation.py`
- `twinmarket_kr/core/daily_cycle.py`
- `twinmarket_kr/core/collect_context.py`
- `twinmarket_kr/llm/*`
- `twinmarket_kr/run_logger.py`

### 구현 방향

1. `concurrency`가 실제로 에이전트 단위 LLM pipeline에 적용되는지 확인한다.
2. 같은 날짜의 agent turn은 `asyncio.Semaphore(concurrency)` 기반으로 병렬 처리한다.
3. 병렬 처리 후 결과는 날짜별/agent_id별로 정렬해서 저장한다.
4. DB write나 CSV/JSONL logging처럼 공유 리소스에 쓰는 부분은 순차 처리하거나 lock을 둔다.
5. 병렬 실행으로 결과 순서가 흔들리더라도 보고서와 validation이 안정적으로 읽을 수 있게 `date`, `turn`, `agent_id` 기준 정렬을 보장한다.

### 주의 사항

- 병렬화 때문에 같은 날짜의 체결 전 포트폴리오 상태가 agent마다 다르게 읽히면 안 된다.
- D일 의사결정은 모든 agent가 D-1까지의 동일한 포트폴리오 snapshot을 기준으로 수행해야 한다.
- 주문 체결과 포트폴리오 업데이트는 모든 주문이 모인 뒤 exchange 단계에서 처리하는 것이 자연스럽다.

## 2. Market 주문 제거 및 전량 지정가화

### 문제 인식

현재 decision에서 `order_type=market` 주문이 생성될 수 있다. 하지만 현재 exchange 구조는 실제 호가창/동시호가 시스템을 정밀하게 구현한 것이 아니라 실제 가격에 앵커링해서 체결시키는 방식이다. 이 상태에서 시장가 주문을 허용하면 다음 문제가 생긴다.

- 동시호가 실험이라는 설명과 주문 타입이 어긋난다.
- 시장가 주문이 실제 D일 가격에 너무 쉽게 체결되어 체결 논리가 느슨해진다.
- buy/sell 방향 실험에서 수량과 가격 조건의 의미가 약해진다.

### 수정 목표

시뮬레이션 주문은 모두 지정가 주문으로 통일한다.

### 확인할 코드 위치

- `prompts/make_decision.txt`
- `twinmarket_kr/llm/decision.py`
- `twinmarket_kr/agents/exchange_agent.py`
- `scripts/generate_run_report_pdf.py`

### 구현 방향

1. decision prompt에서 `order_type`은 `"limit"`만 허용하도록 수정한다.
2. LLM이 `market`을 반환해도 parser에서 `limit`으로 강제 변환한다.
3. 가격이 0이거나 비정상인 경우 fallback 지정가를 설정한다.
4. fallback 기준은 실험 모드별로 명확히 둔다.
   - 기본 모드: 사용 가능한 기준 가격 근처
   - D-1 정보 모드: D-1 종가 또는 D일 reference price
5. 보고서에는 주문가와 체결가를 분리해서 표시한다.

### 정책 후보

지정가 fallback은 다음 중 하나를 선택한다.

- 보수안: `price <= 0`이면 주문 invalid 처리 후 hold
- 실험안: `price <= 0`이면 reference price로 limit 주문 변환
- 추천안: parser 단계에서는 reference price로 보정하되, 보정 여부를 로그에 남긴다.

추천안이 가장 실험 유지에 유리하다. LLM 출력 실수 때문에 주문이 과도하게 사라지는 문제를 줄일 수 있고, 동시에 market 주문은 제거할 수 있다.

## 3. Lookahead 방지 실험 모드 추가

### 현재 구조 평가

현재 반영 구조는 다음과 같다.

```text
decision_date = D
market_features_date = D
news_date = D
portfolio_state = D-1
execution_date = D
validation_date = D
```

즉 D일 뉴스와 D일 종가/기술지표를 보고 D일 주문을 만들고, D일 실제 가격에 앵커링해서 체결한 뒤, D일 실제 개인 순매매와 비교한다.

날짜 키 자체가 하루씩 밀린 off-by-one 버그로 보이지는 않는다. 포트폴리오는 turn-1 기준으로 읽고, 주문/체결/validation 날짜도 같은 date 키로 일관된다. 문제는 날짜 매칭이 아니라 정보 사용 시점이다.

### 핵심 문제

`FundamentalAgent.get_market_features(date)`가 D일의 다음 정보를 그대로 제공한다.

- D일 종가
- D일 등락률
- D일 거래량 변화
- D일 MA5/MA20
- D일 변동성

이 정보는 장 마감 후에야 확정된다. 그런데 현재 구조에서는 이 정보를 보고 D일 주문을 낸다. 이는 예측 실험이라기보다 사후 정보를 가진 당일 반응 실험에 가깝다.

뉴스도 유사한 문제가 있다.

- `NewsAgent.build_base_context(date)`는 D일 뉴스를 포함한다.
- 뉴스 timestamp가 장 전/장 후로 구분되지 않으면 D일 장 마감 이후 뉴스도 D일 의사결정에 들어갈 수 있다.
- depth 2 검색도 current_date까지 포함하므로 D일 이후 정보 사용 가능성을 점검해야 한다.

### 수정 목표

기존 모드는 보존하고, 다음의 새 실험 모드를 추가한다.

```text
decision_date = D
market_features_date = D-1
news_max_date = D-1 또는 D일 장 전 뉴스만
execution_date = D
validation_date = D
```

이 모드는 “D일 매매를 위해 전일까지 확실히 알 수 있는 정보만 사용한다”는 구조다. 현재 validation보다 연구 설계상 방어 가능하다.

### 모드 이름 후보

- `--information-mode prior_close`
- `--no-lookahead`
- `--decision-info-lag 1`

추천은 `--information-mode prior_close`다. 향후 다른 모드를 추가하기 쉽다.

```text
--information-mode same_day
--information-mode prior_close
--information-mode close_to_next_day
```

### 모드별 의미

#### same_day

현재 구조와 동일하다.

```text
decision_date = D
market_features_date = D
news_max_date = D
execution_date = D
```

기존 실험과의 호환성을 위해 유지한다.

#### prior_close

새로 추가할 핵심 비교 모드다.

```text
decision_date = D
market_features_date = D-1
news_max_date = D-1
execution_date = D
```

뉴스 timestamp가 장 전/장 후로 안정적으로 분리되어 있지 않다면 우선은 D-1 뉴스까지만 사용하는 것이 안전하다.

#### close_to_next_day

추후 확장 후보.

```text
decision_date = D
market_features_date = D
news_max_date = D
execution_date = D+1
validation_date = D+1
```

D일 정보를 모두 사용하고 싶다면 주문과 validation을 D+1로 넘기는 방식이 더 자연스럽다.

### 확인할 코드 위치

- `twinmarket_kr/simulation.py`
- `twinmarket_kr/core/daily_cycle.py`
- `twinmarket_kr/core/collect_context.py`
- `twinmarket_kr/agents/fundamental_agent.py`
- `twinmarket_kr/agents/news_agent.py`
- `twinmarket_kr/agents/exchange_agent.py`
- `validation/validate_trading_direction.py`

### 구현 방향

1. CLI에 `--information-mode` 옵션을 추가한다.
2. 날짜별 loop에서 `decision_date`, `market_features_date`, `news_max_date`, `execution_date`를 분리한다.
3. `collect_context`가 market/news 기준일을 별도로 받을 수 있게 수정한다.
4. `FundamentalAgent.get_market_features()`는 기존처럼 특정 날짜를 받되, 호출부에서 D-1을 넘긴다.
5. `NewsAgent`는 `news_max_date` 이하 뉴스만 읽도록 옵션을 받는다.
6. 로그에는 반드시 아래 값을 남긴다.

```text
decision_date
market_features_date
news_max_date
execution_date
information_mode
```

### 보고서 반영

보고서 실행 개요에 정보 기준일을 표시한다.

```text
information_mode = prior_close
decision_date = 2025-02-14
market_features_date = 2025-02-13
news_max_date = 2025-02-13
execution_date = 2025-02-14
```

날짜 구조가 보고서에 남아야 이후 validation 결과 해석이 가능하다.

## 4. 검증 지표 개편: sign 기반 primary metric

### 현재 판단

현재 실험 목적에서는 correlation보다 sign 기반 검증이 1차 지표로 더 합리적이다.

이유는 LLM이 실제로 예측해야 하는 것이 “개인투자자가 순매수할지 순매도할지”에 가깝기 때문이다. 특히 buy/sell-only 실험은 decision space 자체가 방향 선택에 가까우므로, 평가도 먼저 방향이 맞았는지를 보는 것이 자연스럽다.

### 문제점

단순 direction match만 보면 안 된다.

예를 들어 첫 3일 제외 후 실제 방향이 다음과 같다면:

```text
actual buy days = 7
actual sell days = 5
```

매일 buy만 찍어도 7/12 = 58.3%가 나온다. 따라서 단순 일치율은 naive baseline과 반드시 비교해야 한다.

### Primary metrics

검증 리포트의 1차 지표는 다음으로 둔다.

```text
direction_match_rate
balanced_accuracy
buy_recall
sell_recall
sell_day_recall
confusion_matrix
```

정의:

```text
direction_match_rate = sign(LLM net) == sign(Individuals net)

buy_recall = 실제 순매수일 중 LLM도 순매수한 비율

sell_recall = 실제 순매도일 중 LLM도 순매도한 비율

balanced_accuracy = (buy_recall + sell_recall) / 2
```

flat이 있는 경우 정책을 명확히 한다.

- 기본: flat도 하나의 방향으로 취급하여 mismatch 가능
- 보조: nonzero-only match도 함께 제공

### Baseline metrics

반드시 다음 baseline과 비교한다.

```text
always-buy
always-sell
random 50:50
actual-ratio random
previous-day individual direction
previous-day market return direction
```

각 baseline은 동일한 날짜 구간과 동일한 skip rule을 사용해야 한다.

기본 분석 기준:

```text
skip_initial_days = 3
```

앞으로 두 실험 이상을 비교할 때도 처음 3거래일은 제외한 지표를 기본으로 한다.

### Secondary metrics

Correlation은 버리지 않고 2차 지표로 유지한다.

```text
raw pearson correlation
max-abs normalized correlation
z-score normalized correlation
cumulative correlation
cosine similarity
net exposure bias
turnover / order volume
```

해석:

- sign metric은 방향 선택 성능을 본다.
- correlation은 방향을 넘어 강도 패턴까지 실제와 같이 움직이는지 본다.
- correlation이 음수인데 sign match가 높다면, 방향은 일부 맞지만 강도 배분이 실제와 다를 수 있다.

### 보고서/validation 출력 개편

validation report는 다음 순서로 표시한다.

1. 분석 기간 및 skip된 날짜
2. LLM vs Individuals sign metrics
3. baseline 비교 표
4. confusion matrix
5. daily direction table
6. secondary correlation metrics
7. raw/normalized chart

## 5. 실험 비교 설계

가장 깔끔한 다음 실험은 기존 코드를 크게 바꾸는 것이 아니라 모드를 추가해서 비교하는 것이다.

### 비교 축

1. 정보 사용 시점

```text
same_day
prior_close
```

2. decision space

```text
buy/hold/sell
buy/sell-only
```

3. 주문 타입

```text
기존 market 허용
limit-only
```

단, 주문 타입은 앞으로 limit-only를 기본으로 두는 것이 더 자연스럽다.

### 우선순위

1. 코드 안정성 확보
   - 삭제된 persona 거래빈도/회전율 컬럼 참조 제거 유지
   - report 생성 정상 작동
   - simulation 실행 정상 작동

2. limit-only 주문 모드 반영

3. `information_mode=prior_close` 추가

4. validation sign metrics 및 baseline 추가

5. 병렬 실행 확인 및 병목 제거

## 6. 예상되는 파일별 수정 목록

### 시뮬레이션 실행

- `scripts/05_run_simulation.py`
  - `--information-mode` 옵션 추가
  - 필요 시 `--limit-only` 옵션 추가 또는 기본값 limit-only로 전환

- `twinmarket_kr/simulation.py`
  - 날짜 loop에서 decision/execution/information 기준일 분리
  - metadata에 information mode 저장

- `twinmarket_kr/core/daily_cycle.py`
  - agent turn 병렬화 확인 및 개선
  - context 기준일과 execution 기준일 분리

- `twinmarket_kr/core/collect_context.py`
  - market_features_date, news_max_date 인자 추가

### 데이터 에이전트

- `twinmarket_kr/agents/fundamental_agent.py`
  - D-1 날짜 feature 조회가 안정적으로 되도록 helper 추가 가능
  - 첫 거래일 이전 feature가 없을 때 처리 정책 필요

- `twinmarket_kr/agents/news_agent.py`
  - `news_max_date` 이하 뉴스만 가져오는 필터 추가
  - 장 전 뉴스 구분이 없다면 D-1까지 사용하는 mode 우선 구현

### 의사결정

- `prompts/make_decision.txt`
  - order_type은 limit만 허용
  - 시장가 주문 금지 문구 추가
  - 가격을 반드시 명시하도록 요구

- `twinmarket_kr/llm/decision.py`
  - market 반환 시 limit으로 보정
  - price fallback 로직 추가
  - 보정 여부 로그 필드 추가 검토

### 체결

- `twinmarket_kr/agents/exchange_agent.py`
  - limit-only 주문 가정으로 체결 로직 정리
  - 시장가 주문 특수 처리 제거 또는 비활성화

### 검증

- `validation/validate_trading_direction.py`
  - sign primary metrics 추가
  - balanced accuracy 추가
  - baseline 비교 추가
  - first 3 trading days skip을 기본 분석 기준으로 유지
  - correlation은 secondary로 재배치

### 보고서

- `scripts/generate_run_report_pdf.py`
  - 주문장 표시 유지
  - information mode/date 기준 표시 추가
  - limit 보정 주문 표시 가능하면 추가

## 7. 검증 체크리스트

코드 수정 후 반드시 확인할 것:

```text
1. 현재 sys_100.db 로딩 가능
2. persona prompt에 거래빈도/회전율 문구 없음
3. simulation 1~2일 smoke test 통과
4. submitted_orders.csv에 market 주문 없음
5. report PDF 생성 통과
6. report에 날짜별 주문장 표시
7. validation report 생성 통과
8. sign metric과 baseline 출력
9. skip_initial_days=3이 기본 분석에 반영
10. information_mode가 metadata/report/validation에 남음
```

## 8. 해석 기준

다음 실험 결과를 해석할 때는 아래 기준을 사용한다.

좋은 결과로 보기 위한 최소 조건:

```text
direction_match_rate > always-buy baseline
balanced_accuracy > 0.5
sell_recall이 의미 있게 개선
correlation이 강한 음수에서 완화
기간 확장 시에도 지표가 유지
```

주의할 점:

- 12거래일 수준의 작은 표본에서는 58% 전후 일치율을 강한 성능으로 해석하면 안 된다.
- actual buy/sell 분포가 치우쳐 있으면 단순 direction match는 과대평가될 수 있다.
- corr이 낮거나 음수여도 방향 실험 자체가 실패라고 단정할 수는 없다.
- 반대로 direction match가 좋아도 baseline을 못 이기면 예측력이라고 보기 어렵다.

## 9. 결론

이번 수정의 핵심은 세 가지다.

1. 실행은 더 병렬적으로 만들어 실험 시간을 줄인다.
2. 주문은 limit-only로 맞춰 동시호가/호가창형 해석과 일관되게 만든다.
3. 정보 사용 시점을 명확히 분리한 `prior_close` 모드를 추가해 lookahead 가능성을 줄인다.

검증은 sign 기반 지표를 1차로 두되, naive baseline을 반드시 같이 제시한다. correlation은 방향을 넘어 거래 강도까지 설명하는지 확인하는 2차 지표로 유지한다.
