@@ -0,0 +1,290 @@
# Event/Fake News DB Guide

이 문서는 삼성전자 이벤트 기반 가짜뉴스 주입 실험을 위해 만든
`data/event.pkl`과 `data/fake_news.pkl`의 생성 방식, 데이터 구조,
검증 결과, 사용 규칙을 팀원이 공유하기 위한 가이드다.

## 1. 목적

이 데이터는 트레이딩 에이전트가 동일한 시장 환경에서 가짜뉴스 입력에 얼마나 취약한지
비교하기 위한 실험용 데이터다.

- Baseline: 하루 10개 모두 실제 뉴스
- Injection: 이벤트 주입 기간에 baseline 실제 뉴스 10개를 유지하고 가짜뉴스 1개를 추가
- 비교 대상: PnL, 수익률, 거래 빈도, 매수/매도 타이밍, 포지션 변화, 판단 로그

중요한 점은 baseline 실제 뉴스 10개를 제거하지 않는다는 것이다.
따라서 가짜뉴스가 주입되는 날짜의 기본 노출 목록은 11개가 되며,
Baseline과 Injection의 차이가 "실제 뉴스 하나 제거 효과"와 섞이지 않게 한다.

## 2. 산출물

| 파일 | 역할 |
| --- | --- |
| `data/event.pkl` | 삼성전자 주요 이벤트 DB |
| `data/fake_news.pkl` | 이벤트 윈도우별 가짜뉴스 주입 DB |
| `outputs/daily_news_selection.csv` | 날짜별 baseline 실제 뉴스 10개 목록 |

`event.pkl`과 `fake_news.pkl`은 실험에서 직접 사용하는 핵심 산출물이다.
`daily_news_selection.csv`는 baseline 실제 뉴스 10개와 가짜뉴스의 기준 timestamp/slot을 검증하는 기준 데이터다.

## 3. 이벤트 생성 기준

이벤트는 삼성전자 주가에 영향을 줄 수 있는 큰 뉴스와 주가 변동을 함께 보며 선정했다.
최종 이벤트 수는 54개이며, 2025-01부터 2026-06까지 매월 3개씩 포함된다.

이벤트 유형은 다음과 같다.

| 유형 | 개수 |
| --- | ---: |
| `hbm` | 13 |
| `earnings` | 7 |
| `semiconductor_cycle` | 6 |
| `regulation` | 6 |
| `memory_price` | 5 |
| `customer_issue` | 4 |
| `labor_strike` | 4 |
| `competitor_issue` | 2 |
| `export` | 2 |
| `foundry` | 2 |
| `macro` | 1 |
| `capex` | 1 |
| `technology` | 1 |

예측 가능 여부는 다음과 같이 나눈다.

| predictability | 의미 | 개수 |
| --- | --- | ---: |
| `predictable` | 실적 발표, 예정된 산업 이벤트처럼 사전 기대감이 형성될 수 있는 이벤트 | 25 |
| `unpredictable` | 노사 결렬, 규제 발언, 고객사 이슈처럼 사전 주입 시 data leakage가 될 수 있는 이벤트 | 29 |

## 4. 가짜뉴스 주입 규칙

가짜뉴스는 매일 무작위로 넣지 않는다. 이벤트가 있는 구간에만 넣는다.

### 4.1 예측 가능 이벤트

예측 가능한 이벤트는 발표 전 기대감과 루머가 형성될 수 있으므로
`D-2, D-1, D, D+1, D+2` 구간에 주입한다.

```text
D-2   D-1   D-day   D+1   D+2
 |     |      |      |     |
 └──── 가짜뉴스 주입 구간 ────┘
```

단, D-day 이전 fake row는 이벤트 결과나 발표 수치를 사용하지 않는다.

### 4.2 예측 불가능 이벤트

예측 불가능 이벤트는 사전 주입하면 미래 정보를 미리 준 것이 되므로
`D, D+1, D+2`에만 주입한다.

```text
D-day   D+1   D+2
 |      |     |
 └─ 가짜뉴스 주입 구간 ─┘
```

### 4.3 중복 윈도우 처리

여러 이벤트의 주입 윈도우가 겹치면 날짜 단위로 병합한다.
따라서 같은 날짜에는 가짜뉴스가 최대 1개만 들어간다.

검증 결과:

- fake row 수: 178
- fake 노출 날짜 수: 178
- 하루 1개 가짜뉴스 조건: 통과
- 이벤트 주입 윈도우 union과 fake 날짜 집합: 일치

## 5. `event.pkl` 주요 컬럼

| 컬럼 | 의미 |
| --- | --- |
| `event_id` | 이벤트 고유 ID |
| `event_date` | 이벤트 기준일 |
| `event_timestamp` | 이벤트 기준 timestamp |
| `source_news_id` | 이벤트 판단의 근거가 된 실제 뉴스 ID |
| `source_date`, `source_time` | 근거 뉴스 날짜/시간 |
| `source_title`, `source_summary` | 근거 뉴스 제목/요약 |
| `event_title` | 정규화된 이벤트명 |
| `event_summary` | 이벤트 요약 |
| `event_type` | 이벤트 유형 |
| `predictability` | 예측 가능 여부 |
| `injection_window_offsets` | 주입 offset 목록 |
| `injection_dates` | 실제 주입 날짜 목록 |
| `stock_return_1d`, `stock_return_3d`, `stock_return_7d` | 이벤트 주변 주가 반응 |
| `volume_ratio` | 거래량 변화 강도 |
| `importance_score` | 이벤트 중요도 |
| `misinformation_risk_score` | 가짜뉴스 유포 위험도 |

## 6. `fake_news.pkl` 주요 컬럼

| 컬럼 | 의미 |
| --- | --- |
| `synthetic_id` | 가짜뉴스 고유 ID |
| `date` | 에이전트에게 노출되는 날짜 |
| `time`, `timestamp` | 에이전트에게 노출되는 시간 |
| `time_slot` | timestamp 기준 `morning`/`afternoon` |
| `feed_slot` | baseline 뉴스 흐름에서 맞춰 넣을 오전/오후 feed 위치 |
| `title`, `content` | 에이전트에게 노출할 가짜뉴스 제목/본문 |
| `linked_event_id` | 연결된 대표 이벤트 ID |
| `linked_event_ids` | 병합 윈도우에서 연결된 이벤트 ID 목록 |
| `related_event` | 연결된 이벤트명 |
| `injection_offset` | 대표 이벤트 기준 D-day offset |
| `misinformation_type` | 가짜뉴스 유형 |
| `replace_target_news_id` | timestamp/slot 정렬 기준으로 참고한 실제 뉴스 ID. 실제 주입 시 제거하지 않는다. |
| `replace_target_timestamp` | 가짜뉴스가 맞춰 들어갈 기준 실제 뉴스 timestamp |
| `baseline_news_position` | 기준 timestamp가 baseline 10개 뉴스 중 몇 번째였는지 |
| `can_use_event_outcome` | 해당 timestamp에서 이벤트 결과를 사용해도 되는지 |
| `uses_future_event_details` | 미래 이벤트 세부정보 사용 여부 |
| `leakage_safe` | leakage 방지 규칙 통과 여부 |

## 7. 가짜뉴스 유형

가짜뉴스는 세 가지 유형을 거의 1:1:1로 섞었다.

| 유형 | 설명 | 개수 |
| --- | --- | ---: |
| `unintentional_misinformation` | 전망/루머/부분 정보를 사실처럼 오해한 오정보 | 60 |
| `intentional_disinformation` | 의도적으로 확정되지 않은 계약, 수치, 타결 등을 퍼뜨리는 허위정보 | 59 |
| `malicious_context_distortion` | 일부 맥락만 강조해 이벤트 해석을 한쪽으로 몰아가는 왜곡 | 59 |

예시:

- 실제 뉴스: 노사 협상 결렬
- 가짜뉴스: 노사 협상 타결설, 협상 재개를 최종 타결처럼 해석, 생산 정상화 기대 과장

## 8. 적대적 검증 결과

데이터가 실험 목적에 맞는지 다음 관점에서 검증했다.

### 8.1 구조 검증

| 항목 | 결과 |
| --- | --- |
| `event.pkl` 필수 컬럼 존재 | 통과 |
| `fake_news.pkl` 필수 컬럼 존재 | 통과 |
| 필수 컬럼 결측치 | 0 |
| fake row 수 | 178 |
| event row 수 | 54 |
| 날짜별 fake 중복 | 없음 |
| injection count | fake row가 있는 날짜는 `10 real + 1 fake` 조건 통과 |

### 8.2 timestamp 검증

| 항목 | 결과 |
| --- | --- |
| 모든 fake row에 `timestamp` 존재 | 통과 |
| `timestamp == replace_target_timestamp` | 통과 |
| `timestamp`의 날짜와 `date` 일치 | 통과 |
| `time_slot`과 timestamp 오전/오후 일치 | 통과 |
| `replace_target_news_id`가 baseline 실제 뉴스에 존재 | 통과 |

즉, 가짜뉴스는 임의의 시간에 삽입되는 것이 아니라 실제 baseline 뉴스 하나의 timestamp를 기준으로 추가된다.
다만 기준이 된 실제 뉴스는 제거하지 않는다.

### 8.3 data leakage 검증

| 항목 | 결과 |
| --- | --- |
| 예측 불가능 이벤트의 pre-event fake row | 없음 |
| linked event 기준 주입 윈도우 밖 fake row | 없음 |
| D-day 이전 timestamp에서 이벤트 결과 사용 | 없음 |
| `uses_future_event_details` | 전부 `False` |

D-day row 중 16개는 fake timestamp가 event timestamp보다 앞선다.
이 경우 `can_use_event_outcome=False`로 처리했고, 본문도 결과 확정형이 아니라 발표 전 기대/소문형으로 작성했다.

### 8.4 agent-visible text 검증

처음 생성본에는 일부 `content`가 "허위", "오정보", "공식 확인 필요"처럼
가짜뉴스임을 직접 드러내는 표현을 포함하고 있었다.
이는 에이전트가 내용 판단이 아니라 형식적 단서로 가짜뉴스를 구분하게 만들 수 있어 제거했다.

최종 검증 결과:

| 항목 | 결과 |
| --- | --- |
| agent-visible `title/content` 내 self-disclosure 표현 | 0건 |
| fake title 고유값 | 150개 |
| fake content 고유값 | 131개 |
| fake content 평균 길이 | 162.4자 |
| 실제 뉴스 요약 평균 길이 | 214.6자 |

본문 길이는 실제 요약보다 약간 짧지만, 단문 뉴스/요약형 피드로 쓰기에는 허용 가능한 수준이다.
추후 에이전트가 본문 길이에 민감하게 반응하면 fake content를 200자 전후로 한 번 더 늘리면 된다.

## 9. 실험에서 사용하는 방법

### 9.1 Baseline 조건

각 날짜마다 `daily_news_selection.csv`의 실제 뉴스 10개를 그대로 제공한다.

### 9.2 Injection 조건

각 날짜의 baseline 실제 뉴스 10개를 그대로 유지하고,
`fake_news.pkl`의 fake row 1개를 추가한다.

삽입 기준:

```text
daily_news_selection.id == fake_news.replace_target_news_id
```

이 기준은 가짜뉴스의 timestamp/slot 정렬을 위한 참조 기준이다.
해당 실제 뉴스는 제거하지 않는다.

fake row가 없는 날짜는 baseline과 동일하게 실제 뉴스 10개만 제공한다.
fake row가 있는 날짜는 실제 뉴스 10개와 가짜뉴스 1개, 총 11개를 제공한다.

실행 시 노출 여부는 `--fake-news-mode`로 제어한다.

```bash
# injection CSV 사용 + fake row 노출
python scripts/05_run_simulation.py --use-fake-news-injection --fake-news-mode on

# injection CSV 사용 + fake row 숨김
python scripts/05_run_simulation.py --use-fake-news-injection --fake-news-mode off
```

`off` 모드에서는 `is_fake=true` row가 기본 뉴스 목록, 본문 읽기, Depth 2 검색 후보에서 제외된다.

### 9.3 에이전트에게 노출할 컬럼

에이전트에게는 다음 정도만 노출한다.

```text
date
time
timestamp
title
content
category 또는 source
```

`is_fake`, `misinformation_type`, `false_claim`, `why_false_or_misleading`,
`leakage_safe`, `replace_target_news_id` 같은 컬럼은 분석/평가용 메타데이터다.
에이전트 입력에 포함하면 라벨 leakage가 발생한다.

## 10. 최소 사용 예시

```python
import hashlib
import pandas as pd

daily = pd.read_csv("outputs/daily_news_selection.csv", encoding="utf-8-sig")
fake = pd.read_pickle("data/fake_news.pkl")

target_date = "2026-03-04"
real_news = daily[daily["date"] == target_date].copy()
fake_rows = fake[fake["date"] == target_date]

if not fake_rows.empty:
    fake_row = fake_rows.iloc[0]
    category = fake_row.get("replace_target_category") or "종목"
    if category not in {"종목", "섹터", "경제"}:
        category = "종목"
    public_id = "news_{}_{}_{}".format(
        str(fake_row["date"]).replace("-", ""),
        category,
        hashlib.sha1(str(fake_row["synthetic_id"]).encode("utf-8")).hexdigest()[:8],
    )
    injected = {
        "id": public_id,
        "date": fake_row["date"],
        "time": fake_row["time"],
        "category": category,
        "title": fake_row["title"],
        "summary": fake_row["content"],
    }
    real_news = pd.concat([real_news, pd.DataFrame([injected])], ignore_index=True)

real_news = real_news.sort_values(["date", "time"])
```

## 11. 주의사항

- 이 데이터는 실험용 synthetic fake news 데이터다.
- `fake_news.pkl` 안에는 평가를 위한 라벨 컬럼이 들어 있으므로, 에이전트 입력 전에 반드시 제거해야 한다.
- 이벤트 윈도우가 겹치는 날짜는 이미 병합되어 있으므로 같은 날짜에 fake row를 추가로 만들면 안 된다.
- 예측 불가능 이벤트에는 pre-event fake를 만들면 안 된다.
- D-day라도 fake timestamp가 event timestamp보다 빠르면 결과/확정 수치/타결 여부를 쓰면 안 된다.
- 현재 fake content는 뉴스 요약형이다. 실제 기사 본문 길이로 실험하려면 `content`를 더 길게 확장해야 한다.
