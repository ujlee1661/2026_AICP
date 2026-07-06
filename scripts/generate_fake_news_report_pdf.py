#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_DIR = PROJECT_ROOT / "outputs" / "logs" / "current"
REPORT_DIR = PROJECT_ROOT / "outputs" / "reports"
FONT_PATHS = [
    Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
]
SYSTEM_USERS = {"INSTITUTIONAL", "COUNTERSIDE", ""}


def register_font() -> str:
    for path in FONT_PATHS:
        if path.exists():
            pdfmetrics.registerFont(TTFont("Korean", str(path)))
            return "Korean"
    return "Helvetica"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def pct(value: Any) -> str:
    return f"{num(value) * 100:.2f}%"


def pct_points(value: Any) -> str:
    return f"{num(value) * 100:+.2f}pp"


def money(value: Any) -> str:
    return f"{num(value):,.0f}원"


def short(text: Any, limit: int = 140) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def action_ko(action: Any) -> str:
    return {"buy": "매수", "sell": "매도", "hold": "보유"}.get(str(action or "").lower(), str(action or ""))


def agent_id(row: dict[str, Any]) -> str:
    return str(row.get("agent_id") or row.get("user_id") or "")


def action_of(row: dict[str, Any]) -> str:
    return str(row.get("action") or row.get("direction") or "").lower()


def quantity_of(row: dict[str, Any]) -> float:
    return num(row.get("quantity") or row.get("executed_quantity") or row.get("filled_quantity"))


def para(text: Any, style: ParagraphStyle) -> Paragraph:
    safe = str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe.replace("\n", "<br/>"), style)


def make_table(data: list[list[Any]], widths: list[float] | None = None, font: str = "Korean") -> Table:
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("FONTSIZE", (0, 0), (-1, 0), 8.2),
                ("FONTSIZE", (0, 1), (-1, -1), 7.0),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3b3f46")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c7ccd4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f7f9")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def styles(font: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    base.add(
        ParagraphStyle(
            name="KTitle",
            parent=base["Title"],
            fontName=font,
            fontSize=18,
            leading=23,
            alignment=TA_CENTER,
            spaceAfter=8,
        )
    )
    base.add(
        ParagraphStyle(
            name="KHeading1",
            parent=base["Heading1"],
            fontName=font,
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#2f4057"),
            spaceBefore=10,
            spaceAfter=6,
        )
    )
    base.add(
        ParagraphStyle(
            name="KHeading2",
            parent=base["Heading2"],
            fontName=font,
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#4b607c"),
            spaceBefore=7,
            spaceAfter=4,
        )
    )
    base.add(
        ParagraphStyle(
            name="KBody",
            parent=base["BodyText"],
            fontName=font,
            fontSize=8.5,
            leading=12,
            alignment=TA_LEFT,
            spaceAfter=5,
        )
    )
    base.add(
        ParagraphStyle(
            name="KSmall",
            parent=base["BodyText"],
            fontName=font,
            fontSize=7,
            leading=9.5,
            alignment=TA_LEFT,
        )
    )
    return base


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Korean", 8)
    canvas.setFillColor(colors.HexColor("#657080"))
    canvas.drawString(18 * mm, 10 * mm, "TwinMarket Korea Fake News Impact Report")
    canvas.drawRightString(192 * mm, 10 * mm, f"{doc.page}")
    canvas.restoreState()


def latest_portfolio_states(portfolio_events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for event in portfolio_events:
        aid = str(event.get("agent_id") or (event.get("state") or {}).get("agent_id") or "")
        state = event.get("state") or {}
        if aid and state:
            latest[aid] = state
    return latest


def state_initial_value(state: dict[str, Any]) -> float:
    total = num(state.get("total_value"))
    ret = num(state.get("total_return_rate"))
    if total and ret > -0.999:
        return total / (1.0 + ret)
    return 100_000_000.0


def final_return(state: dict[str, Any]) -> float:
    if "total_return_rate" in state:
        return num(state.get("total_return_rate"))
    initial = state_initial_value(state)
    return (num(state.get("total_value")) - initial) / initial if initial else 0.0


def load_run(run_dir: Path) -> dict[str, Any]:
    meta = read_json(run_dir / "run_metadata.json")
    if not meta:
        raise FileNotFoundError(f"run_metadata.json not found in {run_dir}")
    agent_rows = read_csv(run_dir / "agent_turns.csv")
    orders = read_csv(run_dir / "submitted_orders.csv")
    fills = read_csv(run_dir / "exchange_fills.csv")
    daily = read_csv(run_dir / "daily_exchange_summary.csv")
    events = read_jsonl(run_dir / "agent_turns.jsonl")
    portfolios = read_jsonl(run_dir / "portfolio_updates.jsonl")
    states = latest_portfolio_states(portfolios)
    dates = sorted({row.get("date", "") for row in daily if row.get("date")})
    agents = [str(aid) for aid in meta.get("agent_ids") or sorted({agent_id(row) for row in agent_rows})]
    return {
        "run_dir": run_dir,
        "meta": meta,
        "agent_rows": agent_rows,
        "orders": orders,
        "fills": fills,
        "daily": daily,
        "events": events,
        "portfolios": portfolios,
        "states": states,
        "dates": dates,
        "agents": agents,
    }


def fake_items_from_csv(row: dict[str, str]) -> list[dict[str, Any]]:
    ids = [item.strip() for item in str(row.get("fake_public_ids") or "").split(",") if item.strip()]
    synthetic_ids = [item.strip() for item in str(row.get("fake_synthetic_ids") or "").split(",") if item.strip()]
    events = []
    try:
        events = json.loads(row.get("fake_related_events") or "[]")
    except json.JSONDecodeError:
        events = []
    result = []
    for idx, fake_id in enumerate(ids):
        result.append(
            {
                "id": fake_id,
                "synthetic_id": synthetic_ids[idx] if idx < len(synthetic_ids) else "",
                "related_event": events[idx] if idx < len(events) else "",
                "sources": [],
            }
        )
    return result


def extract_fake_exposures(run: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if run["events"]:
        for event in run["events"]:
            audit = event.get("fake_news_audit") or {}
            if not audit.get("fake_exposed") and not any(num(audit.get(k)) for k in ("fake_base_count", "fake_read_count", "fake_search_count", "fake_selected_count")):
                continue
            agent = event.get("agent") or {}
            context = event.get("context") or {}
            decision = event.get("decision") or {}
            interp = event.get("news_interpretation") or {}
            belief = event.get("belief") or {}
            items = audit.get("items") or []
            if not items:
                items = [{"id": fake_id, "sources": []} for fake_id in audit.get("fake_public_ids") or []]
            for item in items:
                sources = item.get("sources") or []
                rows.append(
                    {
                        "run_id": run["meta"].get("run_id", ""),
                        "date": event.get("date", ""),
                        "turn": event.get("turn", ""),
                        "subturn": context.get("subturn", ""),
                        "agent_id": agent.get("agent_id", ""),
                        "news_depth": agent.get("news_depth", context.get("news_context", {}).get("news_depth", "")),
                        "fake_public_id": item.get("id", ""),
                        "fake_synthetic_id": item.get("synthetic_id", ""),
                        "fake_title": item.get("title", ""),
                        "related_event": item.get("related_event", ""),
                        "misinformation_type": item.get("misinformation_type", ""),
                        "sources": ", ".join(sources),
                        "base_exposed": "base" in sources or num(audit.get("fake_base_count")) > 0,
                        "read_exposed": "read" in sources or num(audit.get("fake_read_count")) > 0,
                        "search_exposed": "search" in sources or num(audit.get("fake_search_count")) > 0,
                        "selected_by_agent": "selected" in sources or num(audit.get("fake_selected_count")) > 0,
                        "news_sentiment": interp.get("news_sentiment", ""),
                        "action": decision.get("action", ""),
                        "quantity": decision.get("quantity", ""),
                        "belief_summary": belief.get("belief_summary", ""),
                        "decision_reason": decision.get("reason", ""),
                    }
                )
        return rows

    for row in run["agent_rows"]:
        if str(row.get("fake_exposed", "")).lower() not in {"true", "1", "yes"}:
            continue
        for item in fake_items_from_csv(row):
            rows.append(
                {
                    "run_id": row.get("run_id", ""),
                    "date": row.get("date", ""),
                    "turn": row.get("turn", ""),
                    "subturn": row.get("subturn", ""),
                    "agent_id": row.get("agent_id", ""),
                    "news_depth": row.get("news_depth", ""),
                    "fake_public_id": item.get("id", ""),
                    "fake_synthetic_id": item.get("synthetic_id", ""),
                    "fake_title": item.get("title", ""),
                    "related_event": item.get("related_event", ""),
                    "misinformation_type": item.get("misinformation_type", ""),
                    "sources": ", ".join(item.get("sources") or []),
                    "base_exposed": num(row.get("fake_base_count")) > 0,
                    "read_exposed": num(row.get("fake_read_count")) > 0,
                    "search_exposed": num(row.get("fake_search_count")) > 0,
                    "selected_by_agent": num(row.get("fake_selected_count")) > 0,
                    "news_sentiment": row.get("news_sentiment", ""),
                    "action": row.get("action", ""),
                    "quantity": row.get("quantity", ""),
                    "belief_summary": row.get("belief_summary", ""),
                    "decision_reason": row.get("decision_reason", ""),
                }
            )
    return rows


def summarize_run(run: dict[str, Any], exposures: list[dict[str, Any]]) -> dict[str, Any]:
    states = run["states"]
    returns = [final_return(states[aid]) for aid in run["agents"] if aid in states]
    total_value = sum(num(states[aid].get("total_value")) for aid in run["agents"] if aid in states)
    initial_value = sum(state_initial_value(states[aid]) for aid in run["agents"] if aid in states)
    fills = [row for row in run["fills"] if agent_id(row) not in SYSTEM_USERS]
    buy_qty = sum(quantity_of(row) for row in fills if action_of(row) == "buy")
    sell_qty = sum(quantity_of(row) for row in fills if action_of(row) == "sell")
    action_counts = Counter(action_of(row) for row in run["agent_rows"])
    exposure_agents = {row["agent_id"] for row in exposures if row.get("agent_id")}
    exposure_dates = {row["date"] for row in exposures if row.get("date")}
    fake_ids = {row["fake_public_id"] for row in exposures if row.get("fake_public_id")}
    selected = [row for row in exposures if row.get("selected_by_agent") in {True, "True", "true", "1"}]
    return {
        "run_id": run["meta"].get("run_id", run["run_dir"].name),
        "fake_news_mode": run["meta"].get("fake_news_mode", ""),
        "agent_count": len(run["agents"]),
        "date_count": len(run["dates"]),
        "date_start": run["dates"][0] if run["dates"] else "",
        "date_end": run["dates"][-1] if run["dates"] else "",
        "turn_count": len(run["agent_rows"]),
        "order_count": len(run["orders"]),
        "fill_count": len(fills),
        "buy_qty": buy_qty,
        "sell_qty": sell_qty,
        "net_qty": buy_qty - sell_qty,
        "total_value": total_value,
        "initial_value": initial_value,
        "total_pnl": total_value - initial_value,
        "portfolio_return": (total_value - initial_value) / initial_value if initial_value else 0.0,
        "avg_agent_return": mean(returns) if returns else 0.0,
        "median_agent_return": median(returns) if returns else 0.0,
        "min_agent_return": min(returns) if returns else 0.0,
        "max_agent_return": max(returns) if returns else 0.0,
        "action_buy": action_counts.get("buy", 0),
        "action_sell": action_counts.get("sell", 0),
        "action_hold": action_counts.get("hold", 0),
        "fake_exposure_count": len(exposures),
        "fake_unique_news_count": len(fake_ids),
        "fake_exposed_agent_count": len(exposure_agents),
        "fake_exposed_date_count": len(exposure_dates),
        "fake_selected_count": len(selected),
    }


def daily_net_fills(run: dict[str, Any]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = defaultdict(lambda: {"buy_qty": 0.0, "sell_qty": 0.0, "net_qty": 0.0})
    for row in run["fills"]:
        aid = agent_id(row)
        if aid in SYSTEM_USERS:
            continue
        qty = quantity_of(row)
        if action_of(row) == "buy":
            result[row.get("date", "")]["buy_qty"] += qty
            result[row.get("date", "")]["net_qty"] += qty
        elif action_of(row) == "sell":
            result[row.get("date", "")]["sell_qty"] += qty
            result[row.get("date", "")]["net_qty"] -= qty
    return dict(result)


def agent_returns(run: dict[str, Any]) -> dict[str, float]:
    return {aid: final_return(state) for aid, state in run["states"].items() if aid not in SYSTEM_USERS}


def order_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("date", "")), str(row.get("turn", "")), agent_id(row))


def compare_runs(fake_run: dict[str, Any], baseline_run: dict[str, Any]) -> dict[str, Any]:
    fake_returns = agent_returns(fake_run)
    base_returns = agent_returns(baseline_run)
    common_agents = sorted(set(fake_returns) & set(base_returns))
    agent_rows = [
        {
            "agent_id": aid,
            "baseline_return": base_returns[aid],
            "fake_return": fake_returns[aid],
            "delta_return": fake_returns[aid] - base_returns[aid],
        }
        for aid in common_agents
    ]
    agent_rows.sort(key=lambda row: (row["delta_return"], row["agent_id"]))

    fake_daily = daily_net_fills(fake_run)
    base_daily = daily_net_fills(baseline_run)
    common_dates = sorted(set(fake_daily) & set(base_daily))
    daily_rows = [
        {
            "date": day,
            "baseline_net_qty": base_daily[day]["net_qty"],
            "fake_net_qty": fake_daily[day]["net_qty"],
            "delta_net_qty": fake_daily[day]["net_qty"] - base_daily[day]["net_qty"],
        }
        for day in common_dates
    ]

    fake_orders = {order_key(row): row for row in fake_run["orders"]}
    base_orders = {order_key(row): row for row in baseline_run["orders"]}
    common_order_keys = sorted(set(fake_orders) & set(base_orders))
    order_rows = []
    for key in common_order_keys:
        fake_order = fake_orders[key]
        base_order = base_orders[key]
        if action_of(fake_order) == action_of(base_order) and quantity_of(fake_order) == quantity_of(base_order):
            continue
        order_rows.append(
            {
                "date": key[0],
                "turn": key[1],
                "agent_id": key[2],
                "baseline_action": action_of(base_order),
                "baseline_qty": quantity_of(base_order),
                "fake_action": action_of(fake_order),
                "fake_qty": quantity_of(fake_order),
                "delta_qty": quantity_of(fake_order) - quantity_of(base_order),
            }
        )

    return {
        "common_agents": common_agents,
        "common_dates": common_dates,
        "agent_return_deltas": agent_rows,
        "daily_net_deltas": daily_rows,
        "order_deltas": order_rows,
        "avg_delta_return": mean([row["delta_return"] for row in agent_rows]) if agent_rows else 0.0,
        "median_delta_return": median([row["delta_return"] for row in agent_rows]) if agent_rows else 0.0,
    }


def exposure_tables(exposures: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_news: dict[str, dict[str, Any]] = {}
    for row in exposures:
        fid = row.get("fake_public_id") or "(unknown)"
        item = by_news.setdefault(
            fid,
            {
                "fake_public_id": fid,
                "fake_synthetic_id": row.get("fake_synthetic_id", ""),
                "fake_title": row.get("fake_title", ""),
                "related_event": row.get("related_event", ""),
                "misinformation_type": row.get("misinformation_type", ""),
                "exposure_count": 0,
                "agent_ids": set(),
                "dates": set(),
                "selected_count": 0,
                "actions": Counter(),
            },
        )
        item["exposure_count"] += 1
        item["agent_ids"].add(row.get("agent_id", ""))
        item["dates"].add(row.get("date", ""))
        if row.get("selected_by_agent") in {True, "True", "true", "1"}:
            item["selected_count"] += 1
        item["actions"][str(row.get("action") or "")] += 1
    news_rows = []
    for item in by_news.values():
        actions = item.pop("actions")
        news_rows.append(
            {
                **item,
                "agent_count": len({aid for aid in item["agent_ids"] if aid}),
                "date_count": len({day for day in item["dates"] if day}),
                "agent_ids": ", ".join(sorted(aid for aid in item["agent_ids"] if aid)),
                "dates": ", ".join(sorted(day for day in item["dates"] if day)),
                "action_summary": ", ".join(f"{action_ko(k)} {v}" for k, v in sorted(actions.items()) if k),
            }
        )
    news_rows.sort(key=lambda row: (-row["exposure_count"], row["fake_public_id"]))

    by_agent: dict[str, dict[str, Any]] = {}
    for row in exposures:
        aid = row.get("agent_id") or "(unknown)"
        item = by_agent.setdefault(
            aid,
            {
                "agent_id": aid,
                "news_depth": row.get("news_depth", ""),
                "exposure_count": 0,
                "fake_ids": set(),
                "dates": set(),
                "selected_count": 0,
                "actions": Counter(),
            },
        )
        item["exposure_count"] += 1
        item["fake_ids"].add(row.get("fake_public_id", ""))
        item["dates"].add(row.get("date", ""))
        if row.get("selected_by_agent") in {True, "True", "true", "1"}:
            item["selected_count"] += 1
        item["actions"][str(row.get("action") or "")] += 1
    agent_rows = []
    for item in by_agent.values():
        actions = item.pop("actions")
        agent_rows.append(
            {
                **item,
                "fake_news_count": len({fid for fid in item["fake_ids"] if fid}),
                "date_count": len({day for day in item["dates"] if day}),
                "fake_ids": ", ".join(sorted(fid for fid in item["fake_ids"] if fid)),
                "dates": ", ".join(sorted(day for day in item["dates"] if day)),
                "action_summary": ", ".join(f"{action_ko(k)} {v}" for k, v in sorted(actions.items()) if k),
            }
        )
    agent_rows.sort(key=lambda row: (-row["exposure_count"], row["agent_id"]))
    return {"by_news": news_rows, "by_agent": agent_rows}


def build_story(
    *,
    fake_run: dict[str, Any],
    baseline_run: dict[str, Any] | None,
    exposures: list[dict[str, Any]],
    summary: dict[str, Any],
    exposure_summary: dict[str, list[dict[str, Any]]],
    comparison: dict[str, Any] | None,
    style: dict[str, ParagraphStyle],
    font: str,
    max_rows: int,
) -> list[Any]:
    story: list[Any] = []
    meta = fake_run["meta"]
    story.append(para("Fake News Impact Report", style["KTitle"]))
    story.append(
        para(
            f"실행 ID: {summary['run_id']} / fake_news_mode={summary.get('fake_news_mode') or 'unknown'} / "
            f"기간: {summary['date_start']} ~ {summary['date_end']} / 에이전트 {summary['agent_count']}명",
            style["KBody"],
        )
    )
    if baseline_run is None:
        story.append(para("이 보고서는 단일 실행 로그 기준입니다. `--baseline-run-dir`를 지정하면 동일 에이전트/날짜의 baseline 대비 차이를 추가 계산합니다.", style["KBody"]))
    else:
        story.append(para(f"비교 기준 baseline 실행: {baseline_run['meta'].get('run_id', baseline_run['run_dir'].name)}", style["KBody"]))

    story.append(para("1. 실행 및 성과 요약", style["KHeading1"]))
    overview = [
        ["항목", "값"],
        ["뉴스 입력", f"processed={meta.get('processed_news_csv', '')}, daily={meta.get('daily_news_csv', '')}"],
        ["정보/실행 조건", f"information_mode={meta.get('information_mode', '')}, decision_space={meta.get('decision_space', '')}, seed={meta.get('random_seed', '')}"],
        ["가짜뉴스 노출", f"노출 record {summary['fake_exposure_count']}건, fake news {summary['fake_unique_news_count']}개, 에이전트 {summary['fake_exposed_agent_count']}명, 날짜 {summary['fake_exposed_date_count']}일, selected {summary['fake_selected_count']}건"],
        ["판단 분포", f"매수 {summary['action_buy']} / 매도 {summary['action_sell']} / 보유 {summary['action_hold']}"],
        ["주문/체결", f"주문 {summary['order_count']}건, 체결 {summary['fill_count']}건, 순수량 {summary['net_qty']:,.0f}주"],
        ["PnL", f"총 평가손익 {money(summary['total_pnl'])}, 포트폴리오 수익률 {pct(summary['portfolio_return'])}, 평균 에이전트 수익률 {pct(summary['avg_agent_return'])}"],
        ["로그 위치", str(fake_run["run_dir"])],
    ]
    story.append(make_table([[para(c, style["KSmall"]) for c in row] for row in overview], [42 * mm, 128 * mm], font))

    story.append(para("2. 가짜뉴스별 노출 요약", style["KHeading1"]))
    if exposure_summary["by_news"]:
        rows = [["fake id", "관련 이벤트/유형", "제목", "노출", "에이전트", "선택", "판단"]]
        for row in exposure_summary["by_news"][:max_rows]:
            rows.append(
                [
                    row["fake_public_id"],
                    f"{short(row.get('related_event'), 55)}\n{row.get('misinformation_type', '')}",
                    short(row.get("fake_title") or row.get("fake_synthetic_id"), 90),
                    f"{row['exposure_count']}건 / {row['date_count']}일",
                    short(row["agent_ids"], 90),
                    str(row["selected_count"]),
                    row["action_summary"],
                ]
            )
        story.append(make_table([[para(c, style["KSmall"]) for c in row] for row in rows], [28 * mm, 35 * mm, 42 * mm, 22 * mm, 25 * mm, 13 * mm, 20 * mm], font))
    else:
        story.append(para("이 실행 로그에서 fake_exposed record가 발견되지 않았습니다. fake_news_mode가 off였거나, 해당 기간에 fake row가 윈도우에 들어오지 않았을 수 있습니다.", style["KBody"]))

    story.append(para("3. 에이전트별 가짜뉴스 노출 및 반응", style["KHeading1"]))
    if exposure_summary["by_agent"]:
        rows = [["에이전트", "Depth", "노출", "fake 뉴스", "노출 날짜", "선택", "판단 분포"]]
        for row in exposure_summary["by_agent"][:max_rows]:
            rows.append(
                [
                    row["agent_id"],
                    row["news_depth"],
                    str(row["exposure_count"]),
                    short(row["fake_ids"], 80),
                    short(row["dates"], 75),
                    str(row["selected_count"]),
                    row["action_summary"],
                ]
            )
        story.append(make_table([[para(c, style["KSmall"]) for c in row] for row in rows], [19 * mm, 13 * mm, 15 * mm, 48 * mm, 42 * mm, 14 * mm, 34 * mm], font))

    story.append(para("4. 노출 턴 상세 로그", style["KHeading1"]))
    if exposures:
        rows = [["일자/턴", "에이전트", "fake 뉴스", "노출 경로", "뉴스감성", "판단", "근거 요약"]]
        for row in exposures[:max_rows]:
            source_text = row.get("sources") or ", ".join(
                name
                for name, key in [("base", "base_exposed"), ("read", "read_exposed"), ("search", "search_exposed"), ("selected", "selected_by_agent")]
                if row.get(key) in {True, "True", "true", "1"}
            )
            rows.append(
                [
                    f"{row.get('date')}\nT{row.get('turn')} {row.get('subturn')}",
                    f"{row.get('agent_id')}\nD{row.get('news_depth')}",
                    short(row.get("fake_title") or row.get("fake_public_id"), 75),
                    source_text,
                    row.get("news_sentiment", ""),
                    f"{action_ko(row.get('action'))} {row.get('quantity')}",
                    short(row.get("decision_reason") or row.get("belief_summary"), 150),
                ]
            )
        story.append(make_table([[para(c, style["KSmall"]) for c in row] for row in rows], [22 * mm, 18 * mm, 38 * mm, 25 * mm, 20 * mm, 20 * mm, 42 * mm], font))

    if comparison is not None:
        story.append(PageBreak())
        story.append(para("5. Baseline 대비 영향 비교", style["KHeading1"]))
        rows = [
            ["항목", "값"],
            ["공통 비교 범위", f"에이전트 {len(comparison['common_agents'])}명, 체결 비교 날짜 {len(comparison['common_dates'])}일"],
            ["평균 수익률 차이", pct_points(comparison["avg_delta_return"])],
            ["중앙값 수익률 차이", pct_points(comparison["median_delta_return"])],
            ["주문 변경 record", f"{len(comparison['order_deltas'])}건"],
        ]
        story.append(make_table([[para(c, style["KSmall"]) for c in row] for row in rows], [42 * mm, 128 * mm], font))

        story.append(para("5-1. 에이전트별 최종 수익률 차이", style["KHeading2"]))
        agent_delta_rows = [["에이전트", "Baseline", "Fake", "차이"]]
        for row in comparison["agent_return_deltas"][:max_rows]:
            agent_delta_rows.append([row["agent_id"], pct(row["baseline_return"]), pct(row["fake_return"]), pct_points(row["delta_return"])])
        story.append(make_table([[para(c, style["KSmall"]) for c in row] for row in agent_delta_rows], [35 * mm, 35 * mm, 35 * mm, 35 * mm], font))

        story.append(para("5-2. 일자별 LLM 순체결 수량 차이", style["KHeading2"]))
        daily_rows = [["일자", "Baseline 순수량", "Fake 순수량", "차이"]]
        for row in comparison["daily_net_deltas"][:max_rows]:
            daily_rows.append([row["date"], f"{row['baseline_net_qty']:,.0f}주", f"{row['fake_net_qty']:,.0f}주", f"{row['delta_net_qty']:+,.0f}주"])
        story.append(make_table([[para(c, style["KSmall"]) for c in row] for row in daily_rows], [35 * mm, 40 * mm, 40 * mm, 40 * mm], font))

        story.append(para("5-3. 공통 턴 주문 변경", style["KHeading2"]))
        order_rows = [["일자/턴", "에이전트", "Baseline", "Fake", "수량차"]]
        for row in comparison["order_deltas"][:max_rows]:
            order_rows.append(
                [
                    f"{row['date']}\nT{row['turn']}",
                    row["agent_id"],
                    f"{action_ko(row['baseline_action'])} {row['baseline_qty']:,.0f}",
                    f"{action_ko(row['fake_action'])} {row['fake_qty']:,.0f}",
                    f"{row['delta_qty']:+,.0f}",
                ]
            )
        story.append(make_table([[para(c, style["KSmall"]) for c in row] for row in order_rows], [25 * mm, 25 * mm, 40 * mm, 40 * mm, 30 * mm], font))

    story.append(PageBreak())
    story.append(para("해석 및 후속 비교 설계", style["KHeading1"]))
    story.append(
        para(
            "이 보고서는 실행 로그에 기록된 fake_news_audit를 기준으로 노출 여부를 집계한다. "
            "동일 기간, 동일 seed, 동일 에이전트 집합으로 baseline과 fake run을 각각 생성하면 "
            "공통 에이전트의 최종 수익률 차이, 일자별 순체결 수량 차이, 공통 턴 주문 변경을 직접 비교할 수 있다. "
            "현재 실행 기간이나 에이전트 집합이 다르면 비교 표는 공통 교집합만 사용하므로, 결과 해석 시 표본 범위를 먼저 확인해야 한다.",
            style["KBody"],
        )
    )
    return story


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a fake-news exposure and impact report from simulation logs.")
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR, help="Fake-news or target simulation run directory.")
    parser.add_argument("--baseline-run-dir", type=Path, default=None, help="Optional baseline run directory for comparison.")
    parser.add_argument("--output", type=Path, default=None, help="Output PDF path.")
    parser.add_argument("--summary-json", type=Path, default=None, help="Optional summary JSON path.")
    parser.add_argument("--exposure-csv", type=Path, default=None, help="Optional fake exposure CSV path.")
    parser.add_argument("--max-rows", type=int, default=40, help="Maximum detail rows per section.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    font = register_font()
    style = styles(font)

    fake_run = load_run(args.run_dir)
    exposures = extract_fake_exposures(fake_run)
    summary = summarize_run(fake_run, exposures)
    exposure_summary = exposure_tables(exposures)

    baseline_run = load_run(args.baseline_run_dir) if args.baseline_run_dir else None
    comparison = compare_runs(fake_run, baseline_run) if baseline_run is not None else None

    output = args.output
    if output is None:
        run_id = summary["run_id"] or args.run_dir.name
        output = REPORT_DIR / f"fake_news_impact_{run_id}.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)

    summary_json = args.summary_json or output.with_suffix(".summary.json")
    exposure_csv = args.exposure_csv or output.with_suffix(".exposures.csv")

    payload = {
        "summary": summary,
        "fake_news_by_news": exposure_summary["by_news"],
        "fake_news_by_agent": exposure_summary["by_agent"],
        "comparison": comparison,
    }
    summary_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=list), encoding="utf-8")
    write_csv(
        exposure_csv,
        exposures,
        [
            "run_id",
            "date",
            "turn",
            "subturn",
            "agent_id",
            "news_depth",
            "fake_public_id",
            "fake_synthetic_id",
            "fake_title",
            "related_event",
            "misinformation_type",
            "sources",
            "base_exposed",
            "read_exposed",
            "search_exposed",
            "selected_by_agent",
            "news_sentiment",
            "action",
            "quantity",
            "belief_summary",
            "decision_reason",
        ],
    )

    story = build_story(
        fake_run=fake_run,
        baseline_run=baseline_run,
        exposures=exposures,
        summary=summary,
        exposure_summary=exposure_summary,
        comparison=comparison,
        style=style,
        font=font,
        max_rows=max(1, args.max_rows),
    )
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="TwinMarket Korea Fake News Impact Report",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"report={output}")
    print(f"summary_json={summary_json}")
    print(f"exposure_csv={exposure_csv}")


if __name__ == "__main__":
    main()
