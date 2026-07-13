#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config
from twinmarket_kr.db.connection import connect
from twinmarket_kr.simulation import run_simulation


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _latest_run_dir() -> Path:
    current = config.LOG_DIR / "current"
    if current.exists():
        return current.resolve()
    candidates = [path for path in config.LOG_DIR.iterdir() if path.is_dir()]
    if not candidates:
        raise RuntimeError("No simulation log directory found.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _table_rows(table: str) -> list[dict[str, Any]]:
    with connect(config.SIM_DB) as conn:
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        for key in ("best_posts_seen", "posts_read"):
            if key in item and item[key]:
                try:
                    item[key] = json.loads(item[key])
                except json.JSONDecodeError:
                    pass
        result.append(item)
    return result


def _build_full_log(run_dir: Path, *, output_name: str) -> Path:
    agent_turns = _read_jsonl(run_dir / "agent_turns.jsonl")
    community_events = _read_jsonl(run_dir / "community_events.jsonl")
    daily_exchange = _read_jsonl(run_dir / "daily_exchange.jsonl")
    portfolio_updates = _read_jsonl(run_dir / "portfolio_updates.jsonl")
    errors = _read_jsonl(run_dir / "errors.jsonl")

    by_turn: dict[str, list[dict[str, Any]]] = {}
    for event in agent_turns:
        key = f"turn_{event.get('turn')}_{event.get('date')}"
        by_turn.setdefault(key, []).append(
            {
                "agent": event.get("agent"),
                "input_context": event.get("context"),
                "outputs": {
                    "news_interpretation": event.get("news_interpretation"),
                    "belief": event.get("belief"),
                    "market_analysis": event.get("market_analysis"),
                    "decision": event.get("decision"),
                    "submitted_order": event.get("submitted_order"),
                    "depth2_flow": event.get("depth2_flow"),
                },
            }
        )

    report = {
        "purpose": "2-day community smoke test full input/output log",
        "run_dir": str(run_dir),
        "metadata": _read_json(run_dir / "run_metadata.json"),
        "run_complete": _read_json(run_dir / "run_complete.json"),
        "agent_turn_count": len(agent_turns),
        "community_event_count": len(community_events),
        "daily_exchange": daily_exchange,
        "agent_input_output_by_turn": by_turn,
        "portfolio_updates": portfolio_updates,
        "community": {
            "events": community_events,
            "posts": _table_rows("community_posts"),
            "interactions": _table_rows("community_interactions"),
            "logs": _table_rows("community_logs"),
        },
        "errors": errors,
    }
    output_path = run_dir / output_name
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a small 2-day community simulation and bundle full logs.")
    parser.add_argument("--max-agents", type=int, default=3)
    parser.add_argument("--max-days", type=int, default=2)
    parser.add_argument("--seed", type=int, default=config.RANDOM_SEED)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument(
        "--information-mode",
        choices=("pre_close_cutoff", "same_day", "prior_close"),
        default="pre_close_cutoff",
    )
    parser.add_argument("--decision-space", choices=("buy_sell_only",), default="buy_sell_only")
    parser.add_argument("--output-name", default="community_smoke_test_full_log.json")
    args = parser.parse_args()

    asyncio.run(
        run_simulation(
            max_agents=args.max_agents,
            max_days=args.max_days,
            enable_logs=True,
            random_seed=args.seed,
            start_date=args.start_date,
            end_date=args.end_date,
            information_mode=args.information_mode,
            decision_space=args.decision_space,
        )
    )
    run_dir = _latest_run_dir()
    output_path = _build_full_log(run_dir, output_name=args.output_name)
    print(f"run_dir={run_dir}")
    print(f"full_log={output_path}")


if __name__ == "__main__":
    main()
