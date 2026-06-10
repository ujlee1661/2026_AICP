#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import sys
import csv
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config


def count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def csv_stats(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"exists": False, "rows": 0, "dates": 0}
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    dates = sorted({row.get("date", "") for row in rows if row.get("date")})
    return {
        "exists": True,
        "rows": len(rows),
        "dates": len(dates),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
    }


def daily_news_quota_stats(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"days": 0, "violations": 0}
    by_day: dict[str, Counter[str]] = defaultdict(Counter)
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            by_day[row["date"]][row.get("category", "")] += 1
    violations = [date for date, counts in by_day.items() if sum(counts.values()) > 10]
    category_overflows = [
        date
        for date, counts in by_day.items()
        if counts.get("종목", 0) > 5 or counts.get("섹터", 0) > 3 or counts.get("경제", 0) > 2
    ]
    short_days = [date for date, counts in by_day.items() if sum(counts.values()) < 10]
    return {
        "days": len(by_day),
        "quota_violations": len(violations),
        "category_backfill_days": len(category_overflows),
        "short_days": len(short_days),
        "sample_violations": violations[:5],
    }


def main() -> None:
    sys100 = sqlite3.connect(config.SYS_100_DB)
    sim = sqlite3.connect(config.SIM_DB)
    persona_report = {}
    report_path = config.OUTPUT_DIR / "persona_validation_report.json"
    if report_path.exists():
        persona_report = json.loads(report_path.read_text(encoding="utf-8"))
    stock_dates = {
        str(row[0])
        for row in sim.execute("SELECT DISTINCT date FROM StockData").fetchall()
    }
    news_dates = set()
    if config.DAILY_NEWS_SELECTION_CSV.exists():
        with config.DAILY_NEWS_SELECTION_CSV.open(encoding="utf-8-sig", newline="") as f:
            news_dates = {row.get("date", "") for row in csv.DictReader(f) if row.get("date")}
    overlap = sorted(stock_dates & news_dates)
    report = {
        "agents_count": count(sys100, "agents"),
        "persona_distribution_pass": persona_report.get("distribution_pass"),
        "portfolio_state_count": count(sim, "portfolio_state"),
        "belief_history_count": count(sim, "belief_history"),
        "trade_log_count": count(sim, "trade_log"),
        "stock_data_count": count(sim, "StockData"),
        "trading_details_count": count(sim, "TradingDetails"),
        "processed_news": csv_stats(config.PROCESSED_NEWS_CSV),
        "daily_news_selection": csv_stats(config.DAILY_NEWS_SELECTION_CSV),
        "daily_news_quota": daily_news_quota_stats(config.DAILY_NEWS_SELECTION_CSV),
        "stock_news_overlap_dates": len(overlap),
        "stock_news_overlap_first_date": overlap[0] if overlap else None,
        "stock_news_overlap_last_date": overlap[-1] if overlap else None,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys100.close()
    sim.close()


if __name__ == "__main__":
    main()
