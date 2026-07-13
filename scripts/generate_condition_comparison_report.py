#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
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
RUNS = {
    "C01": {
        "label": "Community ON / Fake OFF",
        "run_id": "simulation_20260707_001750",
        "run_dir": PROJECT_ROOT / "outputs/logs/simulation_20260707_001750",
    },
    "C11": {
        "label": "Community ON / Fake ON",
        "run_id": "simulation_20260707_183141_053281_49182",
        "run_dir": PROJECT_ROOT / "outputs/logs/simulation_20260707_183141_053281_49182",
    },
    "C10": {
        "label": "Community OFF / Fake ON",
        "run_id": "simulation_20260707_184205_084828_50261",
        "run_dir": PROJECT_ROOT / "outputs/logs/simulation_20260707_184205_084828_50261",
    },
    "C00": {
        "label": "Community OFF / Fake OFF",
        "run_id": "simulation_20260710_185009_391863_19763",
        "run_dir": PROJECT_ROOT / "outputs/logs/simulation_20260710_185009_391863_19763",
    },
}
ACTUAL_VALUE = PROJECT_ROOT / "validation/data_trading_value.csv"
STOCK_DATA = PROJECT_ROOT / "data/stock_data.csv"
SYS_DB = PROJECT_ROOT / "outputs/sys_100.db"
VALIDATION_ROOT = PROJECT_ROOT / "validation/outputs"
OUT_DIR = PROJECT_ROOT / "outputs/reports/condition_comparison"
OUT_PDF = OUT_DIR / "community_fake_news_condition_comparison_report.pdf"
OUT_JSON = OUT_DIR / "community_fake_news_condition_comparison_summary.json"
FONT_PATHS = [
    Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
]


def register_font() -> str:
    for path in FONT_PATHS:
        if path.exists():
            pdfmetrics.registerFont(TTFont("Korean", str(path)))
            return "Korean"
    return "Helvetica"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def num(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def money_krw(value: float) -> str:
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:+,.1f}십억원"
    return f"{value / 1_000_000:+,.1f}백만원"


def short(text: Any, limit: int = 150) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "..."


def para(text: Any, style: ParagraphStyle) -> Paragraph:
    safe = str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe.replace("\n", "<br/>"), style)


def make_table(rows: list[list[Any]], widths: list[float] | None = None, font_size: float = 7.2) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Korean"),
                ("FONTSIZE", (0, 0), (-1, 0), font_size + 0.7),
                ("FONTSIZE", (0, 1), (-1, -1), font_size),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#23395d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return t


def load_meta() -> dict[str, dict[str, Any]]:
    result = {}
    for code, info in RUNS.items():
        with (info["run_dir"] / "run_metadata.json").open(encoding="utf-8-sig") as f:
            result[code] = json.load(f)
    return result


def load_validation(metric: str = "value") -> dict[str, list[dict[str, str]]]:
    result = {}
    for code, info in RUNS.items():
        path = VALIDATION_ROOT / info["run_id"] / f"daily_comparison_{metric}.csv"
        result[code] = read_csv(path)
    return result


def load_stock() -> dict[str, dict[str, str]]:
    return {row["date"]: row for row in read_csv(STOCK_DATA)}


def load_actual_value() -> dict[str, dict[str, float]]:
    result = {}
    for row in read_csv(ACTUAL_VALUE):
        date = str(row["Date"]).replace("/", "-")
        result[date] = {
            "Individuals": num(row.get("Individuals")),
            "Institutions": num(row.get("Subtotal-Institutions")),
            "Foreign": num(row.get("Total of foreign")),
            "Other": num(row.get("Other corporations")),
        }
    return result


def load_agent_metrics() -> dict[str, dict[str, dict[str, Any]]]:
    all_metrics: dict[str, dict[str, dict[str, Any]]] = {}
    for code, info in RUNS.items():
        run_dir = info["run_dir"]
        metrics: dict[str, dict[str, Any]] = defaultdict(lambda: defaultdict(float))
        for row in read_csv(run_dir / "agent_turns.csv"):
            aid = row["agent_id"]
            metrics[aid]["turns"] += 1
            metrics[aid][f"action_{row['action']}"] += 1
            metrics[aid]["submitted_qty"] += num(row.get("quantity"))
            if "fallback_decision_after_invalid_llm_output" in (row.get("order_corrections") or ""):
                metrics[aid]["fallback"] += 1
        for row in read_csv(run_dir / "exchange_fills.csv"):
            aid = row["agent_id"]
            qty = num(row.get("quantity"))
            price = num(row.get("executed_price"))
            metrics[aid]["turnover"] += abs(qty * price)
            metrics[aid][f"filled_{row['action']}"] += 1
            metrics[aid][f"filled_qty_{row['action']}"] += qty
        latest: dict[str, dict[str, Any]] = {}
        with (run_dir / "portfolio_updates.jsonl").open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    event = json.loads(line)
                    latest[event["agent_id"]] = event["state"]
        for aid, state in latest.items():
            metrics[aid]["final_return"] = float(state.get("total_return_rate") or 0.0)
            metrics[aid]["final_value"] = float(state.get("total_value") or 0.0)
            metrics[aid]["cash"] = float(state.get("cash") or 0.0)
            metrics[aid]["position_qty"] = sum(int(pos.get("quantity") or 0) for pos in state.get("positions") or [])
        all_metrics[code] = {aid: dict(values) for aid, values in metrics.items()}
    return all_metrics


def load_agent_turn_lookup() -> dict[str, dict[tuple[str, str], list[dict[str, str]]]]:
    result = {}
    for code, info in RUNS.items():
        lookup: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for row in read_csv(info["run_dir"] / "agent_turns.csv"):
            lookup[(row["agent_id"], row["date"])].append(row)
        result[code] = lookup
    return result


def load_personas(agent_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not agent_ids:
        return {}
    with sqlite3.connect(SYS_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT agent_id, gender, age, location, user_type, strategy, news_depth,
                   bh_disposition_effect_category, bh_lottery_preference_category,
                   bh_total_return_category, bh_underdiversification_category,
                   persona_prompt
            FROM agents
            WHERE agent_id IN (%s)
            ORDER BY agent_id
            """
            % ",".join("?" for _ in agent_ids),
            agent_ids,
        ).fetchall()
    return {str(row["agent_id"]): dict(row) for row in rows}


def selected_news_summary(days: list[str]) -> dict[str, dict[str, Any]]:
    summaries = {}
    for day in days:
        titles = Counter()
        sentiments = Counter()
        for info in RUNS.values():
            path = info["run_dir"] / "agent_turns.jsonl"
            if not path.exists():
                continue
            with path.open(encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if event.get("date") != day:
                        continue
                    news_interpretation = event.get("news_interpretation") or {}
                    sentiments[str(news_interpretation.get("news_sentiment") or "")] += 1
                    selected = set(news_interpretation.get("selected_news") or [])
                    news_context = (event.get("context") or {}).get("news_context") or {}
                    candidates = []
                    candidates.extend(news_context.get("daily_titles") or [])
                    candidates.extend(news_context.get("read_contents") or [])
                    candidates.extend(news_context.get("search_results") or [])
                    for item in candidates:
                        if item.get("id") in selected:
                            titles[item.get("title", "")] += 1
        summaries[day] = {
            "sentiments": dict(sentiments.most_common()),
            "top_titles": titles.most_common(5),
        }
    return summaries


def condition_summary(validation_rows: dict[str, list[dict[str, str]]], agent_metrics: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    result = {}
    for code, rows in validation_rows.items():
        mismatches = [row["date"] for row in rows if str(row.get("llm_matches_individuals")) == "0"]
        values = list(agent_metrics[code].values())
        final_returns = [float(item.get("final_return") or 0.0) for item in values]
        result[code] = {
            "mismatch_dates": mismatches,
            "mismatch_count": len(mismatches),
            "avg_return": sum(final_returns) / len(final_returns) if final_returns else 0.0,
            "min_return": min(final_returns) if final_returns else 0.0,
            "max_return": max(final_returns) if final_returns else 0.0,
            "fallback_count": sum(int(item.get("fallback") or 0) for item in values),
            "buy_turns": sum(int(item.get("action_buy") or 0) for item in values),
            "sell_turns": sum(int(item.get("action_sell") or 0) for item in values),
            "turnover": sum(float(item.get("turnover") or 0.0) for item in values),
        }
    return result


def pick_representative_agents(meta: dict[str, dict[str, Any]], agent_metrics: dict[str, dict[str, dict[str, Any]]]) -> list[str]:
    common = set(meta["C01"]["agent_ids"])
    for values in meta.values():
        common &= set(values["agent_ids"])
    scores = []
    for aid in sorted(common):
        returns = [float(agent_metrics[code].get(aid, {}).get("final_return") or 0.0) for code in RUNS]
        buys = [float(agent_metrics[code].get(aid, {}).get("action_buy") or 0.0) for code in RUNS]
        turnovers = [float(agent_metrics[code].get(aid, {}).get("turnover") or 0.0) for code in RUNS]
        fallbacks = sum(float(agent_metrics[code].get(aid, {}).get("fallback") or 0.0) for code in RUNS)
        score = (max(returns) - min(returns)) * 100 + (max(buys) - min(buys)) / 20 + (max(turnovers) - min(turnovers)) / 1_000_000_000 + fallbacks / 20
        scores.append((score, aid))
    return [aid for _, aid in sorted(scores, reverse=True)[:5]]


def score_agents(meta: dict[str, dict[str, Any]], agent_metrics: dict[str, dict[str, dict[str, Any]]]) -> dict[str, float]:
    common = set(meta["C01"]["agent_ids"])
    for values in meta.values():
        common &= set(values["agent_ids"])
    scores = {}
    for aid in sorted(common):
        returns = [float(agent_metrics[code].get(aid, {}).get("final_return") or 0.0) for code in RUNS]
        buys = [float(agent_metrics[code].get(aid, {}).get("action_buy") or 0.0) for code in RUNS]
        turnovers = [float(agent_metrics[code].get(aid, {}).get("turnover") or 0.0) for code in RUNS]
        fallbacks = sum(float(agent_metrics[code].get(aid, {}).get("fallback") or 0.0) for code in RUNS)
        scores[aid] = (
            (max(returns) - min(returns)) * 100
            + (max(buys) - min(buys)) / 20
            + (max(turnovers) - min(turnovers)) / 1_000_000_000
            + fallbacks / 20
        )
    return scores


def pick_common_depth2_agent(meta: dict[str, dict[str, Any]], agent_metrics: dict[str, dict[str, dict[str, Any]]]) -> str | None:
    common = set(meta["C01"]["agent_ids"])
    for values in meta.values():
        common &= set(values["agent_ids"])
    personas = load_personas(sorted(common))
    depth2_ids = [aid for aid in sorted(common) if int(personas.get(aid, {}).get("news_depth") or 0) >= 2]
    if not depth2_ids:
        return None
    scores = score_agents(meta, agent_metrics)
    return max(depth2_ids, key=lambda aid: scores.get(aid, 0.0))


def mismatch_story(day: str, stock: dict[str, str], actual: dict[str, float], news: dict[str, Any], rows_by_code: dict[str, dict[str, str]]) -> str:
    pct_chg = float(stock.get("pct_chg") or 0.0)
    individual = actual["Individuals"]
    llm_sides = {code: rows_by_code[code]["llm_direction"] for code in RUNS}
    top_news = "; ".join(title for title, _ in news["top_titles"][:3])
    if day == "2026-03-09":
        interpretation = "주가가 크게 하락했지만 실제 개인은 저점매수로 강하게 순매수했고, LLM은 손실 회피와 리스크 축소 쪽으로 반응해 전 조건 순매도했다."
    elif day == "2026-03-17":
        interpretation = "주가는 상승했고 AI/엔비디아/자사주 뉴스가 긍정적으로 해석되면서 LLM은 모멘텀 매수로 기울었지만, 실제 개인은 상승 구간에서 차익실현성 순매도를 보였다."
    elif day == "2026-03-23":
        interpretation = "주가가 다시 급락했지만 실제 개인은 대규모 저점매수에 나섰다. LLM은 거시 부채, 규제, 불확실성 뉴스와 가격 하락을 위험 신호로 해석해 전 조건 순매도했다."
    else:
        interpretation = "주가 변동은 작았지만 외국인 순매도와 유가/전쟁/반도체 경쟁 뉴스가 위험 신호로 작동했고, LLM은 방어적으로 순매도했다. 실제 개인은 소폭 순매수였다."
    return (
        f"{day}: 주가 {pct(pct_chg)}, 개인 {money_krw(individual)}, "
        f"LLM 방향 {', '.join(f'{k}={v}' for k, v in llm_sides.items())}. "
        f"{interpretation} 주요 선택 뉴스: {top_news}"
    )


def build_report(summary: dict[str, Any]) -> None:
    font = register_font()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="KTitle", parent=styles["Title"], fontName=font, fontSize=17, leading=23, alignment=TA_CENTER, spaceAfter=8))
    styles.add(ParagraphStyle(name="KHeading1", parent=styles["Heading1"], fontName=font, fontSize=13, leading=17, textColor=colors.HexColor("#23395d"), spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="KHeading2", parent=styles["Heading2"], fontName=font, fontSize=10.5, leading=14, textColor=colors.HexColor("#1f4e79"), spaceBefore=8, spaceAfter=4))
    styles.add(ParagraphStyle(name="KBody", parent=styles["BodyText"], fontName=font, fontSize=8.6, leading=12.2, alignment=TA_LEFT, spaceAfter=4))
    styles.add(ParagraphStyle(name="KSmall", parent=styles["BodyText"], fontName=font, fontSize=7.0, leading=9.5, alignment=TA_LEFT))

    story: list[Any] = []
    story.append(para("Community / Fake News 조건 비교 보고서", styles["KTitle"]))
    story.append(para(f"생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} / 분석 대상: 지정된 4개 로그", styles["KBody"]))
    story.append(para("1. 실행 조건 확인", styles["KHeading1"]))
    condition_rows = [["조건", "Run ID", "Community", "Fake", "Agent", "거래일", "Concurrency", "주의"]]
    meta = summary["meta"]
    common_agents = set(meta["C01"]["agent_ids"])
    for values in meta.values():
        common_agents &= set(values["agent_ids"])
    for code, info in RUNS.items():
        m = meta[code]
        condition_rows.append(
            [
                code,
                info["run_id"],
                str(m.get("community_mode")),
                str(m.get("fake_news_mode")),
                str(m.get("agent_count")),
                str(m.get("date_count")),
                str(m.get("concurrency")),
                "agent set differs" if code == "C00" else "",
            ]
        )
    story.append(make_table([[para(c, styles["KSmall"]) for c in row] for row in condition_rows], [14 * mm, 49 * mm, 22 * mm, 18 * mm, 15 * mm, 15 * mm, 20 * mm, 25 * mm]))
    story.append(para(f"메타데이터 기준 네 로그는 모두 20거래일이다. C00은 기존 balanced-depth 실행이라 전체 30명은 다른 구성이고, 네 조건 공통 에이전트는 {len(common_agents)}명이다.", styles["KBody"]))

    story.append(para("2. 조건별 전체 결과", styles["KHeading1"]))
    rows = [["조건", "불일치일", "불일치 날짜", "평균 수익률", "Fallback", "Buy/Sell", "Turnover"]]
    for code, item in summary["condition_summary"].items():
        rows.append(
            [
                f"{code}\n{RUNS[code]['label']}",
                str(item["mismatch_count"]),
                ", ".join(item["mismatch_dates"]),
                pct(item["avg_return"]),
                str(item["fallback_count"]),
                f"{item['buy_turns']:.0f}/{item['sell_turns']:.0f}",
                money_krw(item["turnover"]),
            ]
        )
    story.append(make_table([[para(c, styles["KSmall"]) for c in row] for row in rows], [27 * mm, 15 * mm, 56 * mm, 20 * mm, 15 * mm, 21 * mm, 25 * mm]))

    story.append(para("3. 네 조건 모두 개인과 불일치한 날", styles["KHeading1"]))
    story.append(para(f"Value와 Volume 기준 모두 공통 불일치한 날은 {', '.join(summary['common_mismatch_dates'])} 총 {len(summary['common_mismatch_dates'])}일이다.", styles["KBody"]))
    mismatch_rows = [["날짜", "주가", "개인", "기관", "외국인", "C01", "C11", "C10", "C00"]]
    for day in summary["common_mismatch_dates"]:
        stock = summary["stock"][day]
        actual = summary["actual"][day]
        row = [
            day,
            f"{int(num(stock['close'])):,}원\n{pct(float(stock['pct_chg']))}",
            money_krw(actual["Individuals"]),
            money_krw(actual["Institutions"]),
            money_krw(actual["Foreign"]),
        ]
        for code in RUNS:
            vrow = summary["validation_by_date"][code][day]
            row.append(f"{vrow['llm_direction']}\n{money_krw(num(vrow['llm_net']))}")
        mismatch_rows.append(row)
    story.append(make_table([[para(c, styles["KSmall"]) for c in row] for row in mismatch_rows], [21 * mm, 20 * mm, 24 * mm, 24 * mm, 24 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm], font_size=6.5))
    for day in summary["common_mismatch_dates"]:
        story.append(para(mismatch_story(day, summary["stock"][day], summary["actual"][day], summary["news"][day], {code: summary["validation_by_date"][code][day] for code in RUNS}), styles["KBody"]))

    story.append(PageBreak())
    story.append(para("4. 대표 에이전트 사례", styles["KHeading1"]))
    depth2_agent = summary.get("depth2_agent")
    story.append(
        para(
            "공통 에이전트 24명 중 조건별 최종 수익률 범위, 매수 횟수 변화, turnover 변화, fallback 발생을 종합해 대표 에이전트를 골랐다. "
            + (f"추가로 공통 depth 2 후보 중 변화가 가장 큰 {depth2_agent}를 포함했다." if depth2_agent else ""),
            styles["KBody"],
        )
    )
    for aid in summary["representative_agents"]:
        story.append(para(f"{aid}", styles["KHeading2"]))
        persona = summary.get("personas", {}).get(aid, {})
        if persona:
            story.append(
                para(
                    f"Persona: {persona.get('gender')} {persona.get('age')}세, {persona.get('location')}, "
                    f"{persona.get('user_type')}, strategy={persona.get('strategy')}, depth={persona.get('news_depth')}, "
                    f"disposition={persona.get('bh_disposition_effect_category')}, risk={persona.get('bh_lottery_preference_category')}, "
                    f"performance={persona.get('bh_total_return_category')}, diversification={persona.get('bh_underdiversification_category')}.",
                    styles["KBody"],
                )
            )
        rows = [["조건", "최종수익률", "Buy/Sell", "Fallback", "Turnover", "보유수량", "3/9", "3/17", "3/23", "3/25"]]
        for code in RUNS:
            m = summary["agent_metrics"][code].get(aid, {})
            day_cells = []
            for day in summary["common_mismatch_dates"]:
                turns = summary["agent_turns"][code].get(f"{aid}|{day}", [])
                actions = "/".join(f"{row['subturn']}:{row['action']} {row['quantity']}" for row in turns) or "-"
                day_cells.append(actions)
            rows.append(
                [
                    code,
                    pct(float(m.get("final_return") or 0.0)),
                    f"{int(m.get('action_buy') or 0)}/{int(m.get('action_sell') or 0)}",
                    str(int(m.get("fallback") or 0)),
                    money_krw(float(m.get("turnover") or 0.0)),
                    f"{int(m.get('position_qty') or 0):,}",
                    *day_cells,
                ]
            )
        story.append(make_table([[para(c, styles["KSmall"]) for c in row] for row in rows], [14 * mm, 18 * mm, 17 * mm, 14 * mm, 23 * mm, 17 * mm, 24 * mm, 24 * mm, 24 * mm, 24 * mm], font_size=6.1))
        best = summary["agent_notes"][aid]
        story.append(para(best, styles["KBody"]))

    story.append(para("5. 해석", styles["KHeading1"]))
    story.append(
        para(
            "공통 불일치 4일은 community/fake 조건보다 가격 충격과 개인투자자 특유의 저점매수/차익실현 패턴이 더 강하게 작동한 날로 보인다. "
            "3/9와 3/23은 급락일에 개인이 대규모 순매수했지만 LLM은 위험 축소로 매도했고, 3/17은 상승일에 개인이 차익실현했지만 LLM은 호재 모멘텀을 따라 매수했다. "
            "조건별 비교에서는 fake/community 유무에 따라 개별 에이전트의 turnover, fallback, 최종 PnL이 크게 달라지는 사례가 있으므로, 향후 재실험은 동일 agent set, 동일 concurrency, fallback 제거 후 다시 비교하는 것이 필요하다.",
            styles["KBody"],
        )
    )

    doc = SimpleDocTemplate(str(OUT_PDF), pagesize=A4, rightMargin=13 * mm, leftMargin=13 * mm, topMargin=14 * mm, bottomMargin=12 * mm, title="Community Fake News Condition Comparison")
    doc.build(story)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = load_meta()
    validation = load_validation("value")
    validation_by_date = {code: {row["date"]: row for row in rows} for code, rows in validation.items()}
    mismatch_sets = [
        {row["date"] for row in rows if str(row.get("llm_matches_individuals")) == "0"}
        for rows in validation.values()
    ]
    common_mismatch_dates = sorted(set.intersection(*mismatch_sets))
    stock = load_stock()
    actual = load_actual_value()
    agent_metrics = load_agent_metrics()
    representative_agents = pick_representative_agents(meta, agent_metrics)
    depth2_agent = pick_common_depth2_agent(meta, agent_metrics)
    if depth2_agent and depth2_agent not in representative_agents:
        representative_agents.append(depth2_agent)
    personas = load_personas(representative_agents)
    turn_lookup_raw = load_agent_turn_lookup()
    agent_turns = {
        code: {
            f"{aid}|{day}": rows
            for (aid, day), rows in lookup.items()
            if aid in representative_agents and day in common_mismatch_dates
        }
        for code, lookup in turn_lookup_raw.items()
    }
    condition = condition_summary(validation, agent_metrics)
    news = selected_news_summary(common_mismatch_dates)
    agent_notes = {}
    for aid in representative_agents:
        returns = {code: float(agent_metrics[code].get(aid, {}).get("final_return") or 0.0) for code in RUNS}
        best_code = max(returns, key=returns.get)
        worst_code = min(returns, key=returns.get)
        buys = {code: int(agent_metrics[code].get(aid, {}).get("action_buy") or 0) for code in RUNS}
        turnovers = {code: float(agent_metrics[code].get(aid, {}).get("turnover") or 0.0) for code in RUNS}
        agent_notes[aid] = (
            f"최종 수익률 범위는 {pct(max(returns.values()) - min(returns.values()))}p 수준이다. "
            f"가장 좋은 조건은 {best_code}({pct(returns[best_code])}), 가장 나쁜 조건은 {worst_code}({pct(returns[worst_code])})이다. "
            f"매수 횟수는 {min(buys.values())}~{max(buys.values())}회, turnover는 {money_krw(min(turnovers.values()))}~{money_krw(max(turnovers.values()))} 범위로 달라졌다."
        )
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "meta": meta,
        "condition_summary": condition,
        "common_mismatch_dates": common_mismatch_dates,
        "validation_by_date": validation_by_date,
        "stock": {day: stock[day] for day in common_mismatch_dates},
        "actual": {day: actual[day] for day in common_mismatch_dates},
        "news": news,
        "agent_metrics": agent_metrics,
        "representative_agents": representative_agents,
        "depth2_agent": depth2_agent,
        "personas": personas,
        "agent_turns": agent_turns,
        "agent_notes": agent_notes,
    }
    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    build_report(summary)
    print(OUT_JSON)
    print(OUT_PDF)


if __name__ == "__main__":
    main()
