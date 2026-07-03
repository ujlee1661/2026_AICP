#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
except ModuleNotFoundError:
    plt = None
    PdfPages = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COUNTERSIDE = "COUNTERSIDE"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def corr(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return float("nan")
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    denom = math.sqrt(sum(x * x for x in dx) * sum(y * y for y in dy))
    return float("nan") if denom == 0 else sum(x * y for x, y in zip(dx, dy)) / denom


def gini(values: list[float]) -> float:
    values = sorted(max(0.0, v) for v in values)
    if not values or sum(values) == 0:
        return 0.0
    n = len(values)
    weighted = sum((idx + 1) * value for idx, value in enumerate(values))
    return (2 * weighted) / (n * sum(values)) - (n + 1) / n


def load_final_returns(run_dir: Path) -> dict[str, float]:
    latest: dict[str, tuple[int, float]] = {}
    path = run_dir / "portfolio_updates.jsonl"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            event = json.loads(line)
            agent_id = str(event.get("agent_id"))
            turn = int(event.get("turn") or 0)
            rate = num((event.get("state") or {}).get("total_return_rate"))
            if agent_id and turn >= latest.get(agent_id, (-1, 0.0))[0]:
                latest[agent_id] = (turn, rate)
    return {agent_id: rate for agent_id, (_, rate) in latest.items()}


def load_depths(run_dir: Path) -> dict[str, int]:
    rows = read_csv(run_dir / "agent_turns.csv")
    depths: dict[str, int] = {}
    for row in rows:
        if row.get("agent_id") and row.get("news_depth") not in (None, ""):
            depths[str(row["agent_id"])] = int(num(row["news_depth"]))
    return depths


def plot_turnover_returns(pdf: PdfPages, fills: list[dict[str, str]], returns: dict[str, float], depths: dict[str, int]) -> None:
    turnover = defaultdict(float)
    for row in fills:
        agent = row.get("user_id")
        if not agent or agent == COUNTERSIDE:
            continue
        turnover[agent] += abs(num(row.get("executed_price")) * num(row.get("executed_quantity")))
    agents = sorted(set(turnover) | set(returns))
    xs = [turnover[a] for a in agents]
    ys = [returns.get(a, 0.0) * 100 for a in agents]
    colors = [depths.get(a, 0) for a in agents]
    fig, ax = plt.subplots(figsize=(11, 6))
    sc = ax.scatter(xs, ys, c=colors, cmap="viridis", alpha=0.8)
    ax.set_title("Agent Turnover vs Final Return")
    ax.set_xlabel("Turnover value")
    ax.set_ylabel("Final return (%)")
    fig.colorbar(sc, ax=ax, label="news_depth")
    ax.grid(alpha=0.25)
    pdf.savefig(fig)
    plt.close(fig)


def plot_order_deviation(pdf: PdfPages, orders: list[dict[str, str]], daily: list[dict[str, str]]) -> None:
    close_by_date = {}
    for row in daily:
        close_by_date[row["date"]] = num(row.get("closing_price"))
    dates = sorted(close_by_date)
    prev = {date: close_by_date[dates[i - 1]] for i, date in enumerate(dates) if i > 0}
    xs_buy, ys_buy, xs_sell, ys_sell = [], [], [], []
    date_index = {date: idx for idx, date in enumerate(dates)}
    for row in orders:
        date = row.get("date")
        base = prev.get(date or "")
        if not base:
            continue
        dev = (num(row.get("price")) - base) / base * 100
        if row.get("direction") == "buy":
            xs_buy.append(date_index[date] - 0.12)
            ys_buy.append(dev)
        else:
            xs_sell.append(date_index[date] + 0.12)
            ys_sell.append(dev)
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.scatter(xs_buy, ys_buy, s=12, label="buy orders", alpha=0.7)
    ax.scatter(xs_sell, ys_sell, s=12, label="sell orders", alpha=0.7)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Daily Order Price Deviation from Previous Close")
    ax.set_ylabel("Deviation (%)")
    ax.set_xticks(range(0, len(dates), max(1, len(dates) // 12)))
    ax.set_xticklabels([dates[i] for i in range(0, len(dates), max(1, len(dates) // 12))], rotation=45)
    ax.legend()
    ax.grid(alpha=0.25)
    pdf.savefig(fig)
    plt.close(fig)


def plot_disposition(pdf: PdfPages, fills: list[dict[str, str]]) -> None:
    buys: dict[str, list[tuple[float, float]]] = defaultdict(list)
    sell_returns = []
    for row in sorted(fills, key=lambda r: (r.get("date", ""), int(num(r.get("turn"))))):
        agent = row.get("user_id")
        if not agent or agent == COUNTERSIDE:
            continue
        qty = num(row.get("executed_quantity"))
        price = num(row.get("executed_price"))
        if row.get("direction") == "buy":
            buys[agent].append((qty, price))
        elif row.get("direction") == "sell" and buys[agent]:
            held_qty = sum(q for q, _ in buys[agent])
            avg = sum(q * p for q, p in buys[agent]) / held_qty if held_qty else 0
            if avg:
                sell_returns.append((price - avg) / avg * 100)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(sell_returns, bins=30, color="#4f46e5", alpha=0.8)
    ax.axvline(0, color="black", linewidth=1)
    ax.set_title("Disposition Effect: Sell Trade Return Distribution")
    ax.set_xlabel("Return at sell vs average buy cost (%)")
    ax.set_ylabel("Sell count")
    pdf.savefig(fig)
    plt.close(fig)


def plot_clustering(pdf: PdfPages, daily: list[dict[str, str]]) -> None:
    rows = sorted(daily, key=lambda r: (r.get("date", ""), int(num(r.get("turn")))))
    by_date = {}
    for row in rows:
        by_date[row["date"]] = {"close": num(row.get("closing_price")), "volume": num(row.get("volume"))}
    dates = sorted(by_date)
    returns = []
    volumes = []
    for prev, cur in zip(dates, dates[1:]):
        p0, p1 = by_date[prev]["close"], by_date[cur]["close"]
        returns.append(abs((p1 - p0) / p0) if p0 else 0.0)
        volumes.append(by_date[cur]["volume"])
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].scatter(returns[:-1], returns[1:], alpha=0.8)
    axes[0].set_title(f"Volatility clustering r={corr(returns[:-1], returns[1:]):.2f}")
    axes[0].set_xlabel("|return t-1|")
    axes[0].set_ylabel("|return t|")
    axes[1].scatter(volumes[:-1], volumes[1:], alpha=0.8)
    axes[1].set_title(f"Volume clustering r={corr(volumes[:-1], volumes[1:]):.2f}")
    axes[1].set_xlabel("volume t-1")
    axes[1].set_ylabel("volume t")
    pdf.savefig(fig)
    plt.close(fig)


def plot_lorenz(pdf: PdfPages, fills: list[dict[str, str]]) -> None:
    traded = defaultdict(float)
    for row in fills:
        agent = row.get("user_id")
        if agent and agent != COUNTERSIDE:
            traded[agent] += abs(num(row.get("executed_price")) * num(row.get("executed_quantity")))
    values = sorted(traded.values())
    total = sum(values)
    y = [0.0]
    running = 0.0
    for value in values:
        running += value
        y.append(running / total if total else 0.0)
    x = [i / max(1, len(values)) for i in range(len(y))]
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot(x, y, label=f"Lorenz curve (Gini={gini(values):.2f})")
    ax.plot([0, 1], [0, 1], "--", color="gray", label="equality")
    ax.set_title("Trading Inequality")
    ax.set_xlabel("Cumulative agent share")
    ax.set_ylabel("Cumulative traded value share")
    ax.legend()
    ax.grid(alpha=0.25)
    pdf.savefig(fig)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--log-root", type=Path, default=PROJECT_ROOT / "outputs" / "logs")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "reports")
    args = parser.parse_args()

    run_dir = args.log_root / args.run_id
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"deep_analysis_{args.run_id}.pdf"

    fills = read_csv(run_dir / "exchange_fills.csv")
    orders = read_csv(run_dir / "submitted_orders.csv")
    daily = read_csv(run_dir / "daily_exchange_summary.csv")
    returns = load_final_returns(run_dir)
    depths = load_depths(run_dir)

    if PdfPages is None:
        write_fallback_pdf(output_path, fills, orders, daily, returns, depths)
        print(output_path)
        return

    with PdfPages(output_path) as pdf:
        plot_turnover_returns(pdf, fills, returns, depths)
        plot_order_deviation(pdf, orders, daily)
        plot_disposition(pdf, fills)
        plot_clustering(pdf, daily)
        plot_lorenz(pdf, fills)
    print(output_path)


def write_fallback_pdf(
    output_path: Path,
    fills: list[dict[str, str]],
    orders: list[dict[str, str]],
    daily: list[dict[str, str]],
    returns: dict[str, float],
    depths: dict[str, int],
) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()

    def table(rows: list[list[Any]]) -> Table:
        t = Table(rows, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
        return t

    traded = defaultdict(float)
    fill_count = defaultdict(int)
    for row in fills:
        agent = row.get("user_id")
        if agent and agent != COUNTERSIDE:
            traded[agent] += abs(num(row.get("executed_price")) * num(row.get("executed_quantity")))
            fill_count[agent] += 1

    top_traders = sorted(traded.items(), key=lambda item: item[1], reverse=True)[:10]
    final_returns = sorted(returns.items(), key=lambda item: item[1], reverse=True)[:10]
    buy_orders = sum(1 for row in orders if row.get("direction") == "buy")
    sell_orders = sum(1 for row in orders if row.get("direction") == "sell")
    llm_values = list(traded.values())

    rows = sorted(daily, key=lambda r: (r.get("date", ""), int(num(r.get("turn")))))
    by_date = {}
    for row in rows:
        by_date[row["date"]] = {"close": num(row.get("closing_price")), "volume": num(row.get("volume"))}
    dates = sorted(by_date)
    returns_abs = []
    volumes = []
    for prev, cur in zip(dates, dates[1:]):
        p0, p1 = by_date[prev]["close"], by_date[cur]["close"]
        returns_abs.append(abs((p1 - p0) / p0) if p0 else 0.0)
        volumes.append(by_date[cur]["volume"])

    story: list[Any] = [
        Paragraph("TwinMarket Deep Analysis Report", styles["Title"]),
        Paragraph("matplotlib is not installed, so this fallback PDF summarizes the five required sections as tables.", styles["BodyText"]),
        Spacer(1, 12),
        Paragraph("1. Agent Turnover vs Final Return", styles["Heading2"]),
        table([["agent", "traded_value", "fills", "final_return_%", "depth"]] + [
            [agent, f"{value:,.0f}", fill_count[agent], f"{returns.get(agent, 0) * 100:.2f}", depths.get(agent, "")]
            for agent, value in top_traders
        ]),
        Spacer(1, 12),
        Paragraph("2. Order Price Deviation & Fill Range", styles["Heading2"]),
        table([["metric", "value"], ["buy_orders", buy_orders], ["sell_orders", sell_orders], ["total_orders", len(orders)]]),
        Spacer(1, 12),
        Paragraph("3. Disposition Effect", styles["Heading2"]),
        table([["agent", "final_return_%"]] + [[agent, f"{rate * 100:.2f}"] for agent, rate in final_returns]),
        Spacer(1, 12),
        Paragraph("4. Volatility & Volume Clustering", styles["Heading2"]),
        table(
            [
                ["metric", "value"],
                ["volatility_corr", f"{corr(returns_abs[:-1], returns_abs[1:]):.4f}"],
                ["volume_corr", f"{corr(volumes[:-1], volumes[1:]):.4f}"],
            ]
        ),
        Spacer(1, 12),
        Paragraph("5. Trading Inequality", styles["Heading2"]),
        table([["metric", "value"], ["agent_count", len(llm_values)], ["gini_traded_value", f"{gini(llm_values):.4f}"]]),
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(output_path), pagesize=A4).build(story)


if __name__ == "__main__":
    main()
