from __future__ import annotations

import csv
import json
import random
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import config
from twinmarket_kr.db.connection import connect, init_agents_db
from twinmarket_kr.persona.segments import get_behavioral_profile, segment_key


VALUE_MAP = {
    "高": "high",
    "中": "medium",
    "低": "low",
    "技术面": "technical",
    "基本面": "value",
    "普通股民": "ordinary",
    "小博主": "small_influencer",
    "大V": "big_influencer",
}

BEHAVIORAL_COLUMNS = [
    "user_type",
    "bh_disposition_effect_category",
    "bh_lottery_preference_category",
    "bh_total_return_category",
    "bh_annual_turnover_category",
    "bh_underdiversification_category",
    "trade_count_category",
    "strategy",
    "trad_pro",
    "fol_ind",
    "sys_prompt",
    "prompt",
    "self_description",
]

LOCATION_WEIGHTS = {
    "경기": 29,
    "서울": 26,
    "부산": 6,
    "인천": 5,
    "경남": 5,
    "대구": 4,
    "경북": 4,
    "충남": 3,
    "대전": 3,
    "광주": 3,
    "전북": 2,
    "충북": 2,
    "울산": 2,
    "전남": 2,
    "강원": 2,
    "제주": 1,
    "세종": 1,
}


def _map_value(value: object) -> object:
    if value is None:
        return value
    if isinstance(value, str):
        return VALUE_MAP.get(value.strip(), value.strip())
    return value


def _normalize_agent(row: dict) -> dict:
    agent = {"user_id": str(row["user_id"])}
    for col in BEHAVIORAL_COLUMNS:
        agent[col] = _map_value(row.get(col))
    agent["trad_pro"] = int(agent.get("trad_pro") or 0)
    agent["fol_ind"] = json.dumps(["전기전자", "반도체"], ensure_ascii=False)
    return agent


def load_pool(source: Path | None = None) -> list[dict]:
    source = source or (config.SYS_1000_DB if config.SYS_1000_DB.exists() else config.SYS_1000_CSV)
    if not source.exists():
        raise FileNotFoundError(f"sys_1000 input not found: {source}")

    if source.suffix == ".csv":
        with source.open(encoding="utf-8-sig", newline="") as f:
            return [_normalize_agent(row) for row in csv.DictReader(f)]

    conn = sqlite3.connect(source)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM Profiles").fetchall()
        return [_normalize_agent(dict(row)) for row in rows]
    finally:
        conn.close()


def score_agent(agent: dict, preferred: dict[str, list[str]]) -> int:
    score = 0
    for col, priority_values in preferred.items():
        agent_val = agent.get(col)
        for rank, val in enumerate(priority_values):
            if agent_val == val:
                score += max(1, 3 - rank)
                break
    return score + 1


def assign_location(rng: random.Random) -> str:
    return rng.choices(
        list(LOCATION_WEIGHTS.keys()),
        weights=list(LOCATION_WEIGHTS.values()),
        k=1,
    )[0]


def assign_news_depth(index: int, total: int) -> int:
    n_depth2 = round(total * config.NEWS_DEPTH2_RATIO)
    return 2 if index >= total - n_depth2 else 1


def assign_depth0_agents(agents: list[dict], rng: random.Random) -> None:
    depth1_agents = [agent for agent in agents if int(agent["news_depth"]) == 1]
    count = min(config.NEWS_DEPTH0_COUNT, len(depth1_agents))
    for agent in rng.sample(depth1_agents, count):
        agent["news_depth"] = 0


def generate_persona_prompt(agent: dict) -> str:
    disposition_desc = {
        "high": "수익이 나면 빠르게 매도하고 손실 시 추가 매수하는 경향이 강합니다",
        "medium": "수익과 손실 상황 모두에서 비교적 균형 잡힌 판단을 하는 편입니다",
        "low": "수익은 오래 보유하고 손실 시 이성적으로 손절하는 편입니다",
    }
    lottery_desc = {
        "high": "고위험 고수익 기회를 적극적으로 선호합니다",
        "medium": "적정 수준의 위험을 수용합니다",
        "low": "안정적이고 검증된 자산을 선호합니다",
    }
    return_desc = {
        "high": "과거 투자 성과가 좋은 편입니다",
        "medium": "과거 투자 성과가 평균적인 편입니다",
        "low": "과거 투자 성과가 낮은 편입니다",
    }
    turnover_desc = {
        "high": "자주 매매하며 단기 기회에 민감하게 반응합니다",
        "medium": "중간 정도의 거래 빈도를 보입니다",
        "low": "장기 보유를 선호하며 불필요한 매매를 자제합니다",
    }
    count_desc = {
        "high": "거래 실행 빈도가 높습니다",
        "medium": "거래 실행 빈도가 보통입니다",
        "low": "거래 실행 빈도가 낮습니다",
    }
    strategy_desc = {
        "technical": "기술적 지표, 추세, 거래량, 이동평균, 돌파 신호를 기반으로 판단합니다",
        "value": "PE/PB 등 가치평가 지표, 내재가치, 성장성, 저평가 여부를 기반으로 판단합니다",
    }
    underdiv_desc = {
        "low": "비교적 잘 분산된 포트폴리오를 유지하는 편입니다",
        "medium": "특정 종목에 다소 집중하는 성향이 있습니다",
    }
    user_type_desc = {
        "ordinary": "일반 개인투자자",
        "small_influencer": "팔로워가 적은 투자 인플루언서",
        "big_influencer": "영향력이 큰 투자 인플루언서",
    }
    gender_ko = "남성" if agent["gender"] == "male" else "여성"
    depth_desc = {
        0: "뉴스는 당일 헤드라인만 훑고 세부 요약은 확인하지 않는 헤드라인 스캔형입니다.",
        1: "뉴스는 당일 헤드라인과 10개 요약본을 모두 확인하는 요약 전독형입니다.",
        2: "뉴스는 당일 헤드라인과 요약본을 확인한 뒤 필요하면 최근 7일 뉴스까지 추가 검색하는 심층 탐색형입니다.",
    }
    depth_line = depth_desc.get(int(agent["news_depth"]), depth_desc[1])
    return (
        "당신은 한국의 삼성전자 개인투자자입니다.\n"
        f"성별은 {gender_ko}, 나이는 {agent['age']}세, 거주 지역은 {agent['location']}입니다.\n"
        f"투자자 유형은 {user_type_desc.get(agent['user_type'], agent['user_type'])}이며, "
        f"주요 투자 전략은 {strategy_desc[agent['strategy']]}\n"
        f"처분효과 측면에서는 {disposition_desc[agent['bh_disposition_effect_category']]}.\n"
        f"위험 자산 선호 측면에서는 {lottery_desc[agent['bh_lottery_preference_category']]}.\n"
        f"성과 경험 측면에서는 {return_desc[agent['bh_total_return_category']]}.\n"
        f"거래 회전율 측면에서는 {turnover_desc[agent['bh_annual_turnover_category']]}.\n"
        f"거래 빈도 측면에서는 {count_desc[agent['trade_count_category']]}.\n"
        f"분산투자 측면에서는 {underdiv_desc[agent['bh_underdiversification_category']]}.\n"
        f"{depth_line}\n"
        "이번 실험에서는 삼성전자 단일 자산만 거래하며, "
        f"초기에는 주식 없이 현금 {agent['ini_cash']:,}원만 보유한 상태로 시장에 진입합니다."
    )


def match_agents(pool: list[dict], slots: list[dict], seed: int = config.RANDOM_SEED) -> list[dict]:
    if len(pool) < len(slots):
        raise ValueError(f"pool has {len(pool)} agents but {len(slots)} slots are required")

    rng = random.Random(seed)
    used_source_ids: set[str] = set()
    selected: list[dict] = []

    for index, slot in enumerate(slots):
        preferred = get_behavioral_profile(slot["age_group"], slot["gender"], slot["ini_cash"])
        candidates = [agent for agent in pool if agent["user_id"] not in used_source_ids]
        weights = [score_agent(agent, preferred) for agent in candidates]
        chosen = dict(rng.choices(candidates, weights=weights, k=1)[0])
        chosen["source_user_id"] = chosen.pop("user_id")
        chosen["agent_id"] = slot["agent_id"]
        chosen["gender"] = slot["gender"]
        chosen["age"] = slot["age"]
        chosen["age_group"] = slot["age_group"]
        chosen["ini_cash"] = slot["ini_cash"]
        chosen["location"] = assign_location(rng)
        chosen["news_depth"] = assign_news_depth(index, len(slots))
        chosen["segment_key"] = segment_key(slot["age_group"], slot["gender"], slot["ini_cash"])
        chosen["match_score"] = score_agent(chosen, preferred)
        chosen["persona_prompt"] = generate_persona_prompt(chosen)
        used_source_ids.add(chosen["source_user_id"])
        selected.append(chosen)

    assign_depth0_agents(selected, rng)
    for agent in selected:
        agent["persona_prompt"] = generate_persona_prompt(agent)

    return selected


def save_sys_100(agents: Iterable[dict], output_db: Path = config.SYS_100_DB) -> None:
    init_agents_db(output_db)
    columns = [
        "agent_id",
        "source_user_id",
        "user_type",
        "gender",
        "age",
        "age_group",
        "location",
        "bh_disposition_effect_category",
        "bh_lottery_preference_category",
        "bh_total_return_category",
        "bh_annual_turnover_category",
        "bh_underdiversification_category",
        "trade_count_category",
        "strategy",
        "trad_pro",
        "fol_ind",
        "ini_cash",
        "news_depth",
        "segment_key",
        "match_score",
        "persona_prompt",
    ]
    placeholders = ", ".join(["?"] * len(columns))
    sql = f"INSERT INTO agents ({', '.join(columns)}) VALUES ({placeholders})"
    with connect(output_db) as conn:
        conn.executemany(sql, [[agent[col] for col in columns] for agent in agents])
        conn.commit()


def verify_distribution(agents: list[dict]) -> dict:
    gender = Counter(agent["gender"] for agent in agents)
    age_group = Counter(agent["age_group"] for agent in agents)
    cash = Counter(agent["ini_cash"] for agent in agents)
    depth = Counter(agent["news_depth"] for agent in agents)
    prompt_errors = [agent["agent_id"] for agent in agents if not agent.get("persona_prompt")]

    turnover_rank = {"low": 1, "medium": 2, "high": 3}
    young_male = [
        turnover_rank[agent["bh_annual_turnover_category"]]
        for agent in agents
        if agent["gender"] == "male" and agent["age_group"] in {"20대", "30대"}
    ]
    senior = [
        turnover_rank[agent["bh_annual_turnover_category"]]
        for agent in agents
        if agent["age_group"] in {"60대", "70대", "80대 이상"}
    ]
    segment_scores: dict[str, list[int]] = defaultdict(list)
    for agent in agents:
        segment_scores[agent["segment_key"]].append(agent["match_score"])

    expected = {
        "gender": {"male": 43, "female": 57},
        "age_group": {"20대": 9, "30대": 18, "40대": 23, "50대": 26, "60대": 17, "70대": 6, "80대 이상": 1},
        "cash": {config.INI_CASH_SMALL: 90, config.INI_CASH_LARGE: 10},
    }
    return {
        "count": len(agents),
        "gender": dict(gender),
        "age_group": dict(age_group),
        "cash": dict(cash),
        "news_depth": dict(depth),
        "distribution_pass": dict(gender) == expected["gender"]
        and dict(age_group) == expected["age_group"]
        and dict(cash) == expected["cash"],
        "prompt_errors": prompt_errors,
        "young_male_avg_turnover": round(sum(young_male) / len(young_male), 3) if young_male else None,
        "senior_avg_turnover": round(sum(senior) / len(senior), 3) if senior else None,
        "segment_avg_scores": {
            key: round(sum(values) / len(values), 3) for key, values in sorted(segment_scores.items())
        },
    }
