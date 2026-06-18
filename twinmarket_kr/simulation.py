from __future__ import annotations

import asyncio
import csv
import random
from collections import defaultdict
from typing import Any

import config
from twinmarket_kr.agents.exchange_agent import ExchangeAgent
from twinmarket_kr.agents.fundamental_agent import FundamentalAgent
from twinmarket_kr.agents.memory_agent import MemoryAgent, load_agents_from_sys100
from twinmarket_kr.agents.news_agent import NewsAgent
from twinmarket_kr.core.daily_cycle import run_agent_turn
from twinmarket_kr.db.connection import connect
from twinmarket_kr.llm.client import OpenRouterClient
from twinmarket_kr.run_logger import SimulationLogger


def trading_dates(limit: int | None = None) -> list[str]:
    return trading_dates_between(limit=limit)


def trading_dates_between(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> list[str]:
    with connect(config.SIM_DB) as conn:
        rows = conn.execute(
            "SELECT date FROM StockData WHERE stock_id = ? ORDER BY date",
            (config.STOCK_CODE,),
        ).fetchall()
    dates = [str(row["date"]) for row in rows]
    news_dates = _daily_news_dates()
    if news_dates:
        dates = [day for day in dates if day in news_dates]
    if start_date:
        dates = [day for day in dates if day >= start_date]
    if end_date:
        dates = [day for day in dates if day <= end_date]
    return dates[:limit] if limit else dates


def _daily_news_dates() -> set[str]:
    if not config.DAILY_NEWS_SELECTION_CSV.exists():
        return set()
    with config.DAILY_NEWS_SELECTION_CSV.open(encoding="utf-8-sig", newline="") as f:
        return {row["date"] for row in csv.DictReader(f) if row.get("date")}


async def run_simulation(
    *,
    max_agents: int | None = None,
    max_days: int | None = None,
    concurrency: int = 8,
    enable_logs: bool = True,
    random_agents: bool = False,
    random_seed: int = config.RANDOM_SEED,
    start_date: str | None = None,
    end_date: str | None = None,
    balanced_depths: bool = False,
) -> None:
    agents = load_agents_from_sys100(config.SYS_100_DB)
    if max_agents:
        all_agents = agents
        if balanced_depths:
            agents = _sample_balanced_depths(agents, max_agents, random_seed)
        elif random_agents:
            agents = random.Random(random_seed).sample(agents, min(max_agents, len(agents)))
            agents.sort(key=lambda agent: agent["agent_id"])
        else:
            agents = agents[:max_agents]
        agents = _ensure_depth2_agent(agents, all_agents)
    dates = trading_dates_between(start_date=start_date, end_date=end_date, limit=max_days)
    if not dates:
        raise RuntimeError("No StockData rows found. Run scripts/03_load_stock_data.py first.")

    _reset_runtime_tables(config.SIM_DB)
    memory = MemoryAgent(config.SIM_DB)
    fundamental = FundamentalAgent(config.SIM_DB)
    news = NewsAgent()
    exchange = ExchangeAgent(config.SIM_DB)
    client = OpenRouterClient()
    semaphore = asyncio.Semaphore(concurrency)
    logger = (
        SimulationLogger(
            metadata={
                "max_agents": max_agents,
                "max_days": max_days,
                "concurrency": concurrency,
                "agent_count": len(agents),
                "date_count": len(dates),
                "sim_db": str(config.SIM_DB),
                "random_agents": random_agents,
                "random_seed": random_seed,
                "start_date": start_date,
                "end_date": end_date,
                "balanced_depths": balanced_depths,
                "agent_ids": [agent["agent_id"] for agent in agents],
                "agent_depths": {agent["agent_id"]: int(agent.get("news_depth") or 0) for agent in agents},
            }
        )
        if enable_logs
        else None
    )

    async def guarded_turn(agent: dict[str, Any], turn: int, day: str) -> dict[str, Any] | None:
        async with semaphore:
            try:
                return await run_agent_turn(
                    agent,
                    turn=turn,
                    date=day,
                    memory_agent=memory,
                    fundamental_agent=fundamental,
                    news_agent=news,
                    client=client,
                    event_logger=logger,
                )
            except Exception as exc:
                if logger is not None:
                    logger.log_agent_error(agent=agent, turn=turn, date=day, error=exc)
                raise

    for index, day in enumerate(dates, start=1):
        orders = [
            order
            for order in await asyncio.gather(*(guarded_turn(agent, index, day) for agent in agents))
            if order is not None
        ]
        real_price = fundamental.get_market_features(day)["close"]
        last_price = real_price if index == 1 else fundamental.get_market_features(dates[index - 2])["close"]
        results = exchange.process_daily_orders(
            orders,
            {config.STOCK_CODE: real_price},
            {config.STOCK_CODE: last_price},
            current_date=day,
            day_number=index,
        )
        if logger is not None:
            logger.log_daily_exchange(date=day, turn=index, orders=orders, results=results)
        _update_portfolios_from_results(
            memory=memory,
            agents=agents,
            turn=index,
            date=day,
            orders=orders,
            results=results,
            current_prices={config.STOCK_CODE: real_price},
            logger=logger,
        )
        print(f"{day} turn={index} orders={len(orders)} volume={results[config.STOCK_CODE]['volume']}")
    if logger is not None:
        logger.write_json(
            "run_complete.json",
            {
                "run_id": logger.run_id,
                "agent_count": len(agents),
                "date_count": len(dates),
                "log_dir": str(logger.run_dir),
            },
        )
        print(f"log_dir={logger.run_dir}")


def _ensure_depth2_agent(agents: list[dict[str, Any]], all_agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if any(int(agent.get("news_depth") or 0) >= 2 for agent in agents):
        return agents
    depth2_agents = [agent for agent in all_agents if int(agent.get("news_depth") or 0) >= 2]
    if not depth2_agents:
        raise RuntimeError("테스트 실행에 Depth 2 에이전트가 최소 1명 필요합니다. sys_100.db를 확인하세요.")
    if not agents:
        return depth2_agents[:1]
    replaced = [*agents[:-1], depth2_agents[0]]
    return sorted({agent["agent_id"]: agent for agent in replaced}.values(), key=lambda agent: agent["agent_id"])


def _sample_balanced_depths(
    agents: list[dict[str, Any]],
    max_agents: int,
    random_seed: int,
) -> list[dict[str, Any]]:
    if max_agents <= 0:
        return []
    rng = random.Random(random_seed)
    by_depth: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for agent in agents:
        by_depth[int(agent.get("news_depth") or 0)].append(agent)

    depths = [0, 1, 2]
    missing = [depth for depth in depths if not by_depth.get(depth)]
    if missing:
        raise RuntimeError(f"Depth 후보가 없습니다: {missing}")

    base = max_agents // len(depths)
    remainder = max_agents % len(depths)
    quotas = {depth: base for depth in depths}
    for depth in depths[:remainder]:
        quotas[depth] += 1

    selected: list[dict[str, Any]] = []
    for depth in depths:
        candidates = by_depth[depth]
        take = min(quotas[depth], len(candidates))
        selected.extend(rng.sample(candidates, take))

    if len(selected) < max_agents:
        selected_ids = {agent["agent_id"] for agent in selected}
        remaining = [agent for agent in agents if agent["agent_id"] not in selected_ids]
        selected.extend(rng.sample(remaining, min(max_agents - len(selected), len(remaining))))

    return sorted(selected, key=lambda agent: agent["agent_id"])


def _update_portfolios_from_results(
    *,
    memory: MemoryAgent,
    agents: list[dict[str, Any]],
    turn: int,
    date: str,
    orders: list[dict[str, Any]],
    results: dict[str, dict[str, Any]],
    current_prices: dict[str, float],
    logger: SimulationLogger | None,
) -> None:
    fills_by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stock_code, result in results.items():
        for tx in result.get("transactions") or []:
            user_id = str(tx.get("user_id") or "")
            if not user_id or user_id == config.COUNTERSIDE_USER_ID:
                continue
            quantity = int(tx.get("executed_quantity", 0))
            price = float(tx.get("executed_price", 0))
            fills_by_agent[user_id].append(
                {
                    "user_id": user_id,
                    "stock_code": tx.get("stock_code", stock_code),
                    "direction": tx.get("direction"),
                    "quantity": quantity,
                    "price": price,
                    "fee": float(tx.get("fee", price * quantity * config.COMMISSION_RATE)),
                }
            )
    submitted_agent_ids = {str(order.get("user_id")) for order in orders if order.get("user_id")}
    for agent_id in submitted_agent_ids:
        fills = fills_by_agent.get(agent_id, [])
        filled_quantity = sum(int(fill["quantity"]) for fill in fills)
        total_value = sum(float(fill["quantity"]) * float(fill["price"]) for fill in fills)
        total_fee = sum(float(fill.get("fee", 0)) for fill in fills)
        executed_price = total_value / filled_quantity if filled_quantity else None
        memory.update_trade_execution(
            agent_id,
            turn,
            filled_quantity=filled_quantity,
            executed_price=executed_price,
            fee=total_fee,
        )
    for agent in agents:
        agent_id = str(agent["agent_id"])
        fills = fills_by_agent.get(agent_id, [])
        state = memory.update_portfolio(
            agent_id,
            turn,
            date,
            fills,
            current_prices=current_prices,
        )
        if logger is not None:
            logger.write_jsonl(
                "portfolio_updates.jsonl",
                {
                    "run_id": logger.run_id,
                    "event": "portfolio_update",
                    "date": date,
                    "turn": turn,
                    "agent_id": agent_id,
                    "fills": fills,
                    "state": state,
                },
            )


def _reset_runtime_tables(db_path: str) -> None:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM TradingDetails")
        conn.execute("DELETE FROM trade_log")
        conn.execute("DELETE FROM belief_history WHERE turn > 0")
        conn.execute("DELETE FROM portfolio_state WHERE turn > 0")
        conn.commit()
