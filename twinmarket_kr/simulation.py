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
from twinmarket_kr.community.agent import CommunityAgent
from twinmarket_kr.community.badge import calculate_badges
from twinmarket_kr.community.posting import posting_decision
from twinmarket_kr.community.reading import community_reading_react, community_reading_select
from twinmarket_kr.core.daily_cycle import run_agent_turn
from twinmarket_kr.db.connection import connect, init_sim_db
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


def _stock_trading_dates() -> list[str]:
    with connect(config.SIM_DB) as conn:
        rows = conn.execute(
            "SELECT date FROM StockData WHERE stock_id = ? ORDER BY date",
            (config.STOCK_CODE,),
        ).fetchall()
    return [str(row["date"]) for row in rows]


def _previous_date_map() -> dict[str, str]:
    dates = _stock_trading_dates()
    return {day: dates[index - 1] for index, day in enumerate(dates) if index > 0}


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
    information_mode: str = "pre_close_cutoff",
    decision_space: str = "buy_sell_only",
    balanced_depths: bool = False,
) -> None:
    if information_mode not in {"pre_close_cutoff", "same_day", "prior_close"}:
        raise ValueError("information_mode must be 'pre_close_cutoff', 'same_day', or 'prior_close'")
    if decision_space != "buy_sell_only":
        raise ValueError("decision_space must be 'buy_sell_only'")
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
    previous_by_date = _previous_date_map()
    uses_previous_market = information_mode in {"pre_close_cutoff", "prior_close"}
    date_limit = None if max_days is None else max_days + (1 if uses_previous_market else 0)
    dates = trading_dates_between(start_date=start_date, end_date=end_date, limit=date_limit)
    if uses_previous_market:
        dates = [day for day in dates if day in previous_by_date]
        if max_days:
            dates = dates[:max_days]
    if not dates:
        raise RuntimeError("No StockData rows found. Run scripts/03_load_stock_data.py first.")

    _reset_runtime_tables(config.SIM_DB)
    memory = MemoryAgent(config.SIM_DB)
    fundamental = FundamentalAgent(config.SIM_DB)
    news = NewsAgent()
    exchange = ExchangeAgent(config.SIM_DB)
    community = CommunityAgent(config.SIM_DB) if config.ENABLE_COMMUNITY else None
    client = OpenRouterClient()
    semaphore = asyncio.Semaphore(concurrency)
    db_write_lock = asyncio.Lock()
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
                "information_mode": information_mode,
                "decision_space": decision_space,
                "limit_only_orders": True,
                "balanced_depths": balanced_depths,
                "agent_ids": [agent["agent_id"] for agent in agents],
                "agent_depths": {agent["agent_id"]: int(agent.get("news_depth") or 0) for agent in agents},
            }
        )
        if enable_logs
        else None
    )

    async def guarded_turn(
        agent: dict[str, Any],
        turn: int,
        day: str,
        market_features_date: str,
        news_max_date: str,
        news_start_date: str | None,
        news_start_time: str | None,
        news_end_time: str | None,
    ) -> dict[str, Any] | None:
        async with semaphore:
            try:
                return await run_agent_turn(
                    agent,
                    turn=turn,
                    date=day,
                    market_features_date=market_features_date,
                    news_max_date=news_max_date,
                    news_start_date=news_start_date,
                    news_start_time=news_start_time,
                    news_end_time=news_end_time,
                    execution_date=day,
                    information_mode=information_mode,
                    decision_space=decision_space,
                    memory_agent=memory,
                    fundamental_agent=fundamental,
                    news_agent=news,
                    client=client,
                    event_logger=logger,
                    db_write_lock=db_write_lock,
                    community_agent=community,
                )
            except Exception as exc:
                if logger is not None:
                    logger.log_agent_error(agent=agent, turn=turn, date=day, error=exc)
                raise

    for index, day in enumerate(dates, start=1):
        news_start_date = None
        news_start_time = None
        news_end_time = None
        if information_mode == "pre_close_cutoff":
            market_features_date = previous_by_date[day]
            news_start_date = previous_by_date[day]
            news_start_time = config.MARKET_CLOSE_TIME
            news_max_date = day
            news_end_time = config.ORDER_CUTOFF_TIME
        elif information_mode == "prior_close":
            market_features_date = previous_by_date[day]
            news_max_date = previous_by_date[day]
        else:
            market_features_date = day
            news_max_date = day
        turn_results = [
            result
            for result in await asyncio.gather(
                *(
                    guarded_turn(
                        agent,
                        index,
                        day,
                        market_features_date,
                        news_max_date,
                        news_start_date,
                        news_start_time,
                        news_end_time,
                    )
                    for agent in agents
                )
            )
            if result is not None
        ]
        orders = [result["order"] for result in turn_results if result.get("order") is not None]
        real_price = fundamental.get_market_features(day)["close"]
        previous_execution_date = previous_by_date.get(day)
        last_price = (
            real_price
            if previous_execution_date is None
            else fundamental.get_market_features(previous_execution_date)["close"]
        )
        results = exchange.process_daily_orders(
            orders,
            {config.STOCK_CODE: real_price},
            {config.STOCK_CODE: last_price},
            current_date=day,
            day_number=index,
        )
        if logger is not None:
            logger.log_daily_exchange(date=day, turn=index, orders=orders, results=results)
        execution_by_agent = _update_portfolios_from_results(
            memory=memory,
            agents=agents,
            turn=index,
            date=day,
            orders=orders,
            results=results,
            current_prices={config.STOCK_CODE: real_price},
            logger=logger,
        )
        if config.ENABLE_COMMUNITY and config.ENABLE_COMMUNITY_POSTING and community is not None:
            await post_trade_posting_phase(
                turn_results=turn_results,
                community_agent=community,
                execution_by_agent=execution_by_agent,
                turn=index,
                date=day,
                client=client,
                concurrency=concurrency,
                event_logger=logger,
            )
        if config.ENABLE_COMMUNITY and community is not None:
            await community_phase(
                agents=agents,
                community_agent=community,
                memory_agent=memory,
                turn=index,
                date=day,
                client=client,
                concurrency=concurrency,
                event_logger=logger,
            )
        print(f"{day} turn={index} orders={len(orders)} volume={results[config.STOCK_CODE]['volume']}")
    if logger is not None:
        logger.write_json(
            "run_complete.json",
            {
                "run_id": logger.run_id,
                "agent_count": len(agents),
                "date_count": len(dates),
                "information_mode": information_mode,
                "decision_space": decision_space,
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
) -> dict[str, dict[str, Any]]:
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
    execution_by_agent: dict[str, dict[str, Any]] = {}
    for agent in agents:
        agent_id = str(agent["agent_id"])
        fills = fills_by_agent.get(agent_id, [])
        filled_quantity = sum(int(fill["quantity"]) for fill in fills)
        total_value = sum(float(fill["quantity"]) * float(fill["price"]) for fill in fills)
        total_fee = sum(float(fill.get("fee", 0)) for fill in fills)
        execution_by_agent[agent_id] = {
            "fills": fills,
            "filled_quantity": filled_quantity,
            "executed_price": total_value / filled_quantity if filled_quantity else None,
            "fee": total_fee,
        }
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
    return execution_by_agent


async def post_trade_posting_phase(
    *,
    turn_results: list[dict[str, Any]],
    community_agent: CommunityAgent,
    execution_by_agent: dict[str, dict[str, Any]],
    turn: int,
    date: str,
    client: OpenRouterClient,
    concurrency: int = 8,
    event_logger: SimulationLogger | None = None,
) -> None:
    active_results = [
        result
        for result in turn_results
        if int(result.get("agent", {}).get("news_depth") or 0) >= 1
    ]
    if not active_results:
        return

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _one_post(result: dict[str, Any]) -> None:
        async with semaphore:
            agent = result["agent"]
            agent_id = str(agent["agent_id"])
            post_result = await posting_decision(
                agent,
                today_belief=result["belief"],
                decision=result["decision"],
                date=date,
                execution_summary=execution_by_agent.get(agent_id, {}),
                client=client,
            )
            if post_result is None:
                return
            post_id = community_agent.save_post(
                agent_id=agent_id,
                turn=turn,
                date=date,
                post_type=post_result["post_type"],
                title=post_result["title"],
                content=post_result["content"],
            )
            if event_logger is not None:
                event_logger.log_community_post(
                    agent_id=agent_id,
                    turn=turn,
                    date=date,
                    post={**post_result, "post_id": post_id},
                )

    await asyncio.gather(*(_one_post(result) for result in active_results))


async def community_phase(
    *,
    agents: list[dict[str, Any]],
    community_agent: CommunityAgent,
    memory_agent: MemoryAgent,
    turn: int,
    date: str,
    client: OpenRouterClient,
    concurrency: int = 8,
    event_logger: SimulationLogger | None = None,
) -> None:
    if not config.ENABLE_COMMUNITY_READING:
        best_posts = community_agent.mark_best_posts(date, config.COMMUNITY_BEST_POST_COUNT)
        if event_logger is not None:
            event_logger.log_community_best_posts(turn=turn, date=date, best_posts=best_posts)
        for agent in agents:
            if int(agent.get("news_depth") or 0) >= 1:
                community_agent.save_community_log(
                    agent_id=str(agent["agent_id"]),
                    turn=turn,
                    date=date,
                    best_posts=best_posts,
                    posts_read=[],
                    thinking="",
                )
                if event_logger is not None:
                    event_logger.log_community_log(
                        agent_id=str(agent["agent_id"]),
                        turn=turn,
                        date=date,
                        best_posts=best_posts,
                        posts_read=[],
                    )
        return

    badges = calculate_badges(agents, memory_agent, turn, str(config.SIM_DB))
    active_agents = [agent for agent in agents if int(agent.get("news_depth") or 0) >= 1]
    if not active_agents:
        community_agent.mark_best_posts(date, config.COMMUNITY_BEST_POST_COUNT)
        return

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _one_agent_reading(agent: dict[str, Any]) -> tuple[str, list[int], list[dict[str, Any]]]:
        async with semaphore:
            depth = int(agent.get("news_depth") or 0)
            read_limit = (
                config.COMMUNITY_DEPTH2_READ_LIMIT
                if depth >= 2
                else config.COMMUNITY_DEPTH1_READ_LIMIT
            )
            agent_id = str(agent["agent_id"])
            post_list = community_agent.get_today_posts(date)
            if not post_list:
                return agent_id, [], []
            visible_posts = [
                {**post, "author_badges": badges.get(str(post["agent_id"]), [])}
                for post in post_list
                if str(post["agent_id"]) != agent_id
            ]
            if event_logger is not None:
                event_logger.log_community_selection_input(
                    agent_id=agent_id,
                    turn=turn,
                    date=date,
                    depth=depth,
                    read_limit=read_limit,
                    visible_posts=visible_posts,
                )
            selected_ids = await community_reading_select(agent, visible_posts, read_limit, client=client)
            if not selected_ids:
                return agent_id, [], []

            posts_content: list[dict[str, Any]] = []
            for post_id in selected_ids:
                content = community_agent.get_post_content(post_id)
                if not content or str(content.get("agent_id")) == agent_id:
                    continue
                content["author_badges"] = badges.get(str(content.get("agent_id")), [])
                content["author_profile"] = (
                    community_agent.get_author_profile(str(content["agent_id"]), memory_agent, turn)
                    if depth >= 2
                    else None
                )
                posts_content.append(content)

            reactions = await community_reading_react(agent, posts_content, client=client)
            reaction_map = {int(item["post_id"]): item["reaction"] for item in reactions}
            posts_read: list[dict[str, Any]] = []
            for post in posts_content:
                post_id = int(post["post_id"])
                reaction = reaction_map.get(post_id, "read")
                recorded = community_agent.record_reaction(agent_id, post_id, turn, date, reaction)
                if recorded and reaction in {"like", "unlike"}:
                    community_agent.update_post_score_live(post_id, reaction)
                posts_read.append(
                    {
                        "post_id": post_id,
                        "title": post.get("title", ""),
                        "post_type": post.get("post_type", ""),
                        "content": post.get("content", ""),
                        "reaction": "read" if reaction == "none" else reaction,
                        "author_badges": post.get("author_badges") or [],
                        "author_profile": post.get("author_profile"),
                    }
                )
            if event_logger is not None:
                event_logger.log_community_reading(
                    agent_id=agent_id,
                    turn=turn,
                    date=date,
                    selected_post_ids=selected_ids,
                    posts_read=posts_read,
                )
            return agent_id, selected_ids, posts_read

    results = await asyncio.gather(*(_one_agent_reading(agent) for agent in active_agents))
    best_posts = community_agent.mark_best_posts(date, config.COMMUNITY_BEST_POST_COUNT)
    if event_logger is not None:
        event_logger.log_community_best_posts(turn=turn, date=date, best_posts=best_posts)
    for agent_id, _selected_ids, posts_read in results:
        community_agent.save_community_log(
            agent_id=agent_id,
            turn=turn,
            date=date,
            best_posts=best_posts,
            posts_read=posts_read,
            thinking="",
        )
        if event_logger is not None:
            event_logger.log_community_log(
                agent_id=agent_id,
                turn=turn,
                date=date,
                best_posts=best_posts,
                posts_read=posts_read,
            )
    print(f"  community_phase done: {len(active_agents)} agents, {len(best_posts)} best posts")


def _reset_runtime_tables(db_path: str) -> None:
    init_sim_db(db_path)
    with connect(db_path) as conn:
        conn.execute("DELETE FROM TradingDetails")
        conn.execute("DELETE FROM trade_log")
        conn.execute("DELETE FROM belief_history WHERE turn > 0")
        conn.execute("DELETE FROM portfolio_state WHERE turn > 0")
        conn.execute("DELETE FROM community_posts")
        conn.execute("DELETE FROM community_interactions")
        conn.execute("DELETE FROM community_logs WHERE turn > 0")
        conn.commit()
