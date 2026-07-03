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
    market_features_date: str | None = None,
    news_max_date: str | None = None,
    news_start_date: str | None = None,
    news_start_time: str | None = None,
    news_end_time: str | None = None,
    execution_date: str | None = None,
    information_mode: str = "pre_close_cutoff",
    subturn: str = "full",
    open_price: float | None = None,
    mid_price: float | None = None,
    previous_close: float | None = None,
    execution_reference: str | None = None,
    memory_agent: MemoryAgent,
    fundamental_agent: FundamentalAgent,
    news_agent: NewsAgent,
    community_agent: Any | None = None,
) -> dict[str, Any]:
    market_date = market_features_date or date
    news_date = news_max_date or date
    exec_date = execution_date or date
    previous_belief = memory_agent.get_previous_belief(agent["agent_id"], turn)
    portfolio_summary = memory_agent.get_portfolio_summary(agent["agent_id"], turn - 1)
    raw_history = memory_agent.get_recent_order_history(agent["agent_id"], last_n=5, current_date=date)
    order_history = _format_order_history(raw_history)
    action_reason = memory_agent.get_last_action_reason(agent["agent_id"])
    news_depth = 1 if agent.get("news_depth") is None else int(agent["news_depth"])
    if news_start_date and news_start_time and news_end_time:
        news_context = news_agent.build_window_context(
            start_date=news_start_date,
            start_time=news_start_time,
            end_date=news_date,
            end_time=news_end_time,
            news_depth=news_depth,
        )
    else:
        news_context = news_agent.build_base_context(news_date, news_depth)
    market_features = fundamental_agent.get_market_features(market_date, config.STOCK_CODE)
    market_features["as_of_date"] = market_date
    market_features["subturn"] = subturn
    if previous_close is not None:
        market_features["previous_close"] = previous_close
    if open_price is not None:
        market_features["open_price"] = open_price
    if mid_price is not None:
        market_features["mid_price"] = mid_price
    if execution_reference:
        market_features["execution_reference"] = execution_reference
    if subturn == "am" and open_price is not None:
        market_features["reference_price"] = open_price
        market_features["close"] = open_price
        if previous_close:
            market_features["intraday_return_from_prev_close"] = (open_price - previous_close) / previous_close
    elif subturn == "pm" and mid_price is not None:
        market_features["reference_price"] = mid_price
        market_features["close"] = mid_price
        if open_price:
            market_features["intraday_return_from_open"] = (mid_price - open_price) / open_price
    community_log = None
    if community_agent is not None and turn > 1:
        if config.ENABLE_COMMUNITY and news_depth >= 1:
            community_turn = turn - 2 if subturn == "pm" else turn - 1
            if community_turn > 0:
                community_log = community_agent.get_community_log(str(agent["agent_id"]), community_turn)
    return {
        "agent_id": agent["agent_id"],
        "turn": turn,
        "date": date,
        "decision_date": date,
        "market_features_date": market_date,
        "news_start_date": news_start_date,
        "news_start_time": news_start_time,
        "news_max_date": news_date,
        "news_end_time": news_end_time,
        "execution_date": exec_date,
        "information_mode": information_mode,
        "subturn": subturn,
        "previous_belief": previous_belief,
        "action_reason": action_reason,
        "portfolio_summary": portfolio_summary,
        "order_history": order_history,
        "news_context": news_context,
        "market_features": market_features,
        "community_log": community_log,
    }


def _format_order_history(raw_history: list[dict[str, Any]]) -> str:
    if not raw_history:
        return "이전 주문 이력 없음"
    lines = []
    for item in raw_history:
        submitted = item.get("submitted_price")
        actual_close = item.get("actual_close")
        executed = item.get("executed_price")
        submitted_text = f"{float(submitted):,.0f}원" if submitted else "N/A"
        close_text = f"{float(actual_close):,.0f}원" if actual_close else "N/A"
        if item.get("filled"):
            exec_text = f"{float(executed):,.0f}원" if executed else "체결"
            lines.append(
                f"{item['date']} turn {item['turn']}: {item['action']} {submitted_text} 제출 -> "
                f"체결 (당일 종가 {close_text}, 체결가 {exec_text})"
            )
        elif submitted and actual_close:
            deviation = (float(submitted) - float(actual_close)) / float(actual_close) * 100
            lines.append(
                f"{item['date']} turn {item['turn']}: {item['action']} {submitted_text} 제출 -> "
                f"미체결 (당일 종가 {close_text}, 편차 {deviation:+.1f}%)"
            )
        else:
            lines.append(f"{item['date']} turn {item['turn']}: {item['action']} {submitted_text} 제출 -> 미체결")
    return "\n".join(lines)
