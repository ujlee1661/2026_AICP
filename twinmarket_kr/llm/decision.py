from __future__ import annotations

import json
from typing import Any

import config
from twinmarket_kr.llm.belief import load_prompt
from twinmarket_kr.llm.client import OpenRouterClient, response_content


DECISION_KEYS = ("action", "quantity", "order_type", "price", "reason", "risk_control")


def build_trading_constraints(
    *,
    available_cash: float,
    current_quantity: int,
    current_price: float,
    min_order_unit: int = config.MIN_ORDER_UNIT,
    max_single_trade_cash_ratio: float = config.MAX_SINGLE_TRADE_CASH_RATIO,
    allow_hold: bool = True,
) -> dict[str, Any]:
    usable_cash = max(0.0, available_cash * max_single_trade_cash_ratio)
    max_buy_quantity = int(usable_cash // current_price) if current_price > 0 else 0
    return {
        "available_cash": available_cash,
        "max_single_trade_cash_ratio": max_single_trade_cash_ratio,
        "max_single_trade_cash": usable_cash,
        "current_quantity": current_quantity,
        "current_price": current_price,
        "min_order_unit": min_order_unit,
        "max_buy_quantity": max_buy_quantity,
        "max_sell_quantity": current_quantity,
        "allow_hold": allow_hold,
        "allowed_actions": ["buy", "sell"] if not allow_hold else ["buy", "sell", "hold"],
    }


def parse_decision_json(content: str, constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text or "{}")
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    for key, default in {
        "action": "hold",
        "quantity": 0,
        "order_type": "limit",
        "price": 0,
        "reason": "",
        "risk_control": "",
    }.items():
        data.setdefault(key, default)
    action = str(data["action"]).lower()
    if action not in {"buy", "sell", "hold"}:
        action = "hold"
    quantity = max(0, int(data.get("quantity") or 0))
    price = float(data.get("price") or 0)
    corrections: list[str] = []
    raw_order_type = str(data.get("order_type") or "limit").lower()
    if raw_order_type != "limit":
        corrections.append(f"order_type:{raw_order_type}->limit")
    order_type = "limit"
    if constraints:
        allow_hold = bool(constraints.get("allow_hold", True))
        reference_price = float(constraints.get("current_price") or 0)
        min_order_unit = int(constraints["min_order_unit"])
        max_buy_quantity = int(constraints["max_buy_quantity"])
        max_sell_quantity = int(constraints["max_sell_quantity"])
        if not allow_hold and action == "hold":
            if max_buy_quantity >= min_order_unit:
                action = "buy"
                quantity = max(quantity, min_order_unit)
                corrections.append("hold->buy")
            elif max_sell_quantity >= min_order_unit:
                action = "sell"
                quantity = max(quantity, min_order_unit)
                corrections.append("hold->sell")
        if action == "buy":
            quantity = min(quantity, max_buy_quantity)
        elif action == "sell":
            quantity = min(quantity, max_sell_quantity)
        if not allow_hold and quantity < min_order_unit:
            if action != "buy" and max_buy_quantity >= min_order_unit:
                action = "buy"
                quantity = min_order_unit
                corrections.append("invalid_or_too_small->buy")
            elif action != "sell" and max_sell_quantity >= min_order_unit:
                action = "sell"
                quantity = min_order_unit
                corrections.append("invalid_or_too_small->sell")
        if quantity < min_order_unit:
            action = "hold"
            quantity = 0
            price = 0
        elif price <= 0 and reference_price > 0:
            price = reference_price
            corrections.append("price<=0->current_price")
        if action == "buy" and price > 0:
            max_by_submitted_price = int(float(constraints.get("max_single_trade_cash") or 0) // price)
            if quantity > max_by_submitted_price:
                quantity = max_by_submitted_price
                corrections.append("quantity_clamped_by_limit_price")
            if quantity < min_order_unit:
                action = "hold"
                quantity = 0
                price = 0
    if action == "hold":
        quantity = 0
        price = 0
        corrections = []
    return {
        "action": action,
        "quantity": quantity,
        "order_type": order_type,
        "price": price,
        "reason": str(data.get("reason") or ""),
        "risk_control": str(data.get("risk_control") or ""),
        "order_corrections": corrections,
    }


async def make_decision(
    agent: dict[str, Any],
    today_belief: dict[str, Any],
    market_analysis: dict[str, Any],
    portfolio_summary: str,
    trading_constraints: dict[str, Any],
    *,
    allow_hold: bool = True,
    client: OpenRouterClient | None = None,
) -> dict[str, Any]:
    client = client or OpenRouterClient()
    decision_space_instruction = (
        '이번 실행에서는 action이 반드시 "buy" 또는 "sell"이어야 합니다. "hold"는 선택할 수 없습니다.'
        if not allow_hold
        else '이번 실행에서는 action으로 "buy", "sell", "hold" 중 하나를 선택할 수 있습니다.'
    )
    prompt = load_prompt("make_decision.txt").format(
        persona_prompt=agent["persona_prompt"],
        today_belief=json.dumps(today_belief, ensure_ascii=False, indent=2),
        market_analysis=json.dumps(market_analysis, ensure_ascii=False, indent=2),
        portfolio_summary=portfolio_summary,
        trading_constraints=json.dumps(trading_constraints, ensure_ascii=False, indent=2),
        decision_space_instruction=decision_space_instruction,
    )
    response = await client.chat(
        [{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return parse_decision_json(response_content(response) or "{}", trading_constraints)
