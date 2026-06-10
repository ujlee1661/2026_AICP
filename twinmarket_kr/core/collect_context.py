from __future__ import annotations

from typing import Any

import config
from twinmarket_kr.agents.fundamental_agent import FundamentalAgent
from twinmarket_kr.agents.memory_agent import MemoryAgent
from twinmarket_kr.agents.news_agent import NewsAgent


def collect_context(
    agent: dict[str, Any],
    *,
    turn: int,
    date: str,
    memory_agent: MemoryAgent,
    fundamental_agent: FundamentalAgent,
    news_agent: NewsAgent,
) -> dict[str, Any]:
    previous_belief = memory_agent.get_previous_belief(agent["agent_id"], turn)
    portfolio_summary = memory_agent.get_portfolio_summary(agent["agent_id"], turn - 1)
    action_reason = memory_agent.get_last_action_reason(agent["agent_id"])
    news_depth = 1 if agent.get("news_depth") is None else int(agent["news_depth"])
    news_context = news_agent.build_base_context(date, news_depth)
    market_features = fundamental_agent.get_market_features(date, config.STOCK_CODE)
    return {
        "agent_id": agent["agent_id"],
        "turn": turn,
        "date": date,
        "previous_belief": previous_belief,
        "action_reason": action_reason,
        "portfolio_summary": portfolio_summary,
        "news_context": news_context,
        "market_features": market_features,
    }
