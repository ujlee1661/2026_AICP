#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config


def count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def main() -> None:
    sys100 = sqlite3.connect(config.SYS_100_DB)
    sim = sqlite3.connect(config.SIM_DB)
    persona_report = {}
    report_path = config.OUTPUT_DIR / "persona_validation_report.json"
    if report_path.exists():
        persona_report = json.loads(report_path.read_text(encoding="utf-8"))
    report = {
        "agents_count": count(sys100, "agents"),
        "persona_distribution_pass": persona_report.get("distribution_pass"),
        "portfolio_state_count": count(sim, "portfolio_state"),
        "belief_history_count": count(sim, "belief_history"),
        "trade_log_count": count(sim, "trade_log"),
        "stock_data_count": count(sim, "StockData"),
        "trading_details_count": count(sim, "TradingDetails"),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys100.close()
    sim.close()


if __name__ == "__main__":
    main()
