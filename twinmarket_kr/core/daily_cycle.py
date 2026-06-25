from __future__ import annotations

import json
import asyncio
from typing import Any

import config
from twinmarket_kr.agents.fundamental_agent import FundamentalAgent
from twinmarket_kr.agents.memory_agent import MemoryAgent
from twinmarket_kr.agents.news_agent import NewsAgent
from twinmarket_kr.core.collect_context import collect_context
from twinmarket_kr.llm.analysis import analyze_market, depth2_post_search, depth2_pre_search, interpret_news
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
    market_features_date: str | None = None,
    news_max_date: str | None = None,
    execution_date: str | None = None,
    information_mode: str = "same_day",
    decision_space: str = "buy_hold_sell",
    memory_agent: MemoryAgent,
    fundamental_agent: FundamentalAgent,
    news_agent: NewsAgent,
    client: OpenRouterClient | None = None,
    event_logger: Any | None = None,
    db_write_lock: asyncio.Lock | None = None,
) -> dict[str, Any] | None:
    today_context = collect_context(
        agent,
        turn=turn,
        date=date,
        market_features_date=market_features_date,
        news_max_date=news_max_date,
        execution_date=execution_date,
        information_mode=information_mode,
        memory_agent=memory_agent,
        fundamental_agent=fundamental_agent,
        news_agent=news_agent,
    )
    today_context["news_context"] = news_agent.expand_context_from_selection(
        base_context=today_context["news_context"],
        current_date=today_context["news_max_date"],
    )
    depth2_flow = None
    if int(agent.get("news_depth") if agent.get("news_depth") is not None else 1) >= 2:
        pre_search = await depth2_pre_search(
            agent,
            today_context["news_context"],
            client=client,
        )
        search_results = []
        post_search = {
            "new_findings": "",
            "view_change": "유지",
            "view_change_detail": "추가 검색을 수행하지 않았습니다.",
            "unresolved_questions": [],
        }
        if pre_search.get("search_keywords"):
            search_results = news_agent.search_news_flat(
                keywords=list(pre_search.get("search_keywords") or []),
                current_date=today_context["news_max_date"],
                top_n=10,
            )
            post_search = await depth2_post_search(
                agent,
                today_context["news_context"],
                search_results,
                pre_search,
                client=client,
            )
        depth2_flow = {
            "step1_base": {
                "headline_count": len(today_context["news_context"].get("daily_titles") or []),
                "summary_count": len(today_context["news_context"].get("read_contents") or []),
            },
            "step2_pre_search_thinking": pre_search,
            "step3_search": {
                "keywords": list(pre_search.get("search_keywords") or []),
                "result_count": len(search_results),
            },
            "step4_post_search_thinking": post_search,
        }
        today_context["news_context"]["search_results"] = search_results
        today_context["news_context"]["search_read_contents"] = search_results
        today_context["news_context"]["depth2_flow"] = depth2_flow
    news_interpretation = await interpret_news(
        agent,
        today_context["news_context"],
        client=client,
    )
    today_context["news_interpretation"] = news_interpretation
    today_belief = await update_belief(
        agent,
        today_context,
        client=client,
        memory=None,
    )
    if db_write_lock is not None:
        async with db_write_lock:
            memory_agent.save_belief(today_belief)
    else:
        memory_agent.save_belief(today_belief)
    current_price = float(today_context["market_features"]["close"])
    available_cash, current_quantity = _portfolio_numbers(memory_agent, agent["agent_id"], turn - 1)
    constraints = build_trading_constraints(
        available_cash=available_cash,
        current_quantity=current_quantity,
        current_price=current_price,
        allow_hold=decision_space != "buy_sell_only",
    )
    market_analysis = await analyze_market(
        agent,
        today_belief=today_belief,
        market_features=today_context["market_features"],
        portfolio_summary=today_context["portfolio_summary"],
        news_interpretation=news_interpretation,
        client=client,
    )
    decision = await make_decision(
        agent,
        today_belief,
        market_analysis,
        today_context["portfolio_summary"],
        constraints,
        allow_hold=decision_space != "buy_sell_only",
        client=client,
    )
    trade_log = {
        "agent_id": agent["agent_id"],
        "turn": turn,
        "date": execution_date or date,
        "action": decision["action"],
        "stock_code": config.STOCK_CODE,
        "quantity": decision["quantity"],
        "fee": 0,
        "action_reason": decision["reason"],
        "risk_control": decision["risk_control"],
        "order_type": decision["order_type"],
        "submitted_price": decision["price"],
        "status": "pending" if decision["action"] != "hold" and decision["quantity"] > 0 else "not_submitted",
        "filled_quantity": 0,
    }
    if db_write_lock is not None:
        async with db_write_lock:
            memory_agent.append_trade_log(trade_log)
    else:
        memory_agent.append_trade_log(trade_log)
    order = None
    if decision["action"] != "hold" and decision["quantity"] > 0:
        order = {
            "stock_code": config.STOCK_CODE,
            "user_id": agent["agent_id"],
            "direction": decision["action"],
            "quantity": decision["quantity"],
            "price": decision["price"],
            "timestamp": float(turn),
            "reason": decision["reason"],
            "decision_date": today_context["decision_date"],
            "market_features_date": today_context["market_features_date"],
            "news_max_date": today_context["news_max_date"],
            "execution_date": today_context["execution_date"],
            "information_mode": today_context["information_mode"],
        }
    if event_logger is not None:
        event_logger.log_agent_turn(
            agent=agent,
            turn=turn,
            date=date,
            context=today_context,
            news_interpretation=news_interpretation,
            belief=today_belief,
            market_analysis=market_analysis,
            decision=decision,
            order=order,
            depth2_flow=depth2_flow,
        )
    return order
