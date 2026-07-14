# Phase 허위뉴스 데이터셋 전달 안내

이 문서는 코드 변경 없이, 아래 데이터셋 파일만 지정하여 기존 시뮬레이션을 실행하기 위한 전달본이다. 모든 synthetic row는 연구용 검토 데이터이며, 원문·주장·근거를 검토한 뒤에만 최종 실험에 사용한다.

## 0. Clone 후 실행 환경

0713 코드에는 `dataclass(slots=True)`가 있으므로 **Python 3.10 이상**이 필요하다. 아래를 먼저 완료한 뒤 6조건 명령을 실행한다.

```bash
git clone --branch 0714 https://github.com/ujlee1661/2026_AICP.git
cd 2026_AICP
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

`.env`에 유효한 `OPENROUTER_API_KEY`와 사용할 모델을 설정한다. `python3 --version`이 3.10 이상인지 확인한다. 6개 실행 명령에서는 활성화한 virtual environment의 `python`을 사용해도 된다.

## 1. 전달 파일

| 용도 | 호재성 조건 | 악재성 조건 |
|---|---|---|
| 사람 검토용 원본 PKL | `data/fake_news_bullish_phase_review.pkl` | `data/fake_news_bearish_phase_review.pkl` |
| 실제 실행용 전체 뉴스 풀 | `outputs/processed_news_injection_bullish_phase_review.csv` | `outputs/processed_news_injection_bearish_phase_review.csv` |
| 실제 실행용 일별 노출 목록 | `outputs/daily_news_selection_injection_bullish_phase_review.csv` | `outputs/daily_news_selection_injection_bearish_phase_review.csv` |
| 실행 입력 manifest | `outputs/fake_news_injection_bullish_phase_review_manifest.json` | `outputs/fake_news_injection_bearish_phase_review_manifest.json` |

내용을 검토할 때는 [원사건 기록](FAKE_NEWS_EVENT_REGISTRY.md), [phase stimulus 검토본](data/fake_news_phase_stimulus_review.md), [호재·악재 쌍 표](data/fake_news_phase_pair_manifest_review.csv)를 사용한다. PKL은 원문 근거, human-review 상태, 허위 주장, 사실 앵커를 모두 보존한 원본이고, CSV 두 파일은 현 `NewsAgent`가 그대로 읽는 실행 입력이다.

## 2. 원사건 기록

아래 9개 원사건을 기준으로 호재성·악재성 synthetic claim을 각각 만들었다. 표의 원문은 **사실 앵커**이며, synthetic 기사는 원문에 없는 확정 상태·수치·인과관계를 추가하거나 한쪽 맥락만 강조한 것이다. 원문 URL, 허용 사실 범위, 금지 추론, 양 방향의 전체 문구는 `data/fake_news_phase_pair_manifest_review.csv`와 `data/fake_news_phase_stimulus_review.md`에 보존된다.

| ID | 원문 시각 | 원사건 | 예측 가능성 | 구성 방식 | 원문 |
|---|---|---|---|---|---|
| M01 | 2026-03-04 17:55 | 노사협상 결렬과 쟁의 절차 | 예측 불가능 | 오해·루머 사실화 | [매일경제](https://www.mk.co.kr/news/business/11978737) |
| M02 | 2026-03-17 18:07 | 엔비디아 추론칩 삼성전자 생산 | 예측 가능 | 확정·수치 조작 | [매일경제](https://www.mk.co.kr/news/it/11990590) |
| M03 | 2026-03-26 17:53 | 구글 TurboQuant와 메모리 수요 논쟁 | 예측 불가능 | 선택적 맥락 강조 | [매일경제](https://www.mk.co.kr/news/stock/11999494) |
| A01 | 2026-04-01 18:13 | 반도체 수출과 메모리 업황 | 예측 가능 | 선택적 맥락 강조 | [한국경제](https://www.hankyung.com/article/2026040126601) |
| A02 | 2026-04-07 07:43 | 삼성전자 1분기 잠정실적 | 예측 가능 | 확정·수치 조작 | [매일경제](https://www.mk.co.kr/news/business/12009719) |
| A03 | 2026-04-15 17:23 | 테슬라 AI5와 삼성전자 생산 언급 | 예측 불가능 | 선택적 맥락 강조 | [매일경제](https://www.mk.co.kr/news/business/12017867) |
| Y01 | 2026-05-05 17:42 | 애플 파운드리 협력 검토 | 예측 불가능 | 선택적 맥락 강조 | [매일경제](https://www.mk.co.kr/news/business/12036115) |
| Y02 | 2026-05-21 07:35 | 엔비디아 실적과 AI 데이터센터 수요 | 예측 가능 | 오해·루머 사실화 | [매일경제](https://www.mk.co.kr/news/it/12053993) |
| Y03 | 2026-05-29 08:48 | HBM4E 12단 샘플 출하 | 예측 불가능 | 확정·수치 조작 | [매일경제](https://www.mk.co.kr/news/business/12060768) |

## 3. 데이터셋 구조

- 대상 기간: 2026-02-27~2026-06-01
- 실제 주입일: 조건당 30일. 각 주입일은 **실제 뉴스 10개 + synthetic 기사 1개**다.
- 사건: 기존 분류를 유지한 9개 사건
  - 예측 가능 4개: D−2, D−1, D0, D+1, D+2
  - 예측 불가능 5개: D0, D+1, D+2
- D0는 해당 원문이 AM 의사결정 창에서 처음 보이는 거래일이다.
- 2026-05-31 이후에는 새 주입을 하지 않는다. 따라서 2026-06-01은 관찰일이다.
- 창이 겹친 3일(2026-03-31, 2026-04-03, 2026-04-06)은 기존 규칙대로 하나의 기사로 병합했다.
- 최종 30개 기사에서 `rumor_as_fact`, `confirmation_quantity_distortion`, `selective_context_emphasis`는 각 10개다.
- 같은 사건을 반복 노출할 때 제목과 요약을 단계별로 바꿨다. 사전 관측, 전망 확산, 관련 소식, 후속 확인, 시장 반영은 같은 핵심 주장에 대한 서로 다른 기사 변형이다.

## 4. 고정된 6개 실험 조건

이 브랜치는 아래 여섯 조건만을 본실험 조건으로 둔다. `Bullish`와 `Bearish`는 fake ON일 때만 구분하므로, 설계는 `Community (OFF/ON) × News condition (Factual/Bullish/Bearish) = 6`이다. `--fake-news-polarity` 옵션은 0713 코드에 없으므로 사용하지 않는다. 대신 각 조건의 CSV 경로를 명시한다.

| 조건 | 입력 CSV | fake-news-mode | community-mode |
|---|---|---|---|
| F-OFF | bullish phase CSV | off | off |
| F-ON | bullish phase CSV | off | on |
| B-OFF | bullish phase CSV | on | off |
| B-ON | bullish phase CSV | on | on |
| R-OFF | bearish phase CSV | on | off |
| R-ON | bearish phase CSV | on | on |

모든 조건은 `2026-02-27~2026-06-01`, `pre_close_cutoff`, 동일한 agent 수·agent 순서·seed·모델·temperature·concurrency로 실행한다. `--sim-db`를 지정하지 않는다. 0713 코드가 매 실행마다 `outputs/sim.db`의 분리 복사본을 생성하므로, 여섯 조건의 포트폴리오와 커뮤니티 상태가 서로 이어지지 않는다.

### F-OFF: factual control, community OFF

```bash
python3 scripts/05_run_simulation.py --start-date 2026-02-27 --end-date 2026-06-01 --seed 2 --information-mode pre_close_cutoff --fake-news-mode off --processed-news-csv outputs/processed_news_injection_bullish_phase_review.csv --daily-news-csv outputs/daily_news_selection_injection_bullish_phase_review.csv --community-mode off
```

### F-ON: factual control, community ON

```bash
python3 scripts/05_run_simulation.py --start-date 2026-02-27 --end-date 2026-06-01 --seed 2 --information-mode pre_close_cutoff --fake-news-mode off --processed-news-csv outputs/processed_news_injection_bullish_phase_review.csv --daily-news-csv outputs/daily_news_selection_injection_bullish_phase_review.csv --community-mode on
```

### B-OFF: bullish fake, community OFF

```bash
python3 scripts/05_run_simulation.py --start-date 2026-02-27 --end-date 2026-06-01 --seed 2 --information-mode pre_close_cutoff --fake-news-mode on --processed-news-csv outputs/processed_news_injection_bullish_phase_review.csv --daily-news-csv outputs/daily_news_selection_injection_bullish_phase_review.csv --community-mode off
```

### B-ON: bullish fake, community ON

```bash
python3 scripts/05_run_simulation.py --start-date 2026-02-27 --end-date 2026-06-01 --seed 2 --information-mode pre_close_cutoff --fake-news-mode on --processed-news-csv outputs/processed_news_injection_bullish_phase_review.csv --daily-news-csv outputs/daily_news_selection_injection_bullish_phase_review.csv --community-mode on
```

### R-OFF: bearish fake, community OFF

```bash
python3 scripts/05_run_simulation.py --start-date 2026-02-27 --end-date 2026-06-01 --seed 2 --information-mode pre_close_cutoff --fake-news-mode on --processed-news-csv outputs/processed_news_injection_bearish_phase_review.csv --daily-news-csv outputs/daily_news_selection_injection_bearish_phase_review.csv --community-mode off
```

### R-ON: bearish fake, community ON

```bash
python3 scripts/05_run_simulation.py --start-date 2026-02-27 --end-date 2026-06-01 --seed 2 --information-mode pre_close_cutoff --fake-news-mode on --processed-news-csv outputs/processed_news_injection_bearish_phase_review.csv --daily-news-csv outputs/daily_news_selection_injection_bearish_phase_review.csv --community-mode on
```

호재·악재 phase CSV의 실제 뉴스 10개는 동일하며 synthetic 기사 30개만 방향별로 다르다. 따라서 Factual control은 bullish CSV를 기준으로 한 번만 실행한다. 이 여섯 개 외의 polarity·community 조합은 본 데이터 패키지의 실험 조건으로 만들지 않는다.

## 5. 사전 확인할 사항

- `final_approval=false`이므로 연구자가 [stimulus 검토본](data/fake_news_phase_stimulus_review.md)의 30개 호재/악재 문구를 승인한 뒤 사용한다.
- `summary`가 에이전트에게 실제로 전달되는 텍스트다. `content`, URL, 허위 판단 근거, review metadata는 PKL/manifest에만 보존된다.
- Depth 2 검색도 명령에서 지정한 `processed_news_injection_*_phase_review.csv` 풀을 사용한다. 따라서 fake ON에서는 같은 조건의 synthetic 기사가 검색 후보가 될 수 있고, fake OFF에서는 `is_fake=true` row가 검색에서 제외된다.
- 실행 중 생성되는 run metadata의 `processed_news_csv`, `daily_news_csv`, `fake_news_mode`, `community_mode`가 위 조건과 일치하는지 확인한다.
- 이 전달본은 데이터셋만 추가한다. community 구조, agent persona, 거래 규칙, fallback 등 실행 코드는 변경하지 않는다.

## 6. 데이터 검토 결과

- 호재·악재 각각 30개 synthetic row
- 모든 주입 날짜는 조건 내 유일
- 왜곡 방식 10 : 10 : 10
- 예측 가능 사건의 D−2/D−1은 사후 결과를 사용하지 않음
- 각 원문 ID·URL·사실 앵커·금지 추론을 PKL과 manifest에 연결
- 원문 기사 선정 및 source anchor 교체 내역은 각 `fake_news_injection_*_phase_review_manifest.json`의 `source_anchor_adjustments`에 기록

별도의 smoke run은 이 전달 범위에 포함하지 않는다.
