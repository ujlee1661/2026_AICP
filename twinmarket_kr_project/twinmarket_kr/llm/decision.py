from __future__ import annotations

import json
from typing import Any

import config
from twinmarket_kr.llm.belief import load_prompt
from twinmarket_kr.llm.client import OpenRouterClient


DECISION_KEYS = ("action", "quantity", "order_type", "price", "reason", "risk_control")


def build_trading_constraints(
    *,
    available_cash: float,
    current_quantity: int,
    current_price: float,
    commission_rate: float = config.COMMISSION_RATE,
    min_order_unit: int = config.MIN_ORDER_UNIT,
) -> dict[str, Any]:
    max_buy_quantity = int(available_cash // (current_price * (1 + commission_rate))) if current_price > 0 else 0
    return {
        "available_cash": available_cash,
        "current_quantity": current_quantity,
        "current_price": current_price,
        "commission_rate": commission_rate,
        "min_order_unit": min_order_unit,
        "max_buy_quantity": max_buy_quantity,
        "max_sell_quantity": current_quantity,
    }


def parse_decision_json(content: str, constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    data = json.loads(text)
    missing = [key for key in DECISION_KEYS if key not in data]
    if missing:
        raise ValueError(f"decision JSON missing keys: {missing}")
    action = str(data["action"]).lower()
    if action not in {"buy", "sell", "hold"}:
        action = "hold"
    quantity = max(0, int(data.get("quantity") or 0))
    price = float(data.get("price") or 0)
    if constraints:
        if action == "buy":
            quantity = min(quantity, int(constraints["max_buy_quantity"]))
        elif action == "sell":
            quantity = min(quantity, int(constraints["max_sell_quantity"]))
        if quantity < int(constraints["min_order_unit"]):
            action = "hold"
            quantity = 0
            price = 0
    if action == "hold":
        quantity = 0
        price = 0
    return {
        "action": action,
        "quantity": quantity,
        "order_type": str(data.get("order_type") or "market"),
        "price": price,
        "reason": str(data.get("reason") or ""),
        "risk_control": str(data.get("risk_control") or ""),
    }


async def make_decision(
    agent: dict[str, Any],
    today_belief: dict[str, Any],
    portfolio_summary: str,
    trading_constraints: dict[str, Any],
    *,
    client: OpenRouterClient | None = None,
) -> dict[str, Any]:
    client = client or OpenRouterClient()
    prompt = load_prompt("make_decision.txt").format(
        persona_prompt=agent["persona_prompt"],
        today_belief=json.dumps(today_belief, ensure_ascii=False, indent=2),
        portfolio_summary=portfolio_summary,
        trading_constraints=json.dumps(trading_constraints, ensure_ascii=False, indent=2),
    )
    response = await client.chat(
        [{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return parse_decision_json(response.choices[0].message.content or "{}", trading_constraints)
