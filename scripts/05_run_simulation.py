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
    parser.add_argument("--random-agents", action="store_true")
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument(
        "--information-mode",
        choices=("same_day", "prior_close"),
        default="same_day",
        help="Information cutoff for each decision turn.",
    )
    parser.add_argument(
        "--decision-space",
        choices=("buy_hold_sell", "buy_sell_only"),
        default="buy_hold_sell",
        help="Allowed trading actions for the decision parser.",
    )
    parser.add_argument("--balanced-depths", action="store_true")
    parser.add_argument("--no-logs", action="store_true", help="Disable detailed output logs.")
    args = parser.parse_args()
    asyncio.run(
        run_simulation(
            max_agents=args.max_agents,
            max_days=args.max_days,
            concurrency=args.concurrency,
            enable_logs=not args.no_logs,
            random_agents=args.random_agents,
            random_seed=args.seed,
            start_date=args.start_date,
            end_date=args.end_date,
            information_mode=args.information_mode,
            decision_space=args.decision_space,
            balanced_depths=args.balanced_depths,
        )
    )


if __name__ == "__main__":
    main()
