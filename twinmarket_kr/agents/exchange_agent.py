from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import config
from twinmarket_kr.db.connection import connect, init_sim_db


@dataclass(slots=True)
class Order:
    stock_code: str
    user_id: str
    direction: str
    quantity: int
    price: float
    timestamp: float


def _as_order(value: Order | dict[str, Any]) -> Order:
    if isinstance(value, Order):
        return value
    return Order(
        stock_code=value.get("stock_code", config.STOCK_CODE),
        user_id=value["user_id"],
        direction=value["direction"],
        quantity=int(value["quantity"]),
        price=float(value.get("price", 0)),
        timestamp=float(value.get("timestamp", 0)),
    )


def _transaction(order: Order, executed_price: float, quantity: int) -> dict[str, Any]:
    fee = 0.0
    if order.user_id != config.COUNTERSIDE_USER_ID:
        fee = executed_price * int(quantity) * config.COMMISSION_RATE
    return {
        "stock_code": order.stock_code,
        "user_id": order.user_id,
        "direction": order.direction,
        "executed_price": executed_price,
        "executed_quantity": int(quantity),
        "fee": fee,
        "timestamp": order.timestamp,
    }


class ExchangeAgent:
    def __init__(self, db_path: Path | str = config.SIM_DB) -> None:
        self.db_path = Path(db_path)
        init_sim_db(self.db_path)

    def execute_warmup_orders(
        self,
        buy_orders: list[Order | dict[str, Any]],
        sell_orders: list[Order | dict[str, Any]],
        *,
        day_number: int,
        real_price: float,
        last_real_price: float,
    ) -> tuple[float, int, list[dict[str, Any]]]:
        upper_limit = last_real_price * (1 + config.CIRCUIT_BREAKER)
        lower_limit = last_real_price * (1 - config.CIRCUIT_BREAKER)
        buys = [_as_order(order) for order in buy_orders]
        sells = [_as_order(order) for order in sell_orders]
        target_orders = buys if day_number == 1 else buys + sells

        transactions = []
        for order in target_orders:
            if order.price <= 0:
                continue
            exec_price = order.price
            if lower_limit <= exec_price <= upper_limit and order.quantity > 0:
                transactions.append(_transaction(order, exec_price, order.quantity))
        volume = sum(tx["executed_quantity"] for tx in transactions)
        return real_price, volume, transactions

    def calculate_anchored_price(
        self,
        buy_orders: list[Order | dict[str, Any]],
        sell_orders: list[Order | dict[str, Any]],
        *,
        target_price: float,
        last_real_price: float,
        stock_code: str = config.STOCK_CODE,
    ) -> tuple[float, int, list[dict[str, Any]]]:
        upper_limit = last_real_price * (1 + config.CIRCUIT_BREAKER)
        lower_limit = last_real_price * (1 - config.CIRCUIT_BREAKER)
        target_price = max(lower_limit, min(upper_limit, target_price))

        buys = [
            _as_order(order)
            for order in buy_orders
            if _as_order(order).quantity > 0 and lower_limit <= _as_order(order).price <= upper_limit
        ]
        sells = [
            _as_order(order)
            for order in sell_orders
            if _as_order(order).quantity > 0 and lower_limit <= _as_order(order).price <= upper_limit
        ]
        if not buys and not sells:
            return target_price, 0, []

        normalized_buys = [Order(o.stock_code, o.user_id, o.direction, o.quantity, o.price, o.timestamp) for o in buys]
        normalized_sells = [Order(o.stock_code, o.user_id, o.direction, o.quantity, o.price, o.timestamp) for o in sells]

        buy_vol = sum(order.quantity for order in normalized_buys if order.price >= target_price)
        sell_vol = sum(order.quantity for order in normalized_sells if order.price <= target_price)
        imbalance = buy_vol - sell_vol
        max_ts = max([order.timestamp for order in normalized_buys + normalized_sells] or [0]) + 0.001

        if imbalance > 0:
            normalized_sells.append(Order(stock_code, config.COUNTERSIDE_USER_ID, "sell", imbalance, target_price, max_ts))
            sell_vol += imbalance
        elif imbalance < 0:
            normalized_buys.append(Order(stock_code, config.COUNTERSIDE_USER_ID, "buy", abs(imbalance), target_price, max_ts))
            buy_vol += abs(imbalance)

        matched_volume = min(buy_vol, sell_vol)
        if matched_volume <= 0:
            return target_price, 0, []

        transactions: list[dict[str, Any]] = []
        remaining = matched_volume
        for order in sorted(normalized_buys, key=lambda item: (-item.price, item.timestamp)):
            if order.price >= target_price and remaining > 0:
                qty = min(order.quantity, remaining)
                transactions.append(_transaction(order, target_price, qty))
                remaining -= qty

        remaining = matched_volume
        for order in sorted(normalized_sells, key=lambda item: (item.price, item.timestamp)):
            if order.price <= target_price and remaining > 0:
                qty = min(order.quantity, remaining)
                transactions.append(_transaction(order, target_price, qty))
                remaining -= qty

        return target_price, matched_volume, transactions

    def process_daily_orders(
        self,
        orders: list[Order | dict[str, Any]],
        real_prices: dict[str, float],
        last_real_prices: dict[str, float],
        *,
        current_date: str,
        day_number: int,
        n_warmup: int = config.N_WARMUP,
        persist: bool = True,
    ) -> dict[str, dict[str, Any]]:
        stock_orders: dict[str, dict[str, list[Order]]] = defaultdict(lambda: {"buy": [], "sell": []})
        for raw_order in orders:
            order = _as_order(raw_order)
            if order.direction not in {"buy", "sell"}:
                continue
            stock_orders[order.stock_code][order.direction].append(order)

        results: dict[str, dict[str, Any]] = {}
        for stock_code in sorted(set(real_prices) | set(stock_orders)):
            real_price = float(real_prices[stock_code])
            last_real_price = float(last_real_prices.get(stock_code, real_price))
            buy = stock_orders[stock_code]["buy"]
            sell = stock_orders[stock_code]["sell"]
            if day_number <= n_warmup:
                closing_price, volume, transactions = self.execute_warmup_orders(
                    buy,
                    sell,
                    day_number=day_number,
                    real_price=real_price,
                    last_real_price=last_real_price,
                )
            else:
                closing_price, volume, transactions = self.calculate_anchored_price(
                    buy,
                    sell,
                    target_price=real_price,
                    last_real_price=last_real_price,
                    stock_code=stock_code,
                )
            results[stock_code] = {
                "closing_price": closing_price,
                "volume": volume,
                "transactions": transactions,
            }
            if persist:
                self.save_trading_details(current_date, stock_code, transactions)
        return results

    def save_trading_details(self, date: str, stock_code: str, transactions: list[dict[str, Any]]) -> None:
        with connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO TradingDetails (
                    date, stock_id, user_id, trading_direction, price, volume
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        date,
                        stock_code,
                        tx["user_id"],
                        tx["direction"],
                        tx["executed_price"],
                        tx["executed_quantity"],
                    )
                    for tx in transactions
                ],
            )
            conn.commit()
