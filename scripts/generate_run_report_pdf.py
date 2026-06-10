#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = PROJECT_ROOT / "outputs" / "logs" / "current"
REPORT_DIR = PROJECT_ROOT / "outputs" / "reports"
REPORT_PATH = REPORT_DIR / "current_report.pdf"
SYS_100_DB = PROJECT_ROOT / "outputs" / "sys_100.db"
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


def load_csv(name: str) -> list[dict[str, str]]:
    with (RUN_DIR / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_jsonl(name: str) -> list[dict[str, Any]]:
    rows = []
    with (RUN_DIR / name).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_json(name: str) -> dict[str, Any]:
    return json.loads((RUN_DIR / name).read_text(encoding="utf-8"))


def num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def money(value: Any) -> str:
    return f"{num(value):,.0f}원"


def pct(value: Any) -> str:
    return f"{num(value) * 100:.3f}%"


def short(text: Any, limit: int = 220) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def action_ko(action: str) -> str:
    return {"buy": "매수", "sell": "매도", "hold": "보유"}.get(action, action)


def para(text: Any, style: ParagraphStyle) -> Paragraph:
    safe = str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe.replace("\n", "<br/>"), style)


def table(data: list[list[Any]], widths: list[float] | None = None) -> Table:
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Korean"),
                ("FONTSIZE", (0, 0), (-1, 0), 8.5),
                ("FONTSIZE", (0, 1), (-1, -1), 7.5),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#23395d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b9c2d0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fb")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def load_initial_values(agent_ids: list[str]) -> dict[str, float]:
    if not SYS_100_DB.exists():
        return {agent_id: 100_000_000.0 for agent_id in agent_ids}
    with sqlite3.connect(SYS_100_DB) as conn:
        rows = conn.execute(
            "SELECT agent_id, ini_cash FROM agents WHERE agent_id IN (%s)"
            % ",".join("?" for _ in agent_ids),
            agent_ids,
        ).fetchall()
    values = {str(agent_id): float(ini_cash) for agent_id, ini_cash in rows}
    return {agent_id: values.get(agent_id, 100_000_000.0) for agent_id in agent_ids}


def latest_portfolios(
    updates: list[dict[str, Any]],
    final_close: float,
    initial_values: dict[str, float],
) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    for row in updates:
        state = row["state"]
        states[state["agent_id"]] = state
    for state in states.values():
        positions = state.get("positions") or []
        cash = num(state.get("cash"))
        stock_value = 0.0
        for pos in positions:
            qty = int(pos.get("quantity") or 0)
            pos["current_price"] = final_close
            pos["unrealized_pnl"] = (final_close - num(pos.get("avg_cost"))) * qty
            stock_value += final_close * qty
        state["total_value_marked_final"] = cash + stock_value
        initial_value = initial_values.get(state["agent_id"], 100_000_000.0)
        state["return_rate_marked_final"] = (
            (cash + stock_value - initial_value) / initial_value if initial_value else 0.0
        )
    return states


def page_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Korean", 8)
    canvas.setFillColor(colors.HexColor("#5f6b7a"))
    canvas.drawString(18 * mm, 10 * mm, "TwinMarket Korea 실행 결과 보고서")
    canvas.drawRightString(192 * mm, 10 * mm, f"{doc.page}")
    canvas.restoreState()


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    font = register_font()

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="KTitle",
            parent=styles["Title"],
            fontName=font,
            fontSize=19,
            leading=25,
            alignment=TA_CENTER,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="KHeading1",
            parent=styles["Heading1"],
            fontName=font,
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#23395d"),
            spaceBefore=12,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="KHeading2",
            parent=styles["Heading2"],
            fontName=font,
            fontSize=11.5,
            leading=15,
            textColor=colors.HexColor("#1f4e79"),
            spaceBefore=8,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="KBody",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=8.7,
            leading=12.2,
            alignment=TA_LEFT,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="KSmall",
            parent=styles["BodyText"],
            fontName=font,
            fontSize=7.2,
            leading=10.2,
            alignment=TA_LEFT,
        )
    )

    meta = load_json("run_metadata.json")
    complete = load_json("run_complete.json")
    agent_rows = load_csv("agent_turns.csv")
    daily_rows = load_csv("daily_exchange_summary.csv")
    order_rows = load_csv("submitted_orders.csv")
    fill_rows = load_csv("exchange_fills.csv")
    turn_rows = load_jsonl("agent_turns.jsonl")
    portfolio_updates = load_jsonl("portfolio_updates.jsonl")

    by_date = defaultdict(list)
    by_agent = defaultdict(list)
    for row in turn_rows:
        by_date[row["date"]].append(row)
        by_agent[row["agent"]["agent_id"]].append(row)
    for rows in by_date.values():
        rows.sort(key=lambda x: x["agent"]["agent_id"])
    for rows in by_agent.values():
        rows.sort(key=lambda x: x["turn"])

    fills_by_date = defaultdict(list)
    fills_by_agent = defaultdict(list)
    for row in fill_rows:
        fills_by_date[row["date"]].append(row)
        fills_by_agent[row["user_id"]].append(row)

    final_close = num(daily_rows[-1]["closing_price"])
    initial_values = load_initial_values(list(meta["agent_ids"]))
    final_states = latest_portfolios(portfolio_updates, final_close, initial_values)

    story: list[Any] = []
    story.append(para("TwinMarket Korea 시뮬레이션 실행 결과 보고서", styles["KTitle"]))
    story.append(
        para(
            f"실행 ID: {meta['run_id']} / 대상 종목: 삼성전자(005930) / 기간: "
            f"{daily_rows[0]['date']} ~ {daily_rows[-1]['date']} / "
            f"에이전트: {', '.join(meta['agent_ids'])}",
            styles["KBody"],
        )
    )

    action_counts = Counter(row["action"] for row in agent_rows)
    total_order_qty = sum(int(num(row["quantity"])) for row in order_rows)
    total_fill_qty = sum(int(num(row["executed_quantity"])) for row in fill_rows)
    total_fees = sum(num(row["fee"]) for row in fill_rows)
    story.append(para("1. 실행 개요", styles["KHeading1"]))
    overview = [
        ["항목", "내용"],
        ["실행 조건", f"랜덤 에이전트 {meta['agent_count']}명, 초반 {meta['date_count']}거래일, seed={meta['random_seed']}, concurrency={meta['concurrency']}"],
        ["선택 에이전트", ", ".join(meta["agent_ids"])],
        ["전체 판단", f"총 {len(agent_rows)}건: 매수 {action_counts.get('buy', 0)}건, 보유 {action_counts.get('hold', 0)}건, 매도 {action_counts.get('sell', 0)}건"],
        ["주문/체결", f"제출 주문 {len(order_rows)}건, 제출 수량 {total_order_qty:,}주, 체결 수량 {total_fill_qty:,}주, 수수료 합계 {total_fees:,.0f}원"],
        ["로그 위치", str(RUN_DIR)],
        ["완료 정보", f"{complete.get('run_id')} / {complete.get('date_count', meta['date_count'])}일 실행 완료"],
    ]
    story.append(table([[para(c, styles["KSmall"]) for c in row] for row in overview], [35 * mm, 135 * mm]))

    story.append(para("2. 일자별 전체 거래 현황", styles["KHeading1"]))
    daily_table = [["일자", "종가", "주문", "체결량", "체결건", "매수/보유", "해석"]]
    for row in daily_rows:
        date = row["date"]
        turns = by_date[date]
        counts = Counter(t["decision"]["action"] for t in turns)
        sentiments = Counter(t["news_interpretation"].get("news_sentiment", "") for t in turns)
        main_sentiment = sentiments.most_common(1)[0][0] if sentiments else ""
        note = (
            f"뉴스 감성은 {main_sentiment} 중심. "
            f"매수 {counts.get('buy', 0)}명, 보유 {counts.get('hold', 0)}명. "
        )
        if num(row["volume"]) == 0:
            note += "제출 주문은 있었지만 당일 체결은 발생하지 않음."
        elif counts.get("buy", 0) >= 4:
            note += "초기 저가/AI 모멘텀 인식이 매수로 강하게 연결됨."
        else:
            note += "보유 판단이 늘며 매수 강도는 둔화됨."
        daily_table.append(
            [
                date,
                money(row["closing_price"]),
                row["submitted_orders"],
                f"{int(num(row['volume'])):,}주",
                row["fill_count"],
                f"매수 {counts.get('buy', 0)} / 보유 {counts.get('hold', 0)}",
                note,
            ]
        )
    story.append(table([[para(c, styles["KSmall"]) for c in row] for row in daily_table], [22 * mm, 23 * mm, 15 * mm, 20 * mm, 15 * mm, 26 * mm, 49 * mm]))

    story.append(para("3. 일자별 상세 분석", styles["KHeading1"]))
    for day in daily_rows:
        date = day["date"]
        rows = by_date[date]
        fills = fills_by_date.get(date, [])
        story.append(para(f"{date} / Turn {day['turn']}", styles["KHeading2"]))
        fill_text = "체결 없음"
        if fills:
            fill_text = ", ".join(
                f"{f['user_id']} {action_ko(f['direction'])} {int(num(f['executed_quantity'])):,}주@{money(f['executed_price'])}"
                for f in fills
            )
        market = rows[0]["context"]["market_features"]
        story.append(
            para(
                f"시장 지표: 종가 {money(day['closing_price'])}, 등락률 {pct(market.get('pct_chg'))}, "
                f"MA5 {money(market.get('ma5'))}, MA20 {money(market.get('ma20'))}. "
                f"당일 주문 {day['submitted_orders']}건, 체결량 {int(num(day['volume'])):,}주, 체결 내역: {fill_text}",
                styles["KBody"],
            )
        )
        news_titles = []
        for turn in rows:
            for item in turn["context"]["news_context"].get("read_contents", []):
                if item.get("title") not in news_titles:
                    news_titles.append(item.get("title"))
        story.append(para("주요 확인 뉴스: " + " / ".join(short(t, 70) for t in news_titles[:6]), styles["KBody"]))

        detail_data = [["에이전트", "생각 변화", "시장/뉴스 해석", "판단 및 이유", "리스크 관리"]]
        for turn in rows:
            decision = turn["decision"]
            belief = turn["belief"]
            analysis = turn["market_analysis"]
            interp = turn["news_interpretation"]
            decision_text = (
                f"{action_ko(decision['action'])} {int(num(decision.get('quantity'))):,}주"
                if decision["action"] != "hold"
                else "보유"
            )
            if decision["action"] != "hold":
                decision_text += f" / {decision.get('order_type')} / {money(decision.get('price'))}"
            decision_text += f": {short(decision.get('reason'), 260)}"
            detail_data.append(
                [
                    f"{turn['agent']['agent_id']}\n{turn['agent']['strategy']} / {turn['agent']['age']}세",
                    short(belief.get("belief_summary"), 260) + "\n변화: " + short(belief.get("view_change"), 180),
                    f"뉴스 감성: {interp.get('news_sentiment')} / {short(interp.get('persona_interpretation'), 210)}\n"
                    f"시장: {short(analysis.get('market_view'), 170)}",
                    decision_text,
                    short(decision.get("risk_control"), 220),
                ]
            )
        story.append(table([[para(c, styles["KSmall"]) for c in row] for row in detail_data], [20 * mm, 40 * mm, 43 * mm, 43 * mm, 24 * mm]))

    story.append(PageBreak())
    story.append(para("4. 에이전트별 5일 사고 흐름 및 최종 상태", styles["KHeading1"]))
    for agent_id in meta["agent_ids"]:
        rows = by_agent[agent_id]
        profile = rows[0]["agent"]
        state = final_states.get(agent_id, {})
        positions = state.get("positions") or []
        pos_text = "보유 종목 없음"
        if positions:
            pos = positions[0]
            pos_text = f"{pos['stock_code']} {int(pos.get('quantity') or 0):,}주, 평균단가 {money(pos.get('avg_cost'))}, 최종 평가가 {money(final_close)}"
        story.append(
            KeepTogether(
                [
                    para(
                        f"{agent_id} ({profile['gender']}, {profile['age']}세, 전략={profile['strategy']}, 거래빈도={profile['trade_count_category']})",
                        styles["KHeading2"],
                    ),
                    para(
                        f"최종 상태: 현금 {money(state.get('cash'))}, {pos_text}, "
                        f"최종 평가 총자산 {money(state.get('total_value_marked_final'))}, "
                        f"최종 평가 수익률 {pct(state.get('return_rate_marked_final'))}.",
                        styles["KBody"],
                    ),
                ]
            )
        )
        flow = [["일자", "관점/생각", "판단", "결과"]]
        agent_fills = {(f["date"], int(num(f["executed_quantity"])), f["direction"]) for f in fills_by_agent.get(agent_id, [])}
        for turn in rows:
            decision = turn["decision"]
            action = action_ko(decision["action"])
            qty = int(num(decision.get("quantity")))
            result = "미체결/주문 없음"
            matched = [f for f in fills_by_agent.get(agent_id, []) if f["date"] == turn["date"]]
            if matched:
                result = "; ".join(f"{action_ko(f['direction'])} {int(num(f['executed_quantity'])):,}주 체결@{money(f['executed_price'])}" for f in matched)
            elif decision["action"] == "hold":
                result = "보유 유지"
            flow.append(
                [
                    turn["date"],
                    short(turn["belief"].get("belief_summary"), 240),
                    f"{action} {qty:,}주. {short(decision.get('reason'), 220)}",
                    result,
                ]
            )
        story.append(table([[para(c, styles["KSmall"]) for c in row] for row in flow], [22 * mm, 55 * mm, 62 * mm, 31 * mm]))

    story.append(PageBreak())
    story.append(para("5. 최종 포트폴리오 및 해석", styles["KHeading1"]))
    final_table = [["에이전트", "최종 보유", "현금", "평가 총자산", "평가 수익률", "요약 해석"]]
    for agent_id in meta["agent_ids"]:
        state = final_states.get(agent_id, {})
        positions = state.get("positions") or []
        pos_text = "-"
        if positions:
            pos = positions[0]
            pos_text = f"{int(pos.get('quantity') or 0):,}주 / 평균 {money(pos.get('avg_cost'))}"
        rows = by_agent[agent_id]
        buys = sum(1 for r in rows if r["decision"]["action"] == "buy")
        holds = sum(1 for r in rows if r["decision"]["action"] == "hold")
        final_table.append(
            [
                agent_id,
                pos_text,
                money(state.get("cash")),
                money(state.get("total_value_marked_final")),
                pct(state.get("return_rate_marked_final")),
                f"5일 중 매수 판단 {buys}회, 보유 판단 {holds}회. "
                f"{short(rows[-1]['belief'].get('belief_summary'), 130)}",
            ]
        )
    story.append(table([[para(c, styles["KSmall"]) for c in row] for row in final_table], [18 * mm, 32 * mm, 28 * mm, 30 * mm, 20 * mm, 42 * mm]))

    story.append(para("6. 종합 결론", styles["KHeading1"]))
    story.append(
        para(
            "이번 5거래일 실행에서는 모든 에이전트가 초반 AI·CES·반도체 기술 리더십 뉴스를 긍정적으로 해석하면서도, "
            "실적 발표 전 목표가 하향과 업황 불확실성을 단기 리스크로 함께 반영했다. 결과적으로 1~3일차에는 매수 판단이 "
            "우세했고, 4~5일차에는 이미 구축한 포지션과 가격 상승 부담 때문에 보유 판단이 늘었다. 특히 A011은 첫날부터 "
            "가용 현금을 거의 전부 사용한 대규모 매수를 실행해 다른 에이전트와 뚜렷하게 구분되며, 나머지 에이전트들은 "
            "100주 단위의 분할 매수와 현금 보존을 병행했다. 마지막 날에는 제출 주문이 있었지만 체결량이 0으로 기록되어, "
            "의사결정과 실제 시장 체결 사이의 차이가 드러났다.",
            styles["KBody"],
        )
    )

    doc = SimpleDocTemplate(
        str(REPORT_PATH),
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="TwinMarket Korea 시뮬레이션 실행 결과 보고서",
    )
    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
