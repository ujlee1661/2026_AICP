# Trading Direction Validation

삼성전자 실제 투자자별 순거래 내역과 TwinMarket Korea 시뮬레이션의 일별 순매수/순매도 방향을 비교한다.

## 입력 파일

- `validation/data_trading_value.csv`: 실제 투자자별 순거래대금
- `validation/data_trading_volume.csv`: 실제 투자자별 순거래량
- `outputs/logs/current`: 기본 시뮬레이션 로그 폴더

## 실행

```bash
python3 validation/validate_trading_direction.py
```

특정 시뮬레이션 로그를 검증하려면:

```bash
python3 validation/validate_trading_direction.py --run-dir outputs/logs/simulation_YYYYMMDD_HHMMSS
```

## 산출물

기본 산출물은 `validation/outputs/<run_id>/` 아래에 생성된다.

- `daily_comparison_value.csv`: 거래대금 기준 일별 비교
- `daily_comparison_volume.csv`: 거래량 기준 일별 비교
- `normalized_comparison_value.csv`: 거래대금 기준 정규화 일별 비교
- `normalized_comparison_volume.csv`: 거래량 기준 정규화 일별 비교
- `summary_metrics.json`: 방향 일치율, 상관계수, 코사인 유사도 요약
- `validation_report.pdf`: 최종 분석 PDF 보고서

## 검증 기준

- LLM 에이전트 체결: `buy`는 양수, `sell`은 음수로 환산한다.
- 기본 검증: LLM 에이전트 전체 순거래 방향과 실제 `Individuals` 방향을 비교한다.
- 보조 검증: `COUNTERSIDE` 순거래 방향을 실제 `Subtotal-Institutions`, `Total of foreign`, `Other corporations` 흐름과 비교한다.
- 체결이 없는 시뮬레이션 날짜는 순거래 0으로 포함한다.
- 기본 설정은 초기 warmup 3거래일을 제외한다. `--skip-initial-days 0`으로 전체 기간 검증이 가능하다.
- 방향 일치율은 원본값의 부호 기준으로 계산한다.
- 양상 비교는 각 주체별 `max_abs`, `z_score`, `cumulative_max_abs` 정규화 지표를 함께 산출한다.
