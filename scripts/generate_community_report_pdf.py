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
    for row in selection_inputs:
        selection_by_date[row["date"]].append(row)
    thinking_by_date = defaultdict(list)
    for row in agent_turns:
        thinking = (row.get("context") or {}).get("community_thinking")
        if thinking:
            thinking_by_date[row["date"]].append((row["agent"]["agent_id"], thinking))

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
    ]
    story.append(table([[para(c, styles["KSmall"]) for c in row] for row in summary], [40 * mm, 130 * mm]))

    dates = sorted(set(posts_by_date) | set(interactions_by_date) | set(best_by_date) | set(selection_by_date) | set(thinking_by_date))
    for index, date in enumerate(dates, start=1):
        if index > 1:
            story.append(PageBreak())
        story.append(para(f"{date} 커뮤니티 화면", styles["KHeading1"]))

        story.append(para("게시글 목록", styles["KHeading2"]))
        post_rows = [["post_id", "작성자", "유형", "제목", "반응", "본문 요약"]]
        for row in posts_by_date.get(date, []):
            post_rows.append([
                row.get("post_id"),
                row.get("agent_id"),
                row.get("post_type"),
                row.get("title"),
                "",
                short(row.get("content"), 220),
            ])
        story.append(table([[para(c, styles["KSmall"]) for c in row] for row in post_rows], [14 * mm, 17 * mm, 20 * mm, 45 * mm, 17 * mm, 57 * mm]))

        story.append(para("Agent별 선택 전 화면", styles["KHeading2"]))
        selection_rows = [["Agent", "Depth", "읽기 한도", "후보 게시글"]]
        for row in sorted(selection_by_date.get(date, []), key=lambda r: r.get("agent_id", "")):
            candidates = []
            for post in row.get("visible_posts") or []:
                badges = ", ".join(post.get("author_badges") or []) or "뱃지 없음"
                candidates.append(f"#{post.get('post_id')} [{post.get('post_type')}] {post.get('title')} / {post.get('anonymous_code')} / {badges} / score {post.get('score')}")
            selection_rows.append([row.get("agent_id"), row.get("depth"), row.get("read_limit"), "\n".join(candidates)])
        story.append(table([[para(c, styles["KSmall"]) for c in row] for row in selection_rows], [18 * mm, 15 * mm, 18 * mm, 119 * mm]))

        story.append(para("읽기 및 반응", styles["KHeading2"]))
        read_rows = [["Agent", "선택", "읽은 글", "반응", "작성자 뱃지", "프로필 제공"]]
        for row in interactions_by_date.get(date, []):
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
            story.append(para("당일 Belief에 반영된 전날 Community Thinking", styles["KHeading2"]))
            thinking_rows = [["Agent", "Community Thinking"]]
            for agent_id, thinking in thinking_by_date[date]:
                thinking_rows.append([agent_id, short(thinking, 520)])
            story.append(table([[para(c, styles["KSmall"]) for c in row] for row in thinking_rows], [22 * mm, 148 * mm]))

    doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title="TwinMarket Community Report")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(output)


if __name__ == "__main__":
    main()
