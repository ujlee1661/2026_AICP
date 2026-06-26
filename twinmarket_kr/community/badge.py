from __future__ import annotations

from typing import Any

import config
from twinmarket_kr.agents.memory_agent import MemoryAgent
from twinmarket_kr.db.connection import connect


def calculate_badges(
    agents: list[dict[str, Any]],
    memory_agent: MemoryAgent,
    turn: int,
    db_path: str,
) -> dict[str, list[str]]:
    badges: dict[str, list[str]] = {str(agent["agent_id"]): [] for agent in agents}
    n = len(agents)
    if n == 0:
        return badges

    returns: list[tuple[str, float]] = []
    assets: list[tuple[str, float]] = []
    for agent in agents:
        agent_id = str(agent["agent_id"])
        row = memory_agent._latest_portfolio(agent_id, before_or_at_turn=turn)
        if row is None:
            continue
        total_value = float(row["total_value"])
        initial_cash = float(agent.get("ini_cash") or config.INI_CASH_SMALL)
        return_rate = (total_value - initial_cash) / initial_cash if initial_cash else 0.0
        returns.append((agent_id, return_rate))
        assets.append((agent_id, total_value))

    for agent_id, _ in _top_percentile(returns, n, config.BADGE_TOP_RETURN_PERCENTILE):
        badges.setdefault(agent_id, []).append("상위 수익자")
    for agent_id, _ in _top_percentile(assets, n, config.BADGE_TOP_ASSET_PERCENTILE):
        badges.setdefault(agent_id, []).append("자산가")

    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT agent_id, SUM(like_count) AS total_likes
            FROM community_posts
            GROUP BY agent_id
            """
        ).fetchall()
    like_counts = [(str(row["agent_id"]), int(row["total_likes"] or 0)) for row in rows]
    for agent_id, _ in _top_percentile(like_counts, len(like_counts), config.BADGE_INFLUENCER_PERCENTILE):
        if agent_id in badges:
            badges[agent_id].append("커뮤니티 인플루언서")

    return badges


def _top_percentile(values: list[tuple[str, float]], total_count: int, percentile: int) -> list[tuple[str, float]]:
    if not values or total_count <= 0:
        return []
    cutoff = max(1, int(total_count * percentile / 100))
    return sorted(values, key=lambda item: (-item[1], item[0]))[:cutoff]
