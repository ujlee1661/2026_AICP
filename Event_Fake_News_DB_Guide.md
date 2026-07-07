# Event/Fake News DB Guide

이 문서는 삼성전자 이벤트 기반 가짜뉴스 주입 실험을 위해 만든 데이터의 생성 기준, 파일 역할, 사용 방법을 팀원이 공유하기 위한 가이드다.

## 1. 실험 목적

목표는 동일한 시장 환경에서 가짜뉴스 입력이 트레이딩 에이전트의 의사결정과 성과에 어떤 영향을 주는지 비교하는 것이다.

- Baseline: 기존 뉴스 피드만 제공
- Injection: 이벤트 윈도우에 한해 기존 10개 뉴스 중 1개를 fake news로 치환
- 비교 지표: PnL, 수익률, 매수/매도 타이밍, 거래 빈도, 포지션 변화, 판단 로그

중요한 점은 fake news mode를 켜도 하루 뉴스 개수를 늘리지 않는다는 것이다. Agent가 받는 정보량은 유지하고, 정보의 질만 오염시키기 위해 `daily_news_selection_injection.csv`에서 기존 row 1개를 fake row 1개로 교체한다.

## 2. 파일 역할

| 파일 | 역할 |
| --- | --- |
| `data/samsung_news_raw.pkl` | 크롤링된 전체 삼성전자 관련 뉴스 원천 데이터 |
| `outputs/processed_news.csv` | raw 전체 뉴스에서 정제한 baseline 검색/본문용 뉴스 DB |
| `outputs/daily_news_selection.csv` | 날짜별 agent 기본 노출용 baseline 뉴스 피드 |
| `data/event.pkl` | raw 전체 뉴스와 주가 변동을 함께 보고 선정한 이벤트 DB |
| `data/fake_new.pkl` | 이벤트별 fake news 원본 및 평가용 메타데이터 |
| `outputs/processed_news_injection.csv` | baseline processed 뉴스 + searchable fake 전문 |
| `outputs/daily_news_selection_injection.csv` | baseline daily feed에서 target 1개를 fake 1개로 치환한 피드 |
| `outputs/fake_news_injection_manifest.json` | injection 생성 요약 및 검증용 manifest |

`event.pkl`과 `fake_new.pkl`은 원천 산출물이고, 실제 simulation runtime은 `--fake-news-mode on`일 때 injection CSV들을 사용한다.

## 3. 원천 뉴스와 Daily Feed의 차이

`data/samsung_news_raw.pkl`은 전체 크롤링 뉴스다. 이벤트 선정은 이 전체 raw DB를 기준으로 한다. `outputs/daily_news_selection.csv`는 전체 뉴스 중 agent가 매일 받는 기본 feed를 구성한 결과물이며, 이벤트 선정 source of truth가 아니다.

이번 재생성에서는 `data/samsung_news_raw.pkl`에서 삼성전자 직접성, 반도체 관련성, 사건성, 주가/거래량 반응을 함께 보고 이벤트를 선정했다. 이후 fake news가 실제 agent feed에 들어갈 수 있도록 `daily_news_selection.csv`의 특정 row를 `replace_target_news_id`로 지정해 치환했다.

## 4. 이벤트 선정 기준

최종 `event.pkl`은 2025-01부터 2026-06까지 64개 이벤트로 구성된다. 월별 이벤트 수는 고정 3개가 아니라 2~4개 범위를 목표로 했고, 최종적으로 각 월 3~4개가 선정됐다.

이벤트 선정 축은 다음과 같다.

| 축 | 기준 |
| --- | --- |
| 뉴스 relevance | 삼성전자 직접 언급, 반도체/HBM/파운드리/메모리 관련성, 사건성 |
| market impact | 당일/3일/7일 수익률, 거래량 변화 |
| novelty | 같은 달 유사 이벤트 중복 제거 |
| source quality | raw row의 날짜, 시간, 제목, 본문, URL 추적 가능성 |

주요 분포는 다음과 같다.

| 항목 | 분포 |
| --- | --- |
| event count | 64 |
| predictable | 29 |
| unpredictable | 35 |
| risk score 5 | 59 |
| risk score 4 | 5 |

주요 event type은 `hbm`, `labor_strike`, `earnings`, `memory_price`, `foundry`, `capex`, `semiconductor_cycle`, `regulation`, `technology`, `competitor_issue`다.

## 5. Fake News 생성 기준

Fake news는 이벤트와 실제 뉴스 맥락에 맞게 만들었다. 예를 들어 실제 뉴스가 노사 협상 결렬이면 fake news는 타결설, 생산 정상화 관측, 협상 재개를 최종 합의처럼 보이게 하는 식으로 대응시켰다.

세 가지 misinformation type을 거의 1:1:1로 섞었다.

| 유형 | 의미 | 개수 |
| --- | --- | ---: |
| `unintentional_misinformation` | 전망/루머/부분 정보를 사실처럼 오해한 오정보 | 64 |
| `deliberate_disinformation` | 확정되지 않은 계약, 승인, 타결, 수치를 의도적으로 확정처럼 쓰는 허위정보 | 63 |
| `malicious_context_distortion` | 일부 맥락만 강조해 이벤트 해석을 한쪽으로 몰아가는 왜곡 | 63 |

`misinformation_risk_score`는 실측 확률이 아니라 실험용 정성 점수다.

| 점수 | 기준 |
| --- | --- |
| 5 | 실적 수치, 노사 타결/결렬, HBM 승인, 대형 계약처럼 루머화가 쉬운 이벤트 |
| 4 | 규제, 관세, 경쟁사, 업황 급변처럼 시장 민감도가 높은 이벤트 |
| 3 이하 | 최종 event DB에서 제외 |

## 6. Injection Window와 Data Leakage 방지

예측 가능한 이벤트는 발표 전 기대와 루머가 형성될 수 있으므로 `D-2~D+2`에 주입한다.

```text
D-2   D-1   D-day   D+1   D+2
 |     |      |      |     |
 └──── fake news injection window ────┘
```

예측 불가능 이벤트는 사전 주입하면 미래 정보를 미리 주는 leakage가 되므로 `D~D+2`에만 주입한다.

```text
D-day   D+1   D+2
 |      |     |
 └─ fake news injection window ─┘
```

검증 결과:

| 항목 | 결과 |
| --- | --- |
| fake row 수 | 190 |
| fake 노출 날짜 수 | 190 |
| 예측 불가능 이벤트의 pre-event fake | 0 |
| D-day 이전/이전 timestamp에서 이벤트 결과 사용 | 0 |
| `can_use_event_outcome=False` pre-event row | 41 |

## 7. 10개 중 1개 Fake 치환 방식

`fake_new.pkl`에는 각 fake row마다 `replace_target_news_id`가 있다. 이 값은 baseline daily feed에서 실제로 교체될 row의 id다.

Injection CSV 생성 방식:

1. `outputs/daily_news_selection.csv`를 읽는다.
2. `fake_new.pkl.replace_target_news_id`와 일치하는 baseline row를 찾는다.
3. 해당 row를 fake row로 치환한다.
4. 전체 daily row 수는 baseline과 동일하게 유지한다.
5. fake row가 없는 날짜는 baseline과 동일하게 유지한다.

최종 검증 결과:

| 항목 | 결과 |
| --- | --- |
| baseline daily row 수 | 3,835 |
| injection daily row 수 | 3,835 |
| daily fake row 수 | 190 |
| target real row가 injection daily에 남아 있는 경우 | 0 |
| fake row의 processed row 존재 여부 | 전부 존재 |

## 8. Depth 1과 Depth 2 노출 구조

Depth 1 agent는 `daily_news_selection_injection.csv`의 title feed를 먼저 본다. 이 파일에는 상세 본문이 없고, 실제 agent-visible 라벨도 없다.

Depth 1에서 본문을 읽거나 Depth 2 agent가 검색을 수행하면 `processed_news_injection.csv`를 사용한다.

- `summary`: daily read용 짧은 fake news 요약
- `search_summary`: Depth 2 검색에서 반환되는 긴 fake news 전문

검증 결과:

| 항목 | 결과 |
| --- | --- |
| fake short summary 평균 길이 | 191.7자 |
| fake search summary 평균 길이 | 900.8자 |
| agent-visible title/summary/search_summary 내 self-disclosure 표현 | 0건 |
| morning/afternoon window별 fake 최대 개수 | 1개 |
| Depth 2 검색에서 fake 전문 반환 | 통과 |

`is_fake`, `misinformation_type`, `false_claim`, `correct_fact`, `why_false_or_misleading`, `replace_target_news_id` 같은 컬럼은 분석/평가용 메타데이터다. Agent에게 공개되는 public output에는 이 라벨을 노출하지 않는다.

## 9. 실행 방법

원격 브랜치 기준 simulation은 `--fake-news-mode`로 baseline/injection을 제어한다.

```bash
# baseline: 기존 processed/daily CSV 사용, fake row 없음
python scripts/05_run_simulation.py --fake-news-mode off

# injection: processed_news_injection.csv / daily_news_selection_injection.csv 사용
python scripts/05_run_simulation.py --fake-news-mode on
```

`--fake-news-mode on`이면 config의 injection CSV 경로가 사용되고, `NewsAgent(include_fake_news=True)`로 실행된다. `--fake-news-mode off`이면 baseline CSV가 사용된다.

기간을 30일 단위로 바꿔 실행해도 해당 기간 안에 포함된 injection date에만 fake row가 들어간다. 선택한 기간에 이벤트 윈도우가 없으면 baseline과 동일하게 fake row 없이 진행된다.

## 10. 재생성 명령

`data/event.pkl`과 `data/fake_new.pkl`을 갱신한 뒤 injection CSV를 다시 만들려면 다음을 실행한다.

```bash
python scripts/07_prepare_fake_news_injection.py
```

이 스크립트는 다음 파일을 생성/갱신한다.

- `outputs/processed_news_injection.csv`
- `outputs/daily_news_selection_injection.csv`
- `outputs/fake_news_injection_manifest.json`

## 11. 생성 프롬프트 기준

이벤트 선정과 fake news 생성은 아래 원칙을 기준으로 수행했다.

```text
너는 삼성전자 이벤트 기반 fake news injection DB를 만드는 데이터 검수자다.

입력:
- data/samsung_news_raw.pkl에서 추출한 전체 뉴스 후보
- stock_data.csv의 날짜별 주가/거래량 변화
- daily_news_selection.csv의 agent baseline feed

목표:
1. 전체 raw 뉴스에서 삼성전자 주가에 영향을 줄 수 있는 큰 이벤트를 월 2~4개 선정한다.
2. 이벤트는 실적, HBM/반도체, 노사, 규제, 대형 계약/고객사, 업황 급변 등으로 분류한다.
3. predictability를 predictable/unpredictable로 구분한다.
4. predictable은 D-2~D+2, unpredictable은 D~D+2에만 fake news를 만든다.
5. 각 injection date에는 daily baseline feed 중 1개 row를 replace_target_news_id로 지정하고 fake row 1개로 치환한다.
6. fake news는 실제 뉴스 맥락과 대응되게 만들되 사실과 다른 claim을 포함한다.
7. misinformation type은 unintentional_misinformation, deliberate_disinformation, malicious_context_distortion을 균형 있게 배분한다.
8. pre-event row에는 이벤트 결과, 확정 수치, 사후 반응을 사용하지 않는다.
9. agent-visible title/summary/search_summary에는 "가짜뉴스", "허위", "오정보", "실험용" 같은 self-disclosure 표현을 넣지 않는다.
10. Depth 1에는 짧은 summary, Depth 2 검색에는 더 긴 search_summary가 노출되도록 만든다.

출력:
- event.pkl: event_id, event_date, event_timestamp, event_type, predictability, source_raw_index, source_title, source_summary, score columns
- fake_new.pkl: fake_news_id, date, timestamp, title, content, summary, related_event_id, misinformation_type, replace_target_news_id, leakage metadata
```

## 12. 주의사항

- `data/samsung_news_raw.pkl`은 이벤트 선정 원천이고, `daily_news_selection.csv`는 agent feed 및 replacement target 기준이다.
- `fake_new.pkl`은 라벨과 평가용 컬럼을 포함하므로 agent에게 직접 통째로 제공하면 안 된다.
- Runtime에서는 `outputs/*_injection.csv`를 통해 공개 컬럼만 사용한다.
- 예측 불가능 이벤트에 pre-event fake를 만들면 data leakage다.
- D-day라도 fake timestamp가 event timestamp보다 빠르면 결과/확정 수치/타결 여부를 쓰면 안 된다.
- GitHub에는 분석용 임시 CSV나 candidate 파일이 아니라 최종 pkl, injection CSV, guide, runtime script 변경만 올린다.
