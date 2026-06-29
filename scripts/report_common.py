from __future__ import annotations

from collections import Counter
from typing import Any


SYSTEM_USERS = {"COUNTERSIDE", "INSTITUTIONAL"}


def num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def pick_representative_agents(
    agent_ids: list[str],
    *,
    final_states: dict[str, dict[str, Any]] | None = None,
    order_rows: list[dict[str, Any]] | None = None,
    fill_rows: list[dict[str, Any]] | None = None,
    community_posts: list[dict[str, Any]] | None = None,
    community_interactions: list[dict[str, Any]] | None = None,
    limit: int = 4,
) -> tuple[list[str], dict[str, str]]:
    """Pick a compact set of agents that still explains most of the run."""
    final_states = final_states or {}
    order_rows = order_rows or []
    fill_rows = fill_rows or []
    community_posts = community_posts or []
    community_interactions = community_interactions or []

    if not agent_ids or limit <= 0:
        return [], {}

    selected: list[str] = []
    reasons: dict[str, str] = {}

    def add(agent_id: str, reason: str) -> None:
        if agent_id and agent_id in agent_ids and agent_id not in selected and len(selected) < limit:
            selected.append(agent_id)
            reasons[agent_id] = reason

    ranked_returns = sorted(
        (
            (
                agent_id,
                num(
                    final_states.get(agent_id, {}).get(
                        "return_rate_marked_final",
                        final_states.get(agent_id, {}).get("total_return_rate", 0),
                    )
                ),
            )
            for agent_id in agent_ids
        ),
        key=lambda item: (-item[1], item[0]),
    )
    for agent_id, value in ranked_returns[:2]:
        add(agent_id, f"최종 평가 수익률 상위권({value * 100:.2f}%)")

    impact = Counter()
    for row in order_rows:
        agent_id = str(row.get("agent_id") or row.get("user_id") or "")
        if agent_id in SYSTEM_USERS:
            continue
        impact[agent_id] += abs(num(row.get("quantity"))) * max(num(row.get("price")), 1)
    for row in fill_rows:
        agent_id = str(row.get("agent_id") or row.get("user_id") or "")
        if agent_id in SYSTEM_USERS:
            continue
        impact[agent_id] += abs(num(row.get("executed_quantity"))) * max(num(row.get("executed_price")), 1) * 2
    if impact:
        agent_id, value = sorted(impact.items(), key=lambda item: (-item[1], item[0]))[0]
        add(agent_id, f"주문/체결 금액 영향도 최상위({value:,.0f})")

    community_activity = Counter()
    for row in community_posts:
        community_activity[str(row.get("agent_id") or "")] += 2
    for row in community_interactions:
        if row.get("post_id"):
            community_activity[str(row.get("agent_id") or "")] += 1
    if community_activity:
        agent_id, value = sorted(community_activity.items(), key=lambda item: (-item[1], item[0]))[0]
        add(agent_id, f"커뮤니티 참여도 최상위({int(value)}점)")

    combined = Counter()
    for agent_id, value in ranked_returns:
        combined[agent_id] += value * 100
    for agent_id, value in impact.items():
        combined[agent_id] += value / 10_000_000
    for agent_id, value in community_activity.items():
        combined[agent_id] += value
    for agent_id in agent_ids:
        combined[agent_id] += 0

    for agent_id, value in sorted(combined.items(), key=lambda item: (-item[1], item[0])):
        add(agent_id, f"복합 점수 보완 선정({value:.2f})")

    return selected, reasons
