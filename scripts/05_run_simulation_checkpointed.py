#!/usr/bin/env python3
"""Run a simulation in restartable date chunks with an isolated SQLite database."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config
from twinmarket_kr.simulation import run_simulation, trading_dates_between


CSV_FILES = (
    "agent_turns.csv",
    "submitted_orders.csv",
    "exchange_fills.csv",
    "daily_exchange_summary.csv",
    "community_posts.csv",
    "community_interactions.csv",
    "community_logs.csv",
    "community_best_posts.csv",
    "community_selection_inputs.csv",
)
JSONL_FILES = (
    "agent_turns.jsonl",
    "portfolio_updates.jsonl",
    "daily_exchange.jsonl",
    "community_events.jsonl",
    "community_selection_inputs.jsonl",
)


def _backup_database(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Simulation source database not found: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _merge_csv(master: Path, chunk: Path) -> None:
    if not chunk.exists():
        return
    master.parent.mkdir(parents=True, exist_ok=True)
    if not master.exists():
        shutil.copy2(chunk, master)
        return
    with master.open("a", encoding="utf-8-sig", newline="") as destination, chunk.open(
        "r", encoding="utf-8-sig", newline=""
    ) as source:
        reader = csv.reader(source)
        writer = csv.writer(destination)
        next(reader, None)
        writer.writerows(reader)


def _merge_jsonl(master: Path, chunk: Path) -> None:
    if not chunk.exists():
        return
    with master.open("a", encoding="utf-8") as destination, chunk.open("r", encoding="utf-8") as source:
        shutil.copyfileobj(source, destination)


def _split_dates(dates: list[str], size: int) -> list[list[str]]:
    return [dates[index : index + size] for index in range(0, len(dates), size)]


def _condition_files(fake_news_mode: str, variant: str) -> tuple[Path, Path]:
    if fake_news_mode == "off":
        return config.PROCESSED_NEWS_CSV, config.DAILY_NEWS_SELECTION_CSV
    if variant == "bearish":
        return config.PROCESSED_NEWS_INJECTION_BEARISH_CSV, config.DAILY_NEWS_SELECTION_INJECTION_BEARISH_CSV
    return config.PROCESSED_NEWS_INJECTION_BULLISH_CSV, config.DAILY_NEWS_SELECTION_INJECTION_BULLISH_CSV


async def _run(args: argparse.Namespace) -> None:
    if args.chunk_days < 1:
        raise ValueError("--chunk-days must be at least 1")

    default_processed, default_daily = _condition_files(args.fake_news_mode, args.fake_news_variant)
    processed_news = Path(args.processed_news_csv) if args.processed_news_csv else default_processed
    daily_news = Path(args.daily_news_csv) if args.daily_news_csv else default_daily
    if not processed_news.exists() or not daily_news.exists():
        raise FileNotFoundError("Required news input CSV is missing.")

    run_dir = Path(args.output_run_dir) if args.output_run_dir else config.LOG_DIR / (
        f"simulation_checkpointed_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    )
    checkpoint_path = run_dir / "checkpoint.json"
    runtime_db = Path(args.sim_db) if args.sim_db else run_dir / "runtime_sim.db"
    source_db = config.SIM_DB

    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint.get("status") == "complete":
            print(f"already complete: {run_dir}")
            return
        if checkpoint.get("runtime_db") != str(runtime_db.resolve()):
            raise RuntimeError("--sim-db does not match the checkpointed run.")
    else:
        run_dir.mkdir(parents=True, exist_ok=False)
        if args.sim_db:
            if not runtime_db.exists():
                _backup_database(source_db, runtime_db)
        else:
            _backup_database(source_db, runtime_db)
        checkpoint = {"status": "running", "completed_chunks": [], "runtime_db": str(runtime_db.resolve())}
        _write_json(checkpoint_path, checkpoint)

    dates = trading_dates_between(
        start_date=args.start_date,
        end_date=args.end_date,
        daily_news_csv_path=daily_news,
        sim_db_path=runtime_db,
    )
    chunks = _split_dates(dates, args.chunk_days)
    if not chunks:
        raise RuntimeError("No trading dates found for requested range.")

    completed = {int(index) for index in checkpoint.get("completed_chunks", [])}
    metadata = {
        "run_id": run_dir.name,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "date_count": len(dates),
        "turn_count": len(dates) * 2,
        "chunk_days": args.chunk_days,
        "chunk_count": len(chunks),
        "max_agents": args.max_agents,
        "concurrency": config.SIMULATION_CONCURRENCY,
        "community_mode": args.community_mode,
        "fake_news_mode": args.fake_news_mode,
        "fake_news_variant": args.fake_news_variant if args.fake_news_mode == "on" else None,
        "processed_news_csv": str(processed_news.resolve()),
        "daily_news_csv": str(daily_news.resolve()),
        "sim_db": str(runtime_db.resolve()),
        "chunks": [],
    }

    for index, chunk_dates in enumerate(chunks, start=1):
        chunk_start, chunk_end = chunk_dates[0], chunk_dates[-1]
        chunk_dir = run_dir / "chunks" / f"chunk_{index:03d}_{chunk_start}_{chunk_end}"
        snapshot = run_dir / "checkpoints" / f"before_chunk_{index:03d}.db"
        if index in completed:
            metadata["chunks"].append({"index": index, "start_date": chunk_start, "end_date": chunk_end, "status": "complete"})
            continue

        if snapshot.exists():
            _backup_database(snapshot, runtime_db)
        else:
            _backup_database(runtime_db, snapshot)

        await run_simulation(
            max_agents=args.max_agents,
            random_seed=args.seed,
            start_date=chunk_start,
            end_date=chunk_end,
            processed_news_csv=processed_news,
            daily_news_csv=daily_news,
            fake_news_mode=args.fake_news_mode,
            fake_news_variant=args.fake_news_variant if args.fake_news_mode == "on" else None,
            community_mode=args.community_mode,
            sim_db=runtime_db,
            reset_runtime_tables=index == 1,
            log_root=run_dir / "chunks",
            log_run_id=chunk_dir.name,
        )

        for filename in CSV_FILES:
            _merge_csv(run_dir / filename, chunk_dir / filename)
        for filename in JSONL_FILES:
            _merge_jsonl(run_dir / filename, chunk_dir / filename)
        completed.add(index)
        checkpoint["completed_chunks"] = sorted(completed)
        _write_json(checkpoint_path, checkpoint)
        metadata["chunks"].append({"index": index, "start_date": chunk_start, "end_date": chunk_end, "status": "complete"})

    _write_json(run_dir / "run_metadata.json", metadata)
    checkpoint["status"] = "complete"
    _write_json(checkpoint_path, checkpoint)
    _write_json(run_dir / "run_complete.json", {"run_id": run_dir.name, "status": "complete", "log_dir": str(run_dir)})
    print(f"log_dir={run_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-agents", type=int, default=30)
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--chunk-days", type=int, default=5)
    parser.add_argument("--community-mode", choices=("off", "on"), default="on")
    parser.add_argument("--fake-news-mode", choices=("off", "on"), default="on")
    parser.add_argument("--fake-news-variant", choices=("bearish", "bullish"), default="bearish")
    parser.add_argument("--processed-news-csv")
    parser.add_argument("--daily-news-csv")
    parser.add_argument("--sim-db")
    parser.add_argument("--output-run-dir")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
