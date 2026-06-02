#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config
from twinmarket_kr.agents.memory_agent import MemoryAgent, load_agents_from_sys100
from twinmarket_kr.llm.belief import generate_initial_belief
from twinmarket_kr.llm.client import OpenRouterClient


async def run(offline: bool) -> None:
    memory = MemoryAgent(config.SIM_DB)
    agents = load_agents_from_sys100(config.SYS_100_DB)
    client = None if offline else OpenRouterClient()
    for agent in agents:
        await generate_initial_belief(agent, client=client, memory=memory, offline=offline)
    print(f"saved initial beliefs for {len(agents)} agents. offline={offline}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Use deterministic template beliefs without LLM.")
    args = parser.parse_args()
    asyncio.run(run(args.offline))


if __name__ == "__main__":
    main()
