#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
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
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from report_common import pick_representative_agents


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_DIR = PROJECT_ROOT / "outputs" / "logs" / "current"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "reports" / "current_community_report.pdf"
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
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def short(text: Any, limit: int = 180) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


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
                ("FONTSIZE", (0, 1), (-1, -1), 7.2),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f4050")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c4ccd8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def latest_states(updates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    for row in updates:
        state = row.get("state") or {}
        agent_id = str(state.get("agent_id") or "")
        if agent_id:
            states[agent_id] = state
    return states


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Korean", 8)
    canvas.setFillColor(colors.HexColor("#5f6b7a"))
    canvas.drawString(18 * mm, 10 * mm, "TwinMarket Korea Community Report")
    canvas.drawRightString(192 * mm, 10 * mm, f"{doc.page}")
    canvas.restoreState()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--representative-agents", type=int, default=4)
    args = parser.parse_args()

    run_dir = args.run_dir
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)

    font = register_font()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="KTitle", parent=styles["Title"], fontName=font, fontSize=18, leading=24, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="KHeading1", parent=styles["Heading1"], fontName=font, fontSize=14, leading=18, textColor=colors.HexColor("#23395d"), spaceBefore=12, spaceAfter=8))
    styles.add(ParagraphStyle(name="KHeading2", parent=styles["Heading2"], fontName=font, fontSize=11.5, leading=15, textColor=colors.HexColor("#1f4e79"), spaceBefore=8, spaceAfter=5))
    styles.add(ParagraphStyle(name="KBody", parent=styles["BodyText"], fontName=font, fontSize=8.6, leading=12, alignment=TA_LEFT, spaceAfter=5))
    styles.add(ParagraphStyle(name="KSmall", parent=styles["BodyText"], fontName=font, fontSize=7.1, leading=9.8, alignment=TA_LEFT))

    meta = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    posts = read_csv(run_dir / "community_posts.csv")
    interactions = read_csv(run_dir / "community_interactions.csv")
    best_posts = read_csv(run_dir / "community_best_posts.csv")
    logs = read_csv(run_dir / "community_logs.csv")
    selection_inputs = read_jsonl(run_dir / "community_selection_inputs.jsonl")
    agent_turns = read_jsonl(run_dir / "agent_turns.jsonl")
    portfolio_updates = read_jsonl(run_dir / "portfolio_updates.jsonl")
    order_rows = read_csv(run_dir / "submitted_orders.csv")
    fill_rows = read_csv(run_dir / "exchange_fills.csv")

    posts_by_date = defaultdict(list)
    for row in posts:
        posts_by_date[row["date"]].append(row)
    interactions_by_date = defaultdict(list)
    for row in interactions:
        interactions_by_date[row["date"]].append(row)
    best_by_date = defaultdict(list)
    for row in best_posts:
        best_by_date[row["date"]].append(row)
    selection_by_date = defaultdict(list)
    post_meta: dict[str, dict[str, Any]] = {}
    for row in selection_inputs:
        selection_by_date[row["date"]].append(row)
        for post in row.get("visible_posts") or []:
            post_id = str(post.get("post_id") or "")
            if post_id and post_id not in post_meta:
                post_meta[post_id] = post
    thinking_by_date = defaultdict(list)
    for row in agent_turns:
        thinking = (row.get("context") or {}).get("community_thinking")
        if thinking:
            thinking_by_date[row["date"]].append((row["agent"]["agent_id"], thinking))

    reaction_counts_by_post = defaultdict(Counter)
    for row in interactions:
        if row.get("post_id"):
            reaction_counts_by_post[str(row["post_id"])][row.get("reaction") or "read"] += 1

    final_states = latest_states(portfolio_updates)
    representative_agents, representative_reasons = pick_representative_agents(
        list(meta.get("agent_ids") or []),
        final_states=final_states,
        order_rows=order_rows,
        fill_rows=fill_rows,
        community_posts=posts,
        community_interactions=interactions,
        limit=args.representative_agents,
    )
    representative_agent_set = set(representative_agents)

    story: list[Any] = []
    story.append(para("TwinMarket Korea 커뮤니티 종토방 보고서", styles["KTitle"]))
    story.append(para(f"실행 ID: {meta['run_id']} / 기간 {meta.get('start_date')}부터 {meta.get('date_count')}거래일 / Agent {meta.get('agent_count')}명", styles["KBody"]))

    reactions = Counter(row.get("reaction") for row in interactions if row.get("reaction"))
    summary = [
        ["항목", "값"],
        ["게시글", f"{len(posts)}건"],
        ["선택 후보 화면", f"{len(selection_inputs)}건"],
        ["읽기/반응", f"{len(interactions)}건 ({', '.join(f'{k}: {v}' for k, v in sorted(reactions.items()))})"],
        ["Best 선정", f"{len(best_posts)}건"],
        ["Community Thinking", f"{sum(len(v) for v in thinking_by_date.values())}건"],
        ["대표 에이전트", ", ".join(f"{agent_id} ({representative_reasons.get(agent_id, '')})" for agent_id in representative_agents)],
    ]
    story.append(table([[para(c, styles["KSmall"]) for c in row] for row in summary], [40 * mm, 130 * mm]))

    dates = sorted(set(posts_by_date) | set(interactions_by_date) | set(best_by_date) | set(selection_by_date) | set(thinking_by_date))
    for index, date in enumerate(dates, start=1):
        if index > 1:
            story.append(PageBreak())
        story.append(para(f"{date} 커뮤니티 화면", styles["KHeading1"]))

        story.append(para("게시글 목록", styles["KHeading2"]))
        post_rows = [["post_id", "이름/작성자", "뱃지", "유형", "제목", "반응", "본문 요약"]]
        for row in posts_by_date.get(date, []):
            meta_for_post = post_meta.get(str(row.get("post_id"))) or {}
            badges = ", ".join(meta_for_post.get("author_badges") or []) or "뱃지 없음"
            reactions_for_post = reaction_counts_by_post.get(str(row.get("post_id"))) or Counter()
            reaction_text = ", ".join(f"{key} {value}" for key, value in sorted(reactions_for_post.items())) or "-"
            post_rows.append([
                row.get("post_id"),
                f"{meta_for_post.get('anonymous_code') or '-'}\n{row.get('agent_id')}",
                badges,
                row.get("post_type"),
                row.get("title"),
                reaction_text,
                short(row.get("content"), 220),
            ])
        story.append(table([[para(c, styles["KSmall"]) for c in row] for row in post_rows], [13 * mm, 23 * mm, 27 * mm, 18 * mm, 38 * mm, 20 * mm, 41 * mm]))

        story.append(para("대표 에이전트 선택 전 화면", styles["KHeading2"]))
        selection_rows = [["Agent", "선정 기준", "Depth", "후보 게시글"]]
        for row in sorted(selection_by_date.get(date, []), key=lambda r: r.get("agent_id", "")):
            if row.get("agent_id") not in representative_agent_set:
                continue
            candidates = []
            for post in row.get("visible_posts") or []:
                badges = ", ".join(post.get("author_badges") or []) or "뱃지 없음"
                candidates.append(f"#{post.get('post_id')} [{post.get('post_type')}] {post.get('title')} / {post.get('anonymous_code')} / {badges} / score {post.get('score')}")
            selection_rows.append([row.get("agent_id"), representative_reasons.get(row.get("agent_id"), ""), row.get("depth"), "\n".join(candidates)])
        story.append(table([[para(c, styles["KSmall"]) for c in row] for row in selection_rows], [18 * mm, 32 * mm, 14 * mm, 106 * mm]))

        story.append(para("대표 에이전트 읽기 및 반응", styles["KHeading2"]))
        read_rows = [["Agent", "선택", "읽은 글", "반응", "작성자 뱃지", "프로필 제공"]]
        for row in interactions_by_date.get(date, []):
            if row.get("agent_id") not in representative_agent_set:
                continue
            read_rows.append([
                row.get("agent_id"),
                row.get("selected_post_ids"),
                f"#{row.get('post_id')} {row.get('title')}",
                row.get("reaction"),
                row.get("author_badges"),
                "Y" if row.get("author_profile") not in {"", "null", None} else "N",
            ])
        story.append(table([[para(c, styles["KSmall"]) for c in row] for row in read_rows], [18 * mm, 22 * mm, 55 * mm, 18 * mm, 37 * mm, 20 * mm]))

        story.append(para("Best 게시글", styles["KHeading2"]))
        best_rows = [["순위", "post_id", "제목", "유형", "score"]]
        for row in best_by_date.get(date, []):
            best_rows.append([row.get("rank"), row.get("post_id"), row.get("title"), row.get("post_type"), row.get("score")])
        story.append(table([[para(c, styles["KSmall"]) for c in row] for row in best_rows], [14 * mm, 18 * mm, 95 * mm, 25 * mm, 18 * mm]))

        if thinking_by_date.get(date):
            story.append(para("대표 에이전트 Community Thinking", styles["KHeading2"]))
            thinking_rows = [["Agent", "Community Thinking"]]
            for agent_id, thinking in thinking_by_date[date]:
                if agent_id not in representative_agent_set:
                    continue
                thinking_rows.append([agent_id, short(thinking, 520)])
            if len(thinking_rows) > 1:
                story.append(table([[para(c, styles["KSmall"]) for c in row] for row in thinking_rows], [22 * mm, 148 * mm]))

    doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title="TwinMarket Community Report")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(output)


if __name__ == "__main__":
    main()
