from __future__ import annotations

import json
from typing import Any

import config
from twinmarket_kr.agents.fundamental_agent import FundamentalAgent
from twinmarket_kr.agents.memory_agent import MemoryAgent
from twinmarket_kr.agents.news_agent import NewsAgent
from twinmarket_kr.core.collect_context import collect_context
from twinmarket_kr.llm.belief import update_belief
from twinmarket_kr.llm.client import OpenRouterClient
from twinmarket_kr.llm.decision import build_trading_constraints, make_decision


def _portfolio_numbers(memory_agent: MemoryAgent, agent_id: str, turn: int) -> tuple[float, int]:
    row = memory_agent._latest_portfolio(agent_id, before_or_at_turn=turn)  # internal read for orchestration
    if row is None:
        return 0.0, 0
    current_quantity = 0
    for pos in json.loads(row["positions"]):
        if pos.get("stock_code") == config.STOCK_CODE:
            current_quantity = int(pos.get("quantity", 0))
            break
    return float(row["cash"]), current_quantity


async def run_agent_turn(
    agent: dict[str, Any],
    *,
    turn: int,
    date: str,
    memory_agent: MemoryAgent,
    fundamental_agent: FundamentalAgent,
    news_agent: NewsAgent,
    client: OpenRouterClient | None = None,
) -> dict[str, Any] | None:
    today_context = collect_context(
        agent,
        turn=turn,
        date=date,
        memory_agent=memory_agent,
        fundamental_agent=fundamental_agent,
        news_agent=news_agent,
    )
    today_belief = await update_belief(
        agent,
        today_context,
        client=client,
        memory=memory_agent,
    )
    current_price = float(today_context["market_features"]["close"])
    available_cash, current_quantity = _portfolio_numbers(memory_agent, agent["agent_id"], turn - 1)
    constraints = build_trading_constraints(
        available_cash=available_cash,
        current_quantity=current_quantity,
        current_price=current_price,
    )
    decision = await make_decision(
        agent,
        today_belief,
        today_context["portfolio_summary"],
        constraints,
        client=client,
    )
    memory_agent.append_trade_log(
        {
            "agent_id": agent["agent_id"],
            "turn": turn,
            "date": date,
            "action": decision["action"],
            "stock_code": config.STOCK_CODE,
            "quantity": decision["quantity"],
            "fee": 0,
            "action_reason": decision["reason"],
            "risk_control": decision["risk_control"],
        }
    )
    if decision["action"] == "hold" or decision["quantity"] <= 0:
        return None
    return {
        "stock_code": config.STOCK_CODE,
        "user_id": agent["agent_id"],
        "direction": decision["action"],
        "quantity": decision["quantity"],
        "price": decision["price"] if decision["order_type"] == "limit" else 0,
        "timestamp": float(turn),
        "reason": decision["reason"],
    }
