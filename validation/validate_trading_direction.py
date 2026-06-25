#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import defaultdict
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
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATION_DIR = PROJECT_ROOT / "validation"
DEFAULT_RUN_DIR = PROJECT_ROOT / "outputs" / "logs" / "current"
COUNTERSIDE_USER_ID = "COUNTERSIDE"
ACTUAL_INVESTOR_COLUMNS = [
    "Individuals",
    "Subtotal-Institutions",
    "Total of foreign",
    "Other corporations",
]
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare simulated LLM net buy/sell direction with Samsung Electronics investor net trading data."
    )
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR, help="Simulation log directory.")
    parser.add_argument("--actual-value", type=Path, default=VALIDATION_DIR / "data_trading_value.csv")
    parser.add_argument("--actual-volume", type=Path, default=VALIDATION_DIR / "data_trading_volume.csv")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--stock-code", default="005930")
    parser.add_argument(
        "--skip-initial-days",
        type=int,
        default=3,
        help="Exclude the first N overlapping trading days from validation metrics and charts.",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_date(value: str) -> str:
    value = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(f"unsupported date format: {value!r}")


def num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def sign(value: float, eps: float = 1e-9) -> int:
    if value > eps:
        return 1
    if value < -eps:
        return -1
    return 0


def direction_label(value: float) -> str:
    side = sign(value)
    if side > 0:
        return "net_buy"
    if side < 0:
        return "net_sell"
    return "flat"


def direction_label_ko(value: float) -> str:
    side = sign(value)
    if side > 0:
        return "순매수"
    if side < 0:
        return "순매도"
    return "중립"


def fmt_int(value: Any) -> str:
    return f"{num(value):,.0f}"


def pct(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "N/A"
    return f"{value * 100:.1f}%"


def score_text(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "N/A"
    return f"{value:.3f}"


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    dx = [x - mean_x for x in xs]
    dy = [y - mean_y for y in ys]
    denom = math.sqrt(sum(x * x for x in dx) * sum(y * y for y in dy))
    if denom == 0:
        return None
    return sum(x * y for x, y in zip(dx, dy)) / denom


def cosine(xs: list[float], ys: list[float]) -> float | None:
    if not xs or len(xs) != len(ys):
        return None
    denom = math.sqrt(sum(x * x for x in xs) * sum(y * y for y in ys))
    if denom == 0:
        return None
    return sum(x * y for x, y in zip(xs, ys)) / denom


def max_abs_normalize(values: list[float]) -> list[float]:
    scale = max([abs(value) for value in values] or [0.0])
    if scale == 0:
        return [0.0 for _ in values]
    return [value / scale for value in values]


def z_score_normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    std = math.sqrt(variance)
    if std == 0:
        return [0.0 for _ in values]
    return [(value - mean) / std for value in values]


def cumulative(values: list[float]) -> list[float]:
    total = 0.0
    result = []
    for value in values:
        total += value
        result.append(total)
    return result


def direction_match_rate(xs: list[float], ys: list[float], *, ignore_zero: bool = False) -> float | None:
    pairs = []
    for x, y in zip(xs, ys):
        sx, sy = sign(x), sign(y)
        if ignore_zero and (sx == 0 or sy == 0):
            continue
        pairs.append((sx, sy))
    if not pairs:
        return None
    return sum(1 for sx, sy in pairs if sx == sy) / len(pairs)


def load_actual(path: Path) -> dict[str, dict[str, float]]:
    rows = read_csv(path)
    actual: dict[str, dict[str, float]] = {}
    for row in rows:
        date = parse_date(row["Date"])
        actual[date] = {column: num(row.get(column)) for column in ACTUAL_INVESTOR_COLUMNS}
    return actual


def load_simulation(run_dir: Path, stock_code: str) -> tuple[str, dict[str, dict[str, float]]]:
    run_dir = run_dir.resolve()
    fills_path = run_dir / "exchange_fills.csv"
    daily_path = run_dir / "daily_exchange_summary.csv"
    metadata_path = run_dir / "run_metadata.json"
    fills = read_csv(fills_path)
    run_id = run_dir.name
    if metadata_path.exists():
        with metadata_path.open(encoding="utf-8") as f:
            run_id = json.load(f).get("run_id") or run_id

    daily: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "llm_volume": 0.0,
            "llm_value": 0.0,
            "counterside_volume": 0.0,
            "counterside_value": 0.0,
            "llm_buy_volume": 0.0,
            "llm_sell_volume": 0.0,
            "counterside_buy_volume": 0.0,
            "counterside_sell_volume": 0.0,
        }
    )
    if daily_path.exists():
        for row in read_csv(daily_path):
            if str(row.get("stock_code") or stock_code) == stock_code:
                daily[parse_date(row["date"])]
    for row in fills:
        if str(row.get("stock_code") or stock_code) != stock_code:
            continue
        date = parse_date(row["date"])
        qty = num(row.get("executed_quantity"))
        price = num(row.get("executed_price"))
        signed_qty = qty if row.get("direction") == "buy" else -qty
        signed_value = signed_qty * price
        prefix = "counterside" if row.get("user_id") == COUNTERSIDE_USER_ID else "llm"
        daily[date][f"{prefix}_volume"] += signed_qty
        daily[date][f"{prefix}_value"] += signed_value
        if signed_qty > 0:
            daily[date][f"{prefix}_buy_volume"] += qty
        elif signed_qty < 0:
            daily[date][f"{prefix}_sell_volume"] += qty
    return run_id, dict(daily)


def metric_bundle(sim_values: list[float], actual_values: list[float]) -> dict[str, Any]:
    sim_max_abs = max_abs_normalize(sim_values)
    actual_max_abs = max_abs_normalize(actual_values)
    sim_z = z_score_normalize(sim_values)
    actual_z = z_score_normalize(actual_values)
    sim_cumulative = max_abs_normalize(cumulative(sim_values))
    actual_cumulative = max_abs_normalize(cumulative(actual_values))
    return {
        "days": len(sim_values),
        "direction_match_rate": direction_match_rate(sim_values, actual_values),
        "nonzero_direction_match_rate": direction_match_rate(sim_values, actual_values, ignore_zero=True),
        "pearson_correlation": pearson(sim_values, actual_values),
        "cosine_similarity": cosine(sim_values, actual_values),
        "max_abs_normalized": {
            "pearson_correlation": pearson(sim_max_abs, actual_max_abs),
            "cosine_similarity": cosine(sim_max_abs, actual_max_abs),
        },
        "z_score_normalized": {
            "pearson_correlation": pearson(sim_z, actual_z),
            "cosine_similarity": cosine(sim_z, actual_z),
        },
        "cumulative_max_abs_normalized": {
            "pearson_correlation": pearson(sim_cumulative, actual_cumulative),
            "cosine_similarity": cosine(sim_cumulative, actual_cumulative),
        },
    }


def build_comparison_rows(
    *,
    label: str,
    actual: dict[str, dict[str, float]],
    simulation: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sim_key = "llm_value" if label == "value" else "llm_volume"
    counter_key = "counterside_value" if label == "value" else "counterside_volume"
    for date in sorted(set(actual) & set(simulation)):
        sim = simulation[date]
        actual_row = actual[date]
        row: dict[str, Any] = {
            "date": date,
            "llm_net": sim[sim_key],
            "llm_direction": direction_label(sim[sim_key]),
            "counterside_net": sim[counter_key],
            "counterside_direction": direction_label(sim[counter_key]),
        }
        for column in ACTUAL_INVESTOR_COLUMNS:
            row[column] = actual_row[column]
            row[f"{column}_direction"] = direction_label(actual_row[column])
        row["llm_matches_individuals"] = int(sign(sim[sim_key]) == sign(actual_row["Individuals"]))
        rows.append(row)
    return rows


def skip_initial_rows(rows: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    if days <= 0:
        return rows
    return rows[days:]


def summarize_dimension(rows: list[dict[str, Any]], metric_key: str) -> dict[str, Any]:
    llm_values = [num(row["llm_net"]) for row in rows]
    counterside_values = [num(row["counterside_net"]) for row in rows]
    summary: dict[str, Any] = {
        "metric": metric_key,
        "overlap_days": len(rows),
        "llm_vs_individuals": metric_bundle(llm_values, [num(row["Individuals"]) for row in rows]),
        "counterside_vs_investor_groups": {},
    }
    for column in ACTUAL_INVESTOR_COLUMNS:
        summary["counterside_vs_investor_groups"][column] = metric_bundle(
            counterside_values, [num(row[column]) for row in rows]
        )
    return summary


def build_normalized_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    series_names = ["llm_net", "counterside_net", *ACTUAL_INVESTOR_COLUMNS]
    raw_series = {name: [num(row[name]) for row in rows] for name in series_names}
    max_abs_series = {name: max_abs_normalize(values) for name, values in raw_series.items()}
    z_score_series = {name: z_score_normalize(values) for name, values in raw_series.items()}
    cumulative_series = {name: max_abs_normalize(cumulative(values)) for name, values in raw_series.items()}

    normalized_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        normalized: dict[str, Any] = {
            "date": row["date"],
            "llm_direction": row["llm_direction"],
            "counterside_direction": row["counterside_direction"],
            "llm_matches_individuals": row["llm_matches_individuals"],
        }
        for name in series_names:
            normalized[f"{name}_raw"] = raw_series[name][index]
            normalized[f"{name}_max_abs"] = max_abs_series[name][index]
            normalized[f"{name}_z_score"] = z_score_series[name][index]
            normalized[f"{name}_cumulative_max_abs"] = cumulative_series[name][index]
        normalized_rows.append(normalized)
    return normalized_rows


def normalized_fieldnames() -> list[str]:
    series_names = ["llm_net", "counterside_net", *ACTUAL_INVESTOR_COLUMNS]
    fields = ["date", "llm_direction", "counterside_direction", "llm_matches_individuals"]
    for name in series_names:
        fields.extend(
            [
                f"{name}_raw",
                f"{name}_max_abs",
                f"{name}_z_score",
                f"{name}_cumulative_max_abs",
            ]
        )
    return fields


class NormalizedLineChart(Flowable):
    def __init__(self, title: str, dates: list[str], series: list[tuple[str, list[float], colors.Color]], width: float):
        super().__init__()
        self.title = title
        self.dates = dates
        self.series = series
        self.width = width
        self.height = 52 * mm

    def draw(self) -> None:
        c = self.canv
        x0, y0 = 8 * mm, 8 * mm
        w, h = self.width - 16 * mm, self.height - 18 * mm
        c.setFont("Korean", 8)
        c.setFillColor(colors.HexColor("#1f2937"))
        c.drawString(x0, y0 + h + 7 * mm, self.title)
        c.setStrokeColor(colors.HexColor("#cbd5e1"))
        c.line(x0, y0 + h / 2, x0 + w, y0 + h / 2)
        c.rect(x0, y0, w, h, stroke=1, fill=0)
        if len(self.dates) < 2:
            c.drawString(x0, y0 + h / 2 + 3 * mm, "비교 가능한 날짜가 부족합니다.")
            return
        all_values = [abs(value) for _, values, _ in self.series for value in values]
        max_abs = max(all_values or [1.0]) or 1.0
        for name, values, color in self.series:
            points = []
            for idx, value in enumerate(values):
                x = x0 + (w * idx / max(1, len(values) - 1))
                y = y0 + h / 2 + (value / max_abs) * (h * 0.42)
                points.append((x, y))
            c.setStrokeColor(color)
            c.setLineWidth(1.2)
            for (x1, y1), (x2, y2) in zip(points, points[1:]):
                c.line(x1, y1, x2, y2)
            c.setFillColor(color)
            c.circle(points[-1][0], points[-1][1], 1.4, stroke=0, fill=1)
        legend_x = x0
        for name, _, color in self.series:
            c.setFillColor(color)
            c.rect(legend_x, y0 - 4 * mm, 3 * mm, 3 * mm, stroke=0, fill=1)
            c.setFillColor(colors.HexColor("#475569"))
            c.drawString(legend_x + 4 * mm, y0 - 3.6 * mm, name)
            legend_x += 35 * mm
        c.setFillColor(colors.HexColor("#64748b"))
        c.drawString(x0, y0 - 9 * mm, self.dates[0])
        c.drawRightString(x0 + w, y0 - 9 * mm, self.dates[-1])


def para(text: Any, style: ParagraphStyle) -> Paragraph:
    safe = str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe.replace("\n", "<br/>"), style)


def table(data: list[list[Any]], widths: list[float] | None = None) -> Table:
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Korean"),
                ("FONTSIZE", (0, 0), (-1, 0), 8.2),
                ("FONTSIZE", (0, 1), (-1, -1), 7.2),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#23395d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def metric_table(title: str, summary: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    rows = [["비교", "일수", "방향", "MaxAbs r", "MaxAbs cos", "Z r", "누적 r", "누적 cos"]]
    primary = summary["llm_vs_individuals"]
    rows.append(
        [
            "LLM vs 개인",
            primary["days"],
            pct(primary["direction_match_rate"]),
            score_text(primary["max_abs_normalized"]["pearson_correlation"]),
            score_text(primary["max_abs_normalized"]["cosine_similarity"]),
            score_text(primary["z_score_normalized"]["pearson_correlation"]),
            score_text(primary["cumulative_max_abs_normalized"]["pearson_correlation"]),
            score_text(primary["cumulative_max_abs_normalized"]["cosine_similarity"]),
        ]
    )
    for investor, metric in summary["counterside_vs_investor_groups"].items():
        rows.append(
            [
                f"COUNTERSIDE vs {investor}",
                metric["days"],
                pct(metric["direction_match_rate"]),
                score_text(metric["max_abs_normalized"]["pearson_correlation"]),
                score_text(metric["max_abs_normalized"]["cosine_similarity"]),
                score_text(metric["z_score_normalized"]["pearson_correlation"]),
                score_text(metric["cumulative_max_abs_normalized"]["pearson_correlation"]),
                score_text(metric["cumulative_max_abs_normalized"]["cosine_similarity"]),
            ]
        )
    return [
        para(title, styles["KHeading2"]),
        table(
            [[para(c, styles["KSmall"]) for c in row] for row in rows],
            [39 * mm, 13 * mm, 18 * mm, 20 * mm, 20 * mm, 18 * mm, 18 * mm, 20 * mm],
        ),
    ]


def page_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Korean", 8)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(18 * mm, 10 * mm, "TwinMarket Korea 거래 방향 검증 보고서")
    canvas.drawRightString(192 * mm, 10 * mm, f"{doc.page}")
    canvas.restoreState()


def build_report(
    *,
    report_path: Path,
    run_id: str,
    run_dir: Path,
    value_rows: list[dict[str, Any]],
    volume_rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    font = register_font()
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="KTitle",
            parent=styles["Title"],
            fontName=font,
            fontSize=18,
            leading=24,
            alignment=TA_CENTER,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="KHeading1",
            parent=styles["Heading1"],
            fontName=font,
            fontSize=13.5,
            leading=18,
            textColor=colors.HexColor("#23395d"),
            spaceBefore=12,
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            name="KHeading2",
            parent=styles["Heading2"],
            fontName=font,
            fontSize=10.8,
            leading=14,
            textColor=colors.HexColor("#1f4e79"),
            spaceBefore=7,
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
            leading=10,
            alignment=TA_LEFT,
        )
    )

    story: list[Any] = []
    story.append(para("TwinMarket Korea 거래 방향 검증 보고서", styles["KTitle"]))
    story.append(
        para(
            f"실행 ID: {run_id} / 로그 위치: {run_dir} / 생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            styles["KBody"],
        )
    )
    skipped_days = int(summary.get("skip_initial_days") or 0)
    if skipped_days:
        story.append(
            para(
                f"검증 기준: COUNTERSIDE가 개입하지 않는 초기 warmup {skipped_days}거래일을 제외하고 비교했다.",
                styles["KBody"],
            )
        )
    overlap_days = summary["value"]["overlap_days"]
    if overlap_days == 0:
        story.append(para("1. 검증 결과", styles["KHeading1"]))
        story.append(
            para(
                "시뮬레이션 로그 날짜와 실제 삼성전자 투자자별 순거래 CSV 날짜가 겹치지 않습니다. "
                "동일 기간으로 시뮬레이션을 다시 실행한 뒤 이 스크립트를 재실행해야 방향 일치율을 계산할 수 있습니다.",
                styles["KBody"],
            )
        )
    else:
        story.append(para("1. 핵심 검증 결과", styles["KHeading1"]))
        v_primary = summary["value"]["llm_vs_individuals"]
        q_primary = summary["volume"]["llm_vs_individuals"]
        story.append(
            para(
                "기본 검증은 LLM 에이전트 전체의 일별 순매수/순매도 방향과 실제 개인 투자자(Individuals)의 "
                "일별 순매수/순매도 방향이 얼마나 자주 일치하는지 본다. 보조 검증으로 COUNTERSIDE가 실제 기관, 외인, "
                "기타법인 중 어느 쪽 흐름과 가까운지도 비교했다. 규모가 다른 시계열의 양상 비교는 각 주체별 max-abs "
                "정규화, z-score 정규화, 누적 max-abs 정규화 지표를 사용한다.",
                styles["KBody"],
            )
        )
        overview = [
            ["항목", "Value", "Volume"],
            ["겹치는 거래일", summary["value"]["overlap_days"], summary["volume"]["overlap_days"]],
            ["LLM vs 개인 방향 일치율", pct(v_primary["direction_match_rate"]), pct(q_primary["direction_match_rate"])],
            [
                "MaxAbs 정규화 상관계수",
                score_text(v_primary["max_abs_normalized"]["pearson_correlation"]),
                score_text(q_primary["max_abs_normalized"]["pearson_correlation"]),
            ],
            [
                "MaxAbs 정규화 코사인",
                score_text(v_primary["max_abs_normalized"]["cosine_similarity"]),
                score_text(q_primary["max_abs_normalized"]["cosine_similarity"]),
            ],
            [
                "누적 정규화 상관계수",
                score_text(v_primary["cumulative_max_abs_normalized"]["pearson_correlation"]),
                score_text(q_primary["cumulative_max_abs_normalized"]["pearson_correlation"]),
            ],
        ]
        story.append(table([[para(c, styles["KSmall"]) for c in row] for row in overview], [50 * mm, 55 * mm, 55 * mm]))

        dates = [row["date"] for row in value_rows]
        value_llm = [num(row["llm_net"]) for row in value_rows]
        value_individuals = [num(row["Individuals"]) for row in value_rows]
        value_counterside = [num(row["counterside_net"]) for row in value_rows]
        volume_llm = [num(row["llm_net"]) for row in volume_rows]
        volume_individuals = [num(row["Individuals"]) for row in volume_rows]
        volume_counterside = [num(row["counterside_net"]) for row in volume_rows]
        story.append(
            NormalizedLineChart(
                "Value MaxAbs 정규화 순거래 흐름: LLM vs 개인 vs COUNTERSIDE",
                dates,
                [
                    ("LLM", max_abs_normalize(value_llm), colors.HexColor("#2563eb")),
                    ("Individuals", max_abs_normalize(value_individuals), colors.HexColor("#16a34a")),
                    ("COUNTERSIDE", max_abs_normalize(value_counterside), colors.HexColor("#dc2626")),
                ],
                170 * mm,
            )
        )
        story.append(Spacer(1, 4 * mm))
        story.append(
            NormalizedLineChart(
                "Volume MaxAbs 정규화 순거래 흐름: LLM vs 개인 vs COUNTERSIDE",
                [row["date"] for row in volume_rows],
                [
                    ("LLM", max_abs_normalize(volume_llm), colors.HexColor("#2563eb")),
                    ("Individuals", max_abs_normalize(volume_individuals), colors.HexColor("#16a34a")),
                    ("COUNTERSIDE", max_abs_normalize(volume_counterside), colors.HexColor("#dc2626")),
                ],
                170 * mm,
            )
        )

        story.append(para("2. 지표별 상세 점수", styles["KHeading1"]))
        story.extend(metric_table("Value 기준", summary["value"], styles))
        story.extend(metric_table("Volume 기준", summary["volume"], styles))

        story.append(PageBreak())
        story.append(para("3. 일별 비교 샘플", styles["KHeading1"]))
        sample_rows = [["날짜", "LLM Value", "개인 Value", "일치", "LLM Volume", "개인 Volume", "일치"]]
        volume_by_date = {row["date"]: row for row in volume_rows}
        for row in value_rows[:30]:
            qrow = volume_by_date[row["date"]]
            sample_rows.append(
                [
                    row["date"],
                    f"{direction_label_ko(num(row['llm_net']))}\n{fmt_int(row['llm_net'])}",
                    f"{direction_label_ko(num(row['Individuals']))}\n{fmt_int(row['Individuals'])}",
                    "Y" if row["llm_matches_individuals"] else "N",
                    f"{direction_label_ko(num(qrow['llm_net']))}\n{fmt_int(qrow['llm_net'])}",
                    f"{direction_label_ko(num(qrow['Individuals']))}\n{fmt_int(qrow['Individuals'])}",
                    "Y" if qrow["llm_matches_individuals"] else "N",
                ]
            )
        story.append(
            table(
                [[para(c, styles["KSmall"]) for c in row] for row in sample_rows],
                [23 * mm, 27 * mm, 31 * mm, 12 * mm, 27 * mm, 31 * mm, 12 * mm],
            )
        )

        story.append(para("4. 해석", styles["KHeading1"]))
        story.append(para(make_interpretation(summary), styles["KBody"]))

    doc = SimpleDocTemplate(
        str(report_path),
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="TwinMarket Korea 거래 방향 검증 보고서",
    )
    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)


def make_interpretation(summary: dict[str, Any]) -> str:
    value_match = summary["value"]["llm_vs_individuals"]["direction_match_rate"]
    volume_match = summary["volume"]["llm_vs_individuals"]["direction_match_rate"]
    value_corr = summary["value"]["llm_vs_individuals"]["max_abs_normalized"]["pearson_correlation"]
    volume_corr = summary["volume"]["llm_vs_individuals"]["max_abs_normalized"]["pearson_correlation"]
    value_cumulative_corr = summary["value"]["llm_vs_individuals"]["cumulative_max_abs_normalized"]["pearson_correlation"]
    volume_cumulative_corr = summary["volume"]["llm_vs_individuals"]["cumulative_max_abs_normalized"]["pearson_correlation"]
    best_counter = []
    for dimension in ("value", "volume"):
        metrics = summary[dimension]["counterside_vs_investor_groups"]
        ranked = sorted(
            metrics.items(),
            key=lambda item: (
                -1 if item[1]["direction_match_rate"] is None else item[1]["direction_match_rate"],
                -1
                if item[1]["max_abs_normalized"]["cosine_similarity"] is None
                else item[1]["max_abs_normalized"]["cosine_similarity"],
            ),
            reverse=True,
        )
        if ranked:
            investor, metric = ranked[0]
            best_counter.append(f"{dimension}: {investor} 방향 일치율 {pct(metric['direction_match_rate'])}")
    return (
        f"LLM 에이전트와 실제 개인 투자자의 방향 일치율은 Value {pct(value_match)}, Volume {pct(volume_match)}이다. "
        f"MaxAbs 정규화 상관계수는 Value {score_text(value_corr)}, Volume {score_text(volume_corr)}이며, "
        f"누적 정규화 상관계수는 Value {score_text(value_cumulative_corr)}, Volume {score_text(volume_cumulative_corr)}이다. "
        "방향 일치율이 높고 정규화 상관계수/코사인 유사도가 양수로 안정적이면 실제 개인 투자자 흐름을 시뮬레이션이 어느 정도 "
        "재현한다고 해석할 수 있다. COUNTERSIDE 보조 비교에서 가장 가까운 실제 투자자 그룹은 "
        + "; ".join(best_counter)
        + "이다."
    )


def safe_run_name(run_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id).strip("_") or "run"


def main() -> None:
    args = parse_args()
    try:
        actual_value = load_actual(args.actual_value)
        actual_volume = load_actual(args.actual_volume)
        run_id, simulation = load_simulation(args.run_dir, args.stock_code)

        output_dir = args.output_dir or (VALIDATION_DIR / "outputs" / safe_run_name(run_id))
        output_dir.mkdir(parents=True, exist_ok=True)

        value_rows = build_comparison_rows(label="value", actual=actual_value, simulation=simulation)
        volume_rows = build_comparison_rows(label="volume", actual=actual_volume, simulation=simulation)
        skipped_value_dates = [row["date"] for row in value_rows[: args.skip_initial_days]]
        skipped_volume_dates = [row["date"] for row in volume_rows[: args.skip_initial_days]]
        value_rows = skip_initial_rows(value_rows, args.skip_initial_days)
        volume_rows = skip_initial_rows(volume_rows, args.skip_initial_days)
        fieldnames = [
            "date",
            "llm_net",
            "llm_direction",
            "counterside_net",
            "counterside_direction",
            *[item for column in ACTUAL_INVESTOR_COLUMNS for item in (column, f"{column}_direction")],
            "llm_matches_individuals",
        ]
        write_csv(output_dir / "daily_comparison_value.csv", value_rows, fieldnames)
        write_csv(output_dir / "daily_comparison_volume.csv", volume_rows, fieldnames)
        write_csv(output_dir / "normalized_comparison_value.csv", build_normalized_rows(value_rows), normalized_fieldnames())
        write_csv(output_dir / "normalized_comparison_volume.csv", build_normalized_rows(volume_rows), normalized_fieldnames())

        summary = {
            "run_id": run_id,
            "run_dir": str(args.run_dir.resolve()),
            "actual_value": str(args.actual_value.resolve()),
            "actual_volume": str(args.actual_volume.resolve()),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "skip_initial_days": args.skip_initial_days,
            "skipped_value_dates": skipped_value_dates,
            "skipped_volume_dates": skipped_volume_dates,
            "value": summarize_dimension(value_rows, "value"),
            "volume": summarize_dimension(volume_rows, "volume"),
        }
        with (output_dir / "summary_metrics.json").open("w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        build_report(
            report_path=output_dir / "validation_report.pdf",
            run_id=run_id,
            run_dir=args.run_dir.resolve(),
            value_rows=value_rows,
            volume_rows=volume_rows,
            summary=summary,
        )
    except Exception as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        raise

    print(output_dir)
    print(output_dir / "summary_metrics.json")
    print(output_dir / "validation_report.pdf")


if __name__ == "__main__":
    main()
