#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config
from twinmarket_kr.agents.fundamental_agent import FundamentalAgent


def main() -> None:
    agent = FundamentalAgent(config.SIM_DB)
    count = agent.load_stock_data_csv(config.STOCK_DATA_CSV)
    print(f"loaded {count} stock rows into {config.SIM_DB}")


if __name__ == "__main__":
    main()
