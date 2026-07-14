# 허위뉴스 생성 원사건 기록

이 문서는 0714의 호재성·악재성 synthetic news가 어떤 실제 사건을 기준으로 만들어졌는지 남기는 사건 레지스트리다. 각 synthetic claim은 아래 원문이 보도한 사실 범위에서 출발했으며, 원문에 없는 확정 상태·수치·인과관계 또는 한쪽 맥락의 과도한 일반화가 treatment의 허위 부분이다.

## 사용 방법

- `source_pair_ID`는 `data/fake_news_bullish_phase_review.pkl`, `data/fake_news_bearish_phase_review.pkl`, `data/fake_news_phase_pair_manifest_review.csv`의 `base_pair_id`와 연결된다.
- 호재성과 악재성은 같은 원사건·동일 주입일·동일 기사 형식을 공유하고, synthetic claim의 방향만 다르다.
- 원문 전체, 허용 사실 범위, 금지 추론, 양 방향의 기사 문구는 [쌍 비교표](data/fake_news_phase_pair_manifest_review.csv)와 [전체 stimulus 검토본](data/fake_news_phase_stimulus_review.md)에 보존한다.
- 이 문서는 원문을 사실 앵커로 기록하는 용도이며, 원사건이 treatment의 허위 주장을 입증한다는 뜻이 아니다.

## 사건 목록

| ID | 원문 시각·출처 | 원사건 | 사실로 사용한 범위 | synthetic claim에서 금지한 추론 | 예측 가능성·주입 창 | 구성 방식 |
|---|---|---|---|---|---|---|
| M01 | 2026-03-04 17:55, [매일경제](https://www.mk.co.kr/news/business/11978737) | 삼성전자 노사협상 결렬 및 노조 쟁의 절차 착수 | 교섭 결렬과 노조의 투쟁 전환·쟁의권 절차 | 실제 반도체 생산 차질, 라인 중단, 최종 노사 합의 | 예측 불가능, D0~D+2 | 오해·루머 사실화 |
| M02 | 2026-03-17 18:07, [매일경제](https://www.mk.co.kr/news/it/11990590) | 엔비디아 추론칩의 삼성전자 생산·3분기 출하 계획 보도 | 삼성전자의 LPU 제조와 3분기 출하 계획 | 구체적 생산 배정 물량, 계약 확대·축소 비율 | 예측 가능, D−2~D+2 | 확정·수치 조작 |
| M03 | 2026-03-26 17:53, [매일경제](https://www.mk.co.kr/news/stock/11999494) | Google TurboQuant 공개 후 AI 메모리 수요 논쟁 | 수요 위축 우려와 물리 메모리 수요가 유지될 수 있다는 반론 | 삼성전자 실제 주문·매출의 증가 또는 감소 | 예측 불가능, D0~D+2 | 선택적 맥락 강조 |
| A01 | 2026-04-01 18:13, [한국경제](https://www.hankyung.com/article/2026040126601) | 반도체 수출 및 메모리 업황 신호 | 반도체 수출·메모리 업황의 섹터 신호와 거시 불확실성 | 삼성전자 개별 고객 수주, 계약가격, 실적의 확정 | 예측 가능, D−2~D+2 | 선택적 맥락 강조 |
| A02 | 2026-04-07 07:43, [매일경제](https://www.mk.co.kr/news/business/12009719) | 삼성전자 1분기 잠정실적 발표 | 잠정실적 수치와 사업부별 수치 미공개 상태 | DS 부문 확정 실적, 향후 출하 목표, 연간 가이던스 | 예측 가능, D−2~D+2 | 확정·수치 조작 |
| A03 | 2026-04-15 17:23, [매일경제](https://www.mk.co.kr/news/business/12017867) | 테슬라 AI5 테이프아웃 및 Samsung·TSMC 언급 | AI5 테이프아웃, 생산 지원 언급, 2027년 양산 예상 | 이전 계약 금액, AI6 정보, 세부 생산 배정 물량 | 예측 불가능, D0~D+2 | 선택적 맥락 강조 |
| Y01 | 2026-05-05 17:42, [매일경제](https://www.mk.co.kr/news/business/12036115) | 애플의 삼성 파운드리 협력 가능성 검토 | 초기 검토, 삼성 팹 방문, 계약 미확정 | 실제 발주, 시범 생산, 계약 체결·종료 | 예측 불가능, D0~D+2 | 선택적 맥락 강조 |
| Y02 | 2026-05-21 07:35, [매일경제](https://www.mk.co.kr/news/it/12053993) | 엔비디아 실적과 AI 데이터센터 수요 | 엔비디아 실적과 AI 인프라 수요 신호 | 삼성전자 HBM의 실제 공급 물량·주문 변화 | 예측 가능, D−2~D+2 | 오해·루머 사실화 |
| Y03 | 2026-05-29 08:48, [매일경제](https://www.mk.co.kr/news/business/12060768) | 삼성전자 HBM4E 12단 샘플 출하 | 글로벌 고객사 샘플 공급과 양산 추진 계획 | 고객 검증 완료, 양산 물량 확정, 공급 중단 | 예측 불가능, D0~D+2 | 확정·수치 조작 |

## 주입 슬롯과 사건 수

- 예측 가능 사건 4개는 D−2, D−1, D0, D+1, D+2의 다섯 단계로 변형한다.
- 예측 불가능 사건 5개는 D0, D+1, D+2의 세 단계로 변형한다.
- 2026-05-31 이후에는 새 기사를 주입하지 않으므로, 2026-06-01은 관찰일이다.
- 같은 날짜의 창이 겹친 경우 하나의 primary 기사로 병합한다. 결과적으로 조건당 30개 주입일이 된다.
- 호재성·악재성 각각 30개씩이며, 세 claim 구성 방식은 각 10개다.

## 재현성 연결

| 파일 | 역할 |
|---|---|
| `data/fake_news_bullish_phase_review.pkl` | 호재성 원본 row와 source provenance |
| `data/fake_news_bearish_phase_review.pkl` | 악재성 원본 row와 source provenance |
| `data/fake_news_phase_pair_manifest_review.csv` | 동일 날짜의 호재/악재 텍스트 및 사실 앵커 비교 |
| `data/fake_news_phase_stimulus_review.md` | 30개 주입일 전체 기사 검토 |
| `outputs/*_phase_review.csv` | 시뮬레이션이 실제로 읽는 6조건용 실행 입력 |
