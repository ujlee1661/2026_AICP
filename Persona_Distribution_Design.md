# TwinMarket Korea — 페르소나 배포 및 선발 시스템 설계서

---

## 1. 시스템 목적 및 설계 동기

기존 TwinMarket 연구는 중국 주식 시장을 배경으로 1000명의 에이전트 페르소나 데이터(sys_1000.db)를 구성하여 사용했다. 이 데이터에는 각 에이전트의 행동 편향, 거래 빈도, 투자 전략 등 행동적 속성이 상세히 포함되어 있다. 이 행동 프로파일이 왜 재사용 가능한가에 대한 답은 `Persona_Report_2.pdf`(Sui & Wang, 2025, "Stakes and Investor Behaviors")에서 찾을 수 있다. 해당 연구는 처분효과, 복권형 주식 선호, 과잉거래, 분산투자 부족, 수익률 등 행동 편향이 동일 투자자의 실계좌와 모의계좌에 걸쳐 강한 일관성을 보임을 실증했다. 즉, 행동 편향은 개인의 고유한 특성으로 시장 맥락이 바뀌어도 지속된다. 따라서 중국 투자자 데이터의 행동 프로파일은 한국 삼성전자 투자자에게도 동일하게 적용 가능하다.

그러나 에이전트의 인구통계적 정체성은 전혀 달라야 한다. 기존 데이터는 남성 941명, 여성 59명으로 극단적으로 편향되어 있어 실제 삼성전자 주주 분포(여성 56.99%, 남성 42.34%)와 정반대에 가깝다. 연령 정보는 아예 없는 상태다.

이 시스템의 설계는 두 단계로 구성된다. 첫째, `Persona_Report_1.pdf`(KSD 삼성전자 주주 통계, 2025/12/31)를 기반으로 **100명의 고정 인구통계 슬롯**(agent_id, 성별, 나이, 연령대, 자산군)을 사전에 확정한다. 이 리스트는 변경되지 않는다. 둘째, 각 슬롯에 대해 성별·연령대·자산군으로 구성된 **14개 세그먼트 특성 기준**에 따라 1000명 pool에서 가장 현실적으로 어울리는 행동 프로파일을 가진 에이전트를 선발하여 배정한다.

또한 기존 sys_prompt, prompt, self_description 세 칼럼을 하나의 persona_prompt로 통합하여 정적 정체성을 단일 텍스트로 관리하고, 동적 포트폴리오 상태 칼럼은 페르소나 테이블에서 분리한다.

---

## 2. 데이터 기반 — 삼성전자 주주 통계 (Persona_Report_1.pdf)

이 섹션의 모든 수치는 KSD SEIBro, 2025/12/31 기준 삼성전자 주주 명부(`Persona_Report_1.pdf`)에서 직접 인용한다.

### 성별 분포

| 성별 | 주주 수 | 비율 | 100명 적용 |
|------|---------|------|-----------|
| 남성 | 1,776,614 | 42.34% | 43명 |
| 여성 | 2,391,543 | 56.99% | 57명 |
| 기타(법인·단체) | 27,868 | 0.66% | → 여성에 흡수 |

### 연령대별 분포

| 연령대 | 주주 수 | 비율 | 포함 여부 | 100명 재배정 |
|--------|---------|------|---------|------------|
| 20세 미만 | 343,694 | 8.19% | 제외 | — |
| 20대 | 333,946 | 7.95% | 포함 | 9명 |
| 30대 | 680,702 | 16.22% | 포함 | 18명 |
| 40대 | 898,589 | 21.41% | 포함 | 23명 |
| 50대 | 1,003,614 | 23.91% | 포함 | 26명 |
| 60대 | 655,491 | 15.62% | 포함 | 17명 |
| 70대 | 215,004 | 5.12% | 포함 | 6명 |
| 80대 이상 | 44,875 | 1.06% | 포함 | 1명 |
| 미분류 | 20,110 | 0.47% | 제외 | — |

20세 미만과 미분류를 제외한 91.29% 기준으로 비례 재배정한 결과다.

### 지역별 분포 (100명 기준)

| 지역 | 주주 수 | 비율 | 100명 목표 |
|------|---------|------|-----------|
| 경기 | 1,237,555 | 29.49% | 29명 |
| 서울 | 1,097,867 | 26.16% | 26명 |
| 부산 | 231,382 | 5.51% | 6명 |
| 인천 | 216,188 | 5.15% | 5명 |
| 경남 | 200,998 | 4.79% | 5명 |
| 대구 | 176,937 | 4.21% | 4명 |
| 경북 | 147,056 | 3.50% | 4명 |
| 충남 | 130,530 | 3.11% | 3명 |
| 대전 | 113,676 | 2.70% | 3명 |
| 광주 | 106,794 | 2.54% | 3명 |
| 전북 | 99,927 | 2.38% | 2명 |
| 충북 | 95,716 | 2.28% | 2명 |
| 울산 | 93,434 | 2.22% | 2명 |
| 전남 | 87,171 | 2.07% | 2명 |
| 강원 | 79,283 | 1.88% | 2명 |
| 제주 | 37,950 | 0.90% | 1명 |
| 세종 | 37,937 | 0.90% | 1명 |
| 기타 | 5,623 | 0.13% | 0명 |

---

## 3. 연구 기반 — 행동 편향의 유효성 (Persona_Report_2.pdf)

`Persona_Report_2.pdf` (Sui & Wang, 2025, "Stakes and Investor Behaviors")는 우리 시스템에서 사용하는 행동 편향 카테고리가 실증적으로 유효하며 개인 특성으로 지속된다는 학술적 근거를 제공한다. 해당 논문은 4,413명 중국 투자자의 실계좌·모의계좌 within-subject 비교를 통해 처분효과, 복권형 주식 선호, 과잉거래, 분산투자 부족, 성과 차이가 개인 내에서 일관되게 나타남을 실증했다.

이 다섯 가지 편향은 sys_1000.db의 behavioral columns와 직접 대응한다:

| 논문의 편향 | sys_1000.db 칼럼 |
|-----------|----------------|
| Disposition effect | bh_disposition_effect_category |
| Lottery preferences | bh_lottery_preference_category |
| Active trading (turnover) | bh_annual_turnover_category, trade_count_category |
| Underdiversification | bh_underdiversification_category |
| Performance | bh_total_return_category |

논문이 인용하는 선행 연구(Grinblatt et al., 2011; Cronqvist & Siegel, 2014)는 행동 편향의 강도가 연령과 상관관계를 가짐을 보여 연령-행동 세그먼트 매핑의 근거가 된다.

---

## 4. 모집단 행동 특성 현황 (sys_1000.db — Profiles 테이블)

pool로 사용하는 `sys_1000.db`의 테이블명은 **Profiles**이며, primary key는 `user_id`다. 이 테이블의 모든 값은 **중국어(한자)**로 저장되어 있으므로 pool을 읽어올 때 아래 매핑 규칙을 적용한다.

**gender, location, age는 pool에서 읽지 않는다.** 이 세 값은 고정 슬롯 리스트에서 직접 부여되며 pool과 무관하다. ini_cash도 고정 슬롯 기준을 사용하므로 pool의 위안화 값은 참고만 한다.

### 값 매핑 규칙 (DB 저장값 → 시스템 사용값)

| DB 저장값 | 의미 | 시스템 사용값 |
|-----------|------|------------|
| `高` | 높음 | `high` |
| `中` | 중간 | `medium` |
| `低` | 낮음 | `low` |
| `技术面` | 기술적 분석 | `technical` |
| `基本面` | 가치/기본적 분석 | `value` |
| `普通股民` | 일반 개미 투자자 | `ordinary` |
| `小博主` | 팔로워 적은 인플루언서 | `small_influencer` |
| `大V` | 유명 인플루언서 | `big_influencer` |

### Profiles 테이블 behavioral category 분포

| 카테고리 | DB 저장값 | 의미 | 인원 |
|---------|----------|------|------|
| bh_disposition_effect | `中` (medium) | 균형 잡힌 매도/보유 판단 | 338명 |
| | `低` (low) | 수익 장기 보유, 이성적 손절 | 333명 |
| | `高` (high) | 수익 빠른 매도, 손실 물타기 | 329명 |
| bh_lottery_preference | `低` (low) | 안정형, 검증된 자산 선호 | 643명 |
| | `高` (high) | 초고위험 복권형 선호 | 298명 |
| | `中` (medium) | 중간 | 59명 |
| bh_total_return | `中` (medium) | 평균 수익 | 360명 |
| | `低` (low) | 저수익 이력 | 343명 |
| | `高` (high) | 고수익 이력 | 297명 |
| bh_annual_turnover | `低` (low) | 장기보유 | 371명 |
| | `中` (medium) | 중간 | 330명 |
| | `高` (high) | 자주 사고팖 | 299명 |
| bh_underdiversification | `中` (medium) | 어느정도 집중 | 678명 |
| | `低` (low) | 잘 분산 | 322명 |
| trade_count | `中` (medium) | 평균 거래 횟수 | 371명 |
| | `低` (low) | 거래 적음 | 332명 |
| | `高` (high) | 거래 많음 | 297명 |
| user_type | `普通股民` | 일반 개미 투자자 | 912명 |
| | `小博主` | 팔로워 적은 인플루언서 | 77명 |
| | `大V` | 유명 인플루언서 | 11명 |
| strategy | `技术面` | technical (기술적 지표 기반) | 600명 |
| | `基本面` | value (가치평가 기반) | 400명 |

### ini_cash 원본 분포 (참고용)

| 위안 단위 원본값 | 인원 | 비율 |
|---------------|------|------|
| 10,000,000 위안 | 731명 | 73.1% |
| 100,000,000 위안 | 269명 | 26.9% |

원본 pool의 ini_cash는 중국 위안 기준이며 직접 사용하지 않는다. 한국 시뮬레이션의 ini_cash(1억 원 90명, 10억 원 10명)는 고정 슬롯에서 결정된다.

---

## 5. 사전 정의된 100명 고정 슬롯

100명의 인구통계 슬롯은 Persona_Report_1.pdf를 기반으로 사전에 확정된다. 이 리스트는 시뮬레이션 전반에 걸쳐 변경되지 않는 고정 기준이다. 각 슬롯은 성별, 나이, 연령대, 운용자산만 정의하며, 행동 프로파일은 Section 6·7의 세그먼트 기준에 따라 pool에서 선발하여 채운다.

### 분포 검증

| 구분 | 배정 |
|------|------|
| 남성 | 43명 |
| 여성 | 57명 |
| 1억 | 90명 |
| 10억 | 10명 |
| 20대 | 9명 |
| 30대 | 18명 |
| 40대 | 23명 |
| 50대 | 26명 |
| 60대 | 17명 |
| 70대 | 6명 |
| 80대 이상 | 1명 |

| 연령대 | 10억 배정 |
|--------|---------|
| 40대 | 2명 |
| 50대 | 4명 |
| 60대 | 3명 |
| 70대 | 1명 |

### 고정 슬롯 전체 목록

```
agent_id, 성별,  나이, 연령대,    운용자산
A001,     여성,  21,  20대,      1억
A002,     여성,  22,  20대,      1억
A003,     남성,  23,  20대,      1억
A004,     남성,  24,  20대,      1억
A005,     여성,  25,  20대,      1억
A006,     남성,  26,  20대,      1억
A007,     여성,  27,  20대,      1억
A008,     여성,  28,  20대,      1억
A009,     남성,  29,  20대,      1억
A010,     여성,  30,  30대,      1억
A011,     남성,  31,  30대,      1억
A012,     남성,  32,  30대,      1억
A013,     남성,  33,  30대,      1억
A014,     여성,  34,  30대,      1억
A015,     여성,  35,  30대,      1억
A016,     여성,  36,  30대,      1억
A017,     여성,  37,  30대,      1억
A018,     남성,  38,  30대,      1억
A019,     남성,  39,  30대,      1억
A020,     남성,  30,  30대,      1억
A021,     여성,  31,  30대,      1억
A022,     여성,  32,  30대,      1억
A023,     여성,  33,  30대,      1억
A024,     여성,  34,  30대,      1억
A025,     여성,  35,  30대,      1억
A026,     여성,  36,  30대,      1억
A027,     여성,  37,  30대,      1억
A028,     남성,  40,  40대,      1억
A029,     남성,  41,  40대,      1억
A030,     남성,  42,  40대,      1억
A031,     남성,  40,  40대,      1억
A032,     여성,  41,  40대,      1억
A033,     여성,  42,  40대,      1억
A034,     여성,  40,  40대,      1억
A035,     여성,  41,  40대,      1억
A036,     여성,  42,  40대,      1억
A037,     남성,  43,  40대,      1억
A038,     남성,  44,  40대,      1억
A039,     여성,  45,  40대,      10억
A040,     여성,  46,  40대,      1억
A041,     남성,  47,  40대,      1억
A042,     남성,  48,  40대,      1억
A043,     여성,  49,  40대,      10억
A044,     여성,  43,  40대,      1억
A045,     남성,  44,  40대,      1억
A046,     여성,  45,  40대,      1억
A047,     여성,  46,  40대,      1억
A048,     여성,  47,  40대,      1억
A049,     여성,  48,  40대,      1억
A050,     여성,  49,  40대,      1억
A051,     여성,  50,  50대,      1억
A052,     남성,  51,  50대,      10억
A053,     여성,  52,  50대,      1억
A054,     남성,  53,  50대,      1억
A055,     남성,  54,  50대,      1억
A056,     여성,  55,  50대,      10억
A057,     남성,  50,  50대,      1억
A058,     여성,  51,  50대,      1억
A059,     여성,  52,  50대,      1억
A060,     여성,  53,  50대,      1억
A061,     여성,  54,  50대,      1억
A062,     여성,  55,  50대,      1억
A063,     남성,  50,  50대,      10억
A064,     여성,  51,  50대,      1억
A065,     남성,  52,  50대,      1억
A066,     여성,  53,  50대,      1억
A067,     남성,  54,  50대,      1억
A068,     남성,  55,  50대,      1억
A069,     여성,  56,  50대,      1억
A070,     남성,  57,  50대,      1억
A071,     여성,  58,  50대,      10억
A072,     여성,  59,  50대,      1억
A073,     남성,  56,  50대,      1억
A074,     여성,  57,  50대,      1억
A075,     여성,  58,  50대,      1억
A076,     여성,  59,  50대,      1억
A077,     여성,  60,  60대,      1억
A078,     여성,  61,  60대,      1억
A079,     여성,  62,  60대,      1억
A080,     남성,  63,  60대,      10억
A081,     여성,  64,  60대,      1억
A082,     남성,  65,  60대,      10억
A083,     남성,  66,  60대,      1억
A084,     남성,  60,  60대,      1억
A085,     남성,  61,  60대,      1억
A086,     남성,  62,  60대,      1억
A087,     여성,  63,  60대,      10억
A088,     남성,  64,  60대,      1억
A089,     남성,  65,  60대,      1억
A090,     남성,  66,  60대,      1억
A091,     여성,  67,  60대,      1억
A092,     남성,  68,  60대,      1억
A093,     여성,  69,  60대,      1억
A094,     여성,  70,  70대,      1억
A095,     남성,  72,  70대,      1억
A096,     여성,  74,  70대,      1억
A097,     남성,  76,  70대,      10억
A098,     남성,  78,  70대,      1억
A099,     여성,  79,  70대,      1억
A100,     남성,  82,  80대 이상, 1억
```

---

## 6. 세그먼트별 페르소나 특성 (14개 세그먼트)

성별 × 연령대가 페르소나의 기본 행동 성향을 결정하고, 자산군(1억/10억)이 그 강도를 보정한다. 각 세그먼트는 pool에서 에이전트를 선발할 때의 behavioral category 우선순위를 정의한다.

### 성별 공통 특성

| 성별 | 기본 특징 |
|------|---------|
| 남성 | 거래빈도·회전율이 높음. ETP·레버리지·인버스 활용 성향이 상대적으로 큼. 잦은 거래로 인해 평균 성과가 낮아질 가능성이 큼. |
| 여성 | 보유종목 수가 상대적으로 많고 국내주식 중심의 안정적 보유 성향. 거래빈도·회전율이 낮고, 평균 성과가 남성보다 우수한 그룹으로 설정. |

### 연령대별 공통 특성

| 연령대 | 기본 특징 |
|--------|---------|
| 20대 | 거래 빈도는 낮지만 회전율은 높음. 소규모 자금으로 탐색적 매매. ETP 활용 비중이 상대적으로 높음. |
| 30대 | 거래 빈도와 회전율이 모두 가장 높은 핵심 단기·중단기 매매층. 성과 악화 위험이 큼. |
| 40대 | 국내주식 핵심 보유층. 인버스 활용 성향이 비교적 높음. 시장 흐름에 대한 대응 매매 가능성이 큼. |
| 50대 | 가장 큰 비중의 투자자층. 거래 빈도와 자산규모가 모두 커 시장 영향력이 큼. |
| 60대 | 국내시장 잔류 성향이 높고 국내주식 집중도가 높음. 평균 성과는 다른 연령대보다 양호하게 설정. |
| 70대 | 국내 집중도가 매우 높고 장기보유 성향이 강함. 신규 상품 활용은 낮게 설정. |
| 80대 이상 | 초고령 장기보유형. 거래 빈도는 매우 낮고 삼성전자 같은 대형주 중심 보유 성향. |

### 세그먼트별 behavioral category 우선순위 (매칭 기준)

배열의 앞 항목이 1순위다. 매칭 대상: bh_annual_turnover, bh_lottery_preference, trade_count, strategy, bh_disposition_effect.

```
남성_20대_1억:
  핵심 이미지: 소액 자금으로 탐색하는 공격적 초보 투자자
  bh_annual_turnover:    [high, medium]
  bh_lottery_preference: [high, medium]
  trade_count:           [medium, low]       ← 거래 횟수는 낮되 회전율은 높음
  strategy:              [technical]
  bh_disposition_effect: [high, medium]      ← 물타기, 빠른 갈아타기

여성_20대_1억:
  핵심 이미지: 소액으로 투자 경험을 쌓는 탐색형 안정 투자자
  bh_annual_turnover:    [medium, low]
  bh_lottery_preference: [low, medium]
  trade_count:           [low, medium]
  strategy:              [technical, value]
  bh_disposition_effect: [medium, low]

남성_30대_1억:
  핵심 이미지: 가장 활동적인 단기·중단기 매매형 투자자
  bh_annual_turnover:    [high]
  bh_lottery_preference: [high, medium]
  trade_count:           [high, medium]
  strategy:              [technical]
  bh_disposition_effect: [high, medium]

여성_30대_1억:
  핵심 이미지: 투자 경험을 쌓아가는 현실적 자산형성 투자자
  bh_annual_turnover:    [medium, low]
  bh_lottery_preference: [low, medium]
  trade_count:           [medium, low]
  strategy:              [value, technical]
  bh_disposition_effect: [medium, low]

남성_40대_1억:
  핵심 이미지: 시장 흐름에 적극 대응하는 중견 투자자
  bh_annual_turnover:    [high, medium]
  bh_lottery_preference: [medium, high]      ← ETP·인버스 활용
  trade_count:           [medium, high]
  strategy:              [technical]
  bh_disposition_effect: [medium, high]

남성_40대_10억:
  핵심 이미지: 경험 있는 고액 대응형 투자자
  bh_annual_turnover:    [medium]
  bh_lottery_preference: [medium, low]
  trade_count:           [medium]
  strategy:              [technical, value]
  bh_disposition_effect: [medium]

여성_40대_1억:
  핵심 이미지: 국내 대형주를 꾸준히 보유하는 안정형 핵심 투자자
  bh_annual_turnover:    [low, medium]
  bh_lottery_preference: [low]
  trade_count:           [low, medium]
  strategy:              [value, technical]
  bh_disposition_effect: [low, medium]

여성_40대_10억:
  핵심 이미지: 분산 포트폴리오를 운용하는 고액 안정형 투자자
  bh_annual_turnover:    [low]
  bh_lottery_preference: [low]
  trade_count:           [low]
  strategy:              [value]
  bh_disposition_effect: [low]

남성_50대_1억:
  핵심 이미지: 자산규모와 거래 영향력이 큰 적극적 투자자
  bh_annual_turnover:    [medium, high]
  bh_lottery_preference: [medium]
  trade_count:           [high, medium]
  strategy:              [technical]
  bh_disposition_effect: [high, medium]     ← 물타기 성향

남성_50대_10억:
  핵심 이미지: 경험 많은 고액 안정형 활동 투자자
  bh_annual_turnover:    [medium]
  bh_lottery_preference: [low, medium]
  trade_count:           [medium]
  strategy:              [technical, value]
  bh_disposition_effect: [medium]

여성_50대_1억:
  핵심 이미지: 대형주 중심의 안정적 장기 보유 투자자
  bh_annual_turnover:    [low]
  bh_lottery_preference: [low]
  trade_count:           [low, medium]
  strategy:              [value]
  bh_disposition_effect: [low, medium]

여성_50대_10억:
  핵심 이미지: 분산 잘 된 고액 안정형 장기 투자자
  bh_annual_turnover:    [low]
  bh_lottery_preference: [low]
  trade_count:           [low]
  strategy:              [value]
  bh_disposition_effect: [low]

남성_60대_1억:
  핵심 이미지: 경험 많은 국내시장 활동형 투자자
  bh_annual_turnover:    [low, medium]
  bh_lottery_preference: [low]
  trade_count:           [low, medium]
  strategy:              [value, technical]
  bh_disposition_effect: [medium, low]

남성_60대_10억:
  핵심 이미지: 국내시장에 머무르는 고액 경험형 투자자
  bh_annual_turnover:    [low]
  bh_lottery_preference: [low]
  trade_count:           [medium, low]
  strategy:              [value]
  bh_disposition_effect: [medium]

여성_60대_1억:
  핵심 이미지: 국내 대형주를 오래 보유하는 보수적 장기 투자자
  bh_annual_turnover:    [low]
  bh_lottery_preference: [low]
  trade_count:           [low]
  strategy:              [value]
  bh_disposition_effect: [low]

여성_60대_10억:
  핵심 이미지: 분산된 고액 보수형 장기 투자자
  bh_annual_turnover:    [low]
  bh_lottery_preference: [low]
  trade_count:           [low]
  strategy:              [value]
  bh_disposition_effect: [low]

남성_70대_1억:
  핵심 이미지: 국내 대형주에 강하게 집중된 경험 기반 보유 투자자
  bh_annual_turnover:    [low]
  bh_lottery_preference: [low]
  trade_count:           [low]
  strategy:              [value]
  bh_disposition_effect: [low, medium]

남성_70대_10억:
  핵심 이미지: 경험 많은 고액 보수형 보유 투자자
  bh_annual_turnover:    [low]
  bh_lottery_preference: [low]
  trade_count:           [low]
  strategy:              [value]
  bh_disposition_effect: [low]

여성_70대_1억:
  핵심 이미지: 거래를 거의 하지 않는 보수적 안정형 투자자
  bh_annual_turnover:    [low]
  bh_lottery_preference: [low]
  trade_count:           [low]
  strategy:              [value]
  bh_disposition_effect: [low]

남성_80대이상_1억:
  핵심 이미지: 초장기 보유 중심의 초고령 보수형 투자자
  bh_annual_turnover:    [low]
  bh_lottery_preference: [low]
  trade_count:           [low]
  strategy:              [value]
  bh_disposition_effect: [low]
```

---

## 7. 자산군 보정 규칙

세그먼트 기준은 기본값이며, 자산군이 행동 강도를 보정한다.

**1억 (일반 자산군)**
- 포트폴리오 실질 분산: 낮음 (1~3개 종목 집중)
- 절세계좌 활용: 보통 또는 낮음
- bh_underdiversification 우선순위: medium 우선
- 복권형 주식 성향: 성별·연령대에 따라 기본 세그먼트 적용

**10억 (고액 자산군)**
- 투자 경험: 높게 설정 (bh_total_return 우선순위: high 우선)
- 포트폴리오 분산: 1억보다 높음 (bh_underdiversification 우선순위: low 우선)
- 회전율: 기본 세그먼트보다 한 단계 낮게 적용
- 복권형 선호: 기본 세그먼트보다 낮게 적용 (투자 경험으로 인한 신중함)
- 절세계좌·ETP 활용: 높게 설정 (직접 반영은 어렵지만 strategy가 value 쪽으로 이동)

---

## 8. 전체 컬럼 정의 및 처리 방침

### 유지 컬럼 (원본 그대로)

| 컬럼명 | 값 범위 | 유지 이유 |
|--------|---------|---------|
| user_type | 일반 개미 / 팔로워 적은 인플루언서 / 유명 인플루언서 | 소셜 역할 분류 |
| bh_disposition_effect_category | low / medium / high | 개인 고유 행동 특성 |
| bh_lottery_preference_category | low / medium / high | 개인 고유 행동 특성 |
| bh_total_return_category | low / medium / high | 개인 고유 행동 특성 |
| bh_annual_turnover_category | low / medium / high | 개인 고유 행동 특성 |
| bh_underdiversification_category | low / medium | 개인 고유 행동 특성 |
| trade_count_category | low / medium / high | 개인 고유 행동 특성 |
| strategy | technical / value | 투자 판단 방식 |
| trad_pro | 0 (전 에이전트) | 변경 없음 |

### 수정 컬럼 (Persona_Report_1.pdf 기준으로 교체)

| 컬럼명 | 원본 | 변경 후 |
|--------|------|---------|
| gender | 남성 941명, 여성 59명 (중국 기준, 편향) | 고정 슬롯 기준: 남성 43명, 여성 57명 |
| location | 중국 지명 | 한국 17개 시도 (지역 분포 기반 가중 배정) |

### 추가 컬럼 (신규)

| 컬럼명 | 설명 |
|--------|------|
| age | 고정 슬롯에서 직접 부여 (나이 정수) |
| persona_prompt | sys_prompt + prompt + self_description 통합 텍스트 |

### 고정값 컬럼

| 컬럼명 | 값 |
|--------|---|
| fol_ind | `{"전기전자", "반도체"}` (전 에이전트 동일) |
| ini_cash | 고정 슬롯에서 직접 부여 (1억: 90명, 10억: 10명) |

### 제거 컬럼

sys_prompt, prompt, self_description → persona_prompt로 통합  
current_cash, cur_positions, total_value, total_return, return_rate, stock_returns, yest_returns, initial_positions, created_at → portfolio_state 테이블로 분리

---

## 9. 전체 시스템 흐름

```
[고정 슬롯 로드 (100명 리스트)]
(agent_id, 성별, 나이, 연령대, 운용자산 사전 확정)
        ↓
[sys_1000.db 로드 — 1000명 행동 프로파일 pool]
        ↓
[각 슬롯별 세그먼트 결정]
(성별 × 연령대 × 자산군 → 14개 세그먼트 중 하나로 분류)
        ↓
[세그먼트 기준 behavioral profile 조회]
(Section 6의 우선순위 배열 로드)
        ↓
[pool → 슬롯 가중 선택]
(세그먼트 프로파일과의 일치도를 점수로 환산, 가중 랜덤 선발로 다양성 확보, 1인 1슬롯)
        ↓
[location 배정 — Persona_Report_1.pdf 지역 분포 가중 샘플링]
        ↓
[persona_prompt 생성]
        ↓
[sys_100.db 저장]
        ↓
[분포 검증]
```

---

## 10. 운영 단계 — Phase 시스템

**Phase 1: 고정 슬롯 로드** — 100명 고정 리스트를 로드한다. age, 성별, 연령대, ini_cash는 이 단계에서 확정된다.

**Phase 2: Pool 로드** — sys_1000.db의 **Profiles** 테이블에서 behavioral columns 전체를 로드한다. gender, location은 읽지 않는다. 한자 값은 값 매핑 규칙(Section 4)을 적용해 영문으로 변환한다.

**Phase 3: 세그먼트 분류** — 각 슬롯을 (연령대, 성별, 자산군) 조합으로 분류하여 Section 6의 behavioral profile 우선순위 기준을 할당한다.

**Phase 4: 가중 선택** — 각 슬롯에 대해 세그먼트 프로파일과의 일치 정도를 점수로 환산하고, 이를 가중치로 삼아 pool 전체에서 확률적으로 선발한다. 특정 프로파일에 해당하는 에이전트를 중점적으로 선발하되, pool 전체가 선발 대상이 되어 다양성을 확보한다. 1인 1슬롯 원칙.

**Phase 5: location 배정** — Persona_Report_1.pdf 지역 분포 기반으로 가중 랜덤 샘플링한다.

**Phase 6: persona_prompt 생성 및 저장** — 통합 텍스트를 생성하고 sys_100.db에 저장한다.

---

## 11. 각 Phase 핵심 알고리즘

### Phase 1: 고정 슬롯 로드

```python
def load_fixed_slots(csv_path: str) -> list[dict]:
    # 100명 고정 리스트 CSV 로드
    # 반환: agent_id, gender, age, age_group, ini_cash 포함 100개 딕셔너리
    slots = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            slots.append({
                "agent_id":  row["agent_id"],
                "gender":    "male" if row["성별"] == "남성" else "female",
                "age":       int(row["나이"]),
                "age_group": row["연령대"],   # "20대", "30대", ...
                "ini_cash":  parse_cash(row["운용자산"]),  # "1억" → 100000000
            })
    return slots  # 100개
```

### Phase 3: 세그먼트 분류 및 behavioral profile 조회

```python
def get_behavioral_profile(age_group: str, gender: str, ini_cash: int) -> dict:
    asset_group = "고액" if ini_cash >= 1_000_000_000 else "일반"
    segment = f"{gender}_{age_group}_{asset_group}"

    profiles = {
        # --- 20대 ---
        "male_20대_일반": {
            "bh_annual_turnover_category":    ["high", "medium"],
            "bh_lottery_preference_category": ["high", "medium"],
            "trade_count_category":           ["medium", "low"],
            "strategy":                       ["technical"],
            "bh_disposition_effect_category": ["high", "medium"],
        },
        "female_20대_일반": {
            "bh_annual_turnover_category":    ["medium", "low"],
            "bh_lottery_preference_category": ["low", "medium"],
            "trade_count_category":           ["low", "medium"],
            "strategy":                       ["technical", "value"],
            "bh_disposition_effect_category": ["medium", "low"],
        },
        # --- 30대 ---
        "male_30대_일반": {
            "bh_annual_turnover_category":    ["high"],
            "bh_lottery_preference_category": ["high", "medium"],
            "trade_count_category":           ["high", "medium"],
            "strategy":                       ["technical"],
            "bh_disposition_effect_category": ["high", "medium"],
        },
        "female_30대_일반": {
            "bh_annual_turnover_category":    ["medium", "low"],
            "bh_lottery_preference_category": ["low", "medium"],
            "trade_count_category":           ["medium", "low"],
            "strategy":                       ["value", "technical"],
            "bh_disposition_effect_category": ["medium", "low"],
        },
        # --- 40대 ---
        "male_40대_일반": {
            "bh_annual_turnover_category":    ["high", "medium"],
            "bh_lottery_preference_category": ["medium", "high"],
            "trade_count_category":           ["medium", "high"],
            "strategy":                       ["technical"],
            "bh_disposition_effect_category": ["medium", "high"],
        },
        "male_40대_고액": {
            "bh_annual_turnover_category":    ["medium"],
            "bh_lottery_preference_category": ["medium", "low"],
            "trade_count_category":           ["medium"],
            "strategy":                       ["technical", "value"],
            "bh_disposition_effect_category": ["medium"],
        },
        "female_40대_일반": {
            "bh_annual_turnover_category":    ["low", "medium"],
            "bh_lottery_preference_category": ["low"],
            "trade_count_category":           ["low", "medium"],
            "strategy":                       ["value", "technical"],
            "bh_disposition_effect_category": ["low", "medium"],
        },
        "female_40대_고액": {
            "bh_annual_turnover_category":    ["low"],
            "bh_lottery_preference_category": ["low"],
            "trade_count_category":           ["low"],
            "strategy":                       ["value"],
            "bh_disposition_effect_category": ["low"],
        },
        # --- 50대 ---
        "male_50대_일반": {
            "bh_annual_turnover_category":    ["medium", "high"],
            "bh_lottery_preference_category": ["medium"],
            "trade_count_category":           ["high", "medium"],
            "strategy":                       ["technical"],
            "bh_disposition_effect_category": ["high", "medium"],
        },
        "male_50대_고액": {
            "bh_annual_turnover_category":    ["medium"],
            "bh_lottery_preference_category": ["low", "medium"],
            "trade_count_category":           ["medium"],
            "strategy":                       ["technical", "value"],
            "bh_disposition_effect_category": ["medium"],
        },
        "female_50대_일반": {
            "bh_annual_turnover_category":    ["low"],
            "bh_lottery_preference_category": ["low"],
            "trade_count_category":           ["low", "medium"],
            "strategy":                       ["value"],
            "bh_disposition_effect_category": ["low", "medium"],
        },
        "female_50대_고액": {
            "bh_annual_turnover_category":    ["low"],
            "bh_lottery_preference_category": ["low"],
            "trade_count_category":           ["low"],
            "strategy":                       ["value"],
            "bh_disposition_effect_category": ["low"],
        },
        # --- 60대 ---
        "male_60대_일반": {
            "bh_annual_turnover_category":    ["low", "medium"],
            "bh_lottery_preference_category": ["low"],
            "trade_count_category":           ["low", "medium"],
            "strategy":                       ["value", "technical"],
            "bh_disposition_effect_category": ["medium", "low"],
        },
        "male_60대_고액": {
            "bh_annual_turnover_category":    ["low"],
            "bh_lottery_preference_category": ["low"],
            "trade_count_category":           ["medium", "low"],
            "strategy":                       ["value"],
            "bh_disposition_effect_category": ["medium"],
        },
        "female_60대_일반": {
            "bh_annual_turnover_category":    ["low"],
            "bh_lottery_preference_category": ["low"],
            "trade_count_category":           ["low"],
            "strategy":                       ["value"],
            "bh_disposition_effect_category": ["low"],
        },
        "female_60대_고액": {
            "bh_annual_turnover_category":    ["low"],
            "bh_lottery_preference_category": ["low"],
            "trade_count_category":           ["low"],
            "strategy":                       ["value"],
            "bh_disposition_effect_category": ["low"],
        },
        # --- 70대 ---
        "male_70대_일반": {
            "bh_annual_turnover_category":    ["low"],
            "bh_lottery_preference_category": ["low"],
            "trade_count_category":           ["low"],
            "strategy":                       ["value"],
            "bh_disposition_effect_category": ["low", "medium"],
        },
        "male_70대_고액": {
            "bh_annual_turnover_category":    ["low"],
            "bh_lottery_preference_category": ["low"],
            "trade_count_category":           ["low"],
            "strategy":                       ["value"],
            "bh_disposition_effect_category": ["low"],
        },
        "female_70대_일반": {
            "bh_annual_turnover_category":    ["low"],
            "bh_lottery_preference_category": ["low"],
            "trade_count_category":           ["low"],
            "strategy":                       ["value"],
            "bh_disposition_effect_category": ["low"],
        },
        # --- 80대+ ---
        "male_80대 이상_일반": {
            "bh_annual_turnover_category":    ["low"],
            "bh_lottery_preference_category": ["low"],
            "trade_count_category":           ["low"],
            "strategy":                       ["value"],
            "bh_disposition_effect_category": ["low"],
        },
    }
    return profiles.get(segment, profiles["male_60대_일반"])  # 미정의 세그먼트 fallback
```

### Phase 4: 가중 선택 알고리즘

세그먼트 프로파일을 완벽히 따르는 에이전트만 선발하는 것이 아니라, 세그먼트 특성에 가까울수록 높은 가중치를 부여하여 pool 전체에서 확률적으로 선발한다. 이 방식은 세그먼트 특성을 중점적으로 반영하면서도 다양한 행동 프로파일이 선발될 여지를 남겨, 시뮬레이션 내 에이전트 다양성을 자연스럽게 확보한다.

```python
def score_agent(agent: dict, preferred: dict) -> int:
    """
    에이전트가 세그먼트 프로파일과 얼마나 일치하는지를 점수로 환산한다.
    - 1순위 값 일치: +3점
    - 2순위 값 일치: +2점
    - 3순위 값 일치: +1점
    - 불일치: +0점 (선발 가능하지만 낮은 확률)
    최소 점수 1을 보장하여 모든 에이전트가 선발 가능하도록 한다.
    """
    score = 0
    for col, priority_values in preferred.items():
        agent_val = agent.get(col)
        for rank, val in enumerate(priority_values):
            if agent_val == val:
                score += max(1, 3 - rank)
                break
    return score + 1  # 최소 가중치 1 보장


def match_agents(pool: list[dict], slots: list[dict]) -> list[dict]:
    used_ids = set()
    selected = []

    for slot in slots:
        preferred = get_behavioral_profile(
            slot["age_group"], slot["gender"], slot["ini_cash"]
        )

        # 미선발 에이전트 전체가 후보 (다양성 보장)
        candidates = [a for a in pool if a["user_id"] not in used_ids]

        # 세그먼트 프로파일 일치도를 가중치로 환산
        weights = [score_agent(a, preferred) for a in candidates]

        # 가중 랜덤 선발 — 프로파일에 가까울수록 선발 확률이 높음
        selected_agent = dict(random.choices(candidates, weights=weights, k=1)[0])

        # 슬롯의 인구통계 값을 선발된 에이전트에 덮어씀
        # (gender, age, ini_cash는 pool 값이 아닌 고정 슬롯 값으로 대체)
        selected_agent["agent_id"] = slot["agent_id"]
        selected_agent["gender"]   = slot["gender"]
        selected_agent["age"]      = slot["age"]
        selected_agent["age_group"]= slot["age_group"]
        selected_agent["ini_cash"] = slot["ini_cash"]

        used_ids.add(slot["agent_id"])
        selected.append(selected_agent)

    return selected
```

### Phase 5: location 배정

```python
def assign_location() -> str:
    weights = {
        "경기": 29, "서울": 26, "부산": 6,  "인천": 5,  "경남": 5,
        "대구": 4,  "경북": 4,  "충남": 3,  "대전": 3,  "광주": 3,
        "전북": 2,  "충북": 2,  "울산": 2,  "전남": 2,  "강원": 2,
        "제주": 1,  "세종": 1,
    }
    return random.choices(list(weights.keys()), weights=list(weights.values()), k=1)[0]
```

### Phase 6: persona_prompt 생성

```python
def generate_persona_prompt(agent: dict) -> str:
    disposition_desc = {
        "high":   "수익이 나면 빠르게 매도하고 손실 시 추가 매수하는 경향(처분효과 높음)",
        "medium": "수익과 손실 상황 모두에서 비교적 균형 잡힌 판단을 하는 편",
        "low":    "수익은 오래 보유하고 손실 시 이성적으로 손절하는 편(처분효과 낮음)",
    }
    lottery_desc = {
        "high":   "고위험 고수익 복권형 자산을 선호",
        "medium": "적정 수준의 위험을 수용하는 편",
        "low":    "안정적이고 검증된 자산을 선호",
    }
    turnover_desc = {
        "high":   "자주 매매하며 단기 기회에 민감하게 반응",
        "medium": "중간 정도의 거래 빈도를 보임",
        "low":    "장기 보유를 선호하며 불필요한 매매를 자제",
    }
    strategy_desc = {
        "technical": "기술적 지표·추세·거래량·이동평균·돌파 신호를 기반으로 판단",
        "value":     "PE/PB 등 가치평가 지표·내재가치·성장성·저평가 여부를 기반으로 판단",
    }
    underdiv_desc = {
        "low":    "비교적 잘 분산된 포트폴리오를 유지하는 편",
        "medium": "특정 종목에 다소 집중하는 성향",
    }

    template = (
        "당신은 한국의 삼성전자 개인투자자입니다.\n"
        "성별은 {gender}, 나이는 {age}세, 거주 지역은 {location}입니다.\n"
        "투자자 유형은 {user_type}이며, 주요 투자 전략은 {strategy_d}입니다.\n"
        "처분효과 측면에서는 {disposition_d}.\n"
        "위험 자산 선호 측면에서는 {lottery_d}.\n"
        "거래 빈도 측면에서는 {turnover_d}.\n"
        "분산투자 측면에서는 {underdiv_d}.\n"
        "이번 실험에서는 삼성전자 단일 자산만 거래하며, "
        "초기에는 주식 없이 현금 {ini_cash:,}원만 보유한 상태로 시장에 진입합니다."
    )

    return template.format(
        gender       = "남성" if agent["gender"] == "male" else "여성",
        age          = agent["age"],
        location     = agent["location"],
        user_type    = agent["user_type"],
        strategy_d   = strategy_desc[agent["strategy"]],
        disposition_d= disposition_desc[agent["bh_disposition_effect_category"]],
        lottery_d    = lottery_desc[agent["bh_lottery_preference_category"]],
        turnover_d   = turnover_desc[agent["bh_annual_turnover_category"]],
        underdiv_d   = underdiv_desc[agent["bh_underdiversification_category"]],
        ini_cash     = agent["ini_cash"],
    )
```

---

## 12. 엣지 케이스 처리

**가중치 집중**: pool의 behavioral 분포가 특정 세그먼트 프로파일에 극히 드문 경우(예: 20대 남성 슬롯에 맞는 high turnover + high lottery 에이전트가 매우 적음), 해당 에이전트들이 여러 슬롯에 반복 선발될 수 없어(1인 1슬롯) 후반 슬롯의 가중치 분포가 달라질 수 있다. 이는 정상 동작이며, pool 전체가 선발 대상이므로 알고리즘은 중단되지 않는다. 실행 후 선발된 에이전트의 세그먼트별 평균 점수를 검증 리포트에 기록한다.

**미정의 세그먼트**: 고정 슬롯 리스트에 정의된 세그먼트만 존재하지만, 코드 안전성을 위해 profiles.get() fallback을 유지한다.

**location 편차**: 경기+서울(55명)은 실제 주주 분포(55.65%)를 정확히 반영하므로 조정하지 않는다. 독립 샘플링 특성상 ±3명 편차는 허용한다.

**30대 여성 슬롯 수**: 30대 여성이 18명 중 10명(56%)을 차지하여 pool에서 여성 30대 특성(낮은 turnover, value 전략 선호)을 가진 에이전트 수요가 높다. pool에서 low/medium turnover + value strategy 에이전트는 371+330=701명(turnover 기준) 중 상당수가 해당하므로 고갈 가능성은 낮다.

---

## 13. 전체 처리 함수 흐름

```
load_fixed_slots(fixed_slots_csv)
    → 100개 슬롯 (agent_id, gender, age, age_group, ini_cash) 로드
    ↓
load_pool(sys_1000_db)
    → 1000명 behavioral profile 로드
    ↓
for each slot:
    get_behavioral_profile(slot.age_group, slot.gender, slot.ini_cash)
        → 세그먼트 기준 preferred behavioral categories 반환
    ↓
match_agents(pool, slots)
    → score_agent(): 각 에이전트의 세그먼트 일치도를 점수로 환산
    → random.choices(candidates, weights): 가중 확률 선발 (다양성 + 중점 선발 동시 확보)
    → used_ids로 중복 방지 (1인 1슬롯)
    → 슬롯의 gender, age, ini_cash를 선발 에이전트에 덮어씀
    ↓
for each selected_agent:
    assign_location()
        → Persona_Report_1.pdf 지역 분포 기반 가중 샘플링
    ↓
    generate_persona_prompt(agent)
        → sys_prompt + prompt + self_description 통합 텍스트
    ↓
save_sys_100(selected_agents, output_db)
    ↓
verify_distribution(sys_100.db)
    → 성별·연령대·자산군·지역 분포 검증 리포트
```

---

## 14. DB 기록 방식 — sys_100 테이블 참고 형식

```
테이블명: agents (sys_100.db)

agent_id                         TEXT  PRIMARY KEY   A001 ~ A100
user_type                        TEXT   일반 개미 / 팔로워 적은 인플루언서 / 유명 인플루언서
gender                           TEXT   male / female
age                              INTEGER  구체적 나이 (고정 슬롯에서 부여)
location                         TEXT   한국 시도명 (예: 경기, 서울)
bh_disposition_effect_category   TEXT   low / medium / high
bh_lottery_preference_category   TEXT   low / medium / high
bh_total_return_category         TEXT   low / medium / high
bh_annual_turnover_category      TEXT   low / medium / high
bh_underdiversification_category TEXT   low / medium
trade_count_category             TEXT   low / medium / high
strategy                         TEXT   technical / value
trad_pro                         INTEGER  0 (전 에이전트 고정)
fol_ind                          TEXT   '{"전기전자", "반도체"}' (전 에이전트 고정)
ini_cash                         INTEGER  고정 슬롯에서 부여 (1억 또는 10억)
news_depth                       INTEGER  뉴스 정보 접근 깊이 (0=headline only, 1=10개 요약, 2=심층 검색)
persona_prompt                   TEXT   통합 정적 정체성 텍스트

--- 제거 컬럼 (동적 → portfolio_state 테이블) ---
current_cash, cur_positions, total_value, total_return, return_rate,
stock_returns, yest_returns, initial_positions, created_at,
sys_prompt, prompt, self_description
```

시뮬레이션 시작 시 ini_cash를 기반으로 portfolio_state_t000을 생성한다.

```
초기 portfolio_state_t000 (전 에이전트):
  보유 주식: 없음
  보유 현금: ini_cash
  총 자산:   ini_cash
  누적 수익: 0
  전일 수익: null
```

---

## 15. 검증 계획

**인구통계 분포 검증.** 최종 100명의 성별(남 43명, 여 57명), 연령대(7개 그룹), 자산군(1억 90명, 10억 10명)이 고정 슬롯 정의와 정확히 일치하는지 확인한다. 고정 슬롯을 그대로 사용하므로 편차는 0이어야 한다.

**세그먼트 behavioral coherence 검증.** 각 세그먼트에 배정된 에이전트들의 behavioral category 분포가 Section 6에서 정의한 우선순위 방향과 일치하는지 확인한다. 예를 들어 남성_30대_일반 슬롯 7명의 과반 이상이 bh_annual_turnover=high를 가져야 한다.

**세그먼트 간 방향성 검증.** 20대+30대 남성 슬롯의 평균 turnover가 60대+70대 슬롯보다 높아야 하며, 여성 슬롯의 평균 turnover가 동일 연령대 남성 슬롯보다 낮아야 한다.

**세그먼트 일치 점수 분포 확인.** 각 슬롯에서 선발된 에이전트의 score_agent 평균 점수를 세그먼트별로 집계한다. 특정 세그먼트의 평균 점수가 다른 세그먼트에 비해 현저히 낮은 경우(pool의 해당 프로파일이 희소), 세그먼트 우선순위 기준 완화 여부를 검토한다.

**persona_prompt 품질 확인.** 빈 값, 포매팅 오류, ini_cash 정수 반영 오류, 성별 변환 오류를 전수 확인한다.

---

*통계 근거: KSD SEIBro 삼성전자 주주 통계(Persona_Report_1.pdf, 2025/12/31). 행동 편향 근거: Sui & Wang (2025), "Stakes and Investor Behaviors"(Persona_Report_2.pdf). 에이전트 초기화 및 portfolio_state 관리는 Overall_Framework_First.md 참조.*
