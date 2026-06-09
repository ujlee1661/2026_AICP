from __future__ import annotations

import asyncio
from typing import Any

import config
from twinmarket_kr.agents.exchange_agent import ExchangeAgent
from twinmarket_kr.agents.fundamental_agent import FundamentalAgent
from twinmarket_kr.agents.memory_agent import MemoryAgent, load_agents_from_sys100
from twinmarket_kr.agents.news_agent import NewsAgent
from twinmarket_kr.core.daily_cycle import run_agent_turn
from twinmarket_kr.db.connection import connect
from twinmarket_kr.llm.client import OpenRouterClient


def trading_dates(limit: int | None = None) -> list[str]:
    with connect(config.SIM_DB) as conn:
        rows = conn.execute(
            "SELECT date FROM StockData WHERE stock_id = ? ORDER BY date",
            (config.STOCK_CODE,),
        ).fetchall()
    dates = [str(row["date"]) for row in rows]
    return dates[:limit] if limit else dates


async def run_simulation(
    *,
    max_agents: int | None = None,
    max_days: int | None = None,
    concurrency: int = 8,
) -> None:
    agents = load_agents_from_sys100(config.SYS_100_DB)
    if max_agents:
        agents = agents[:max_agents]
    dates = trading_dates(max_days)
    if not dates:
        raise RuntimeError("No StockData rows found. Run scripts/03_load_stock_data.py first.")

    memory = MemoryAgent(config.SIM_DB)
    fundamental = FundamentalAgent(config.SIM_DB)
    news = NewsAgent()
    exchange = ExchangeAgent(config.SIM_DB)
    client = OpenRouterClient()
    semaphore = asyncio.Semaphore(concurrency)

    async def guarded_turn(agent: dict[str, Any], turn: int, day: str) -> dict[str, Any] | None:
        async with semaphore:
            return await run_agent_turn(
                agent,
                turn=turn,
                date=day,
                memory_agent=memory,
                fundamental_agent=fundamental,
                news_agent=news,
                client=client,
            )

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
        print(f"{day} turn={index} orders={len(orders)} volume={results[config.STOCK_CODE]['volume']}")
