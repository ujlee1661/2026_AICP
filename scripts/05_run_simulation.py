#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from twinmarket_kr.simulation import run_simulation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-agents", type=int, default=None)
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    asyncio.run(
        run_simulation(
            max_agents=args.max_agents,
            max_days=args.max_days,
            concurrency=args.concurrency,
        )
    )


if __name__ == "__main__":
    main()
