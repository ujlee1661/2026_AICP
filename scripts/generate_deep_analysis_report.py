"""
TwinMarket 심층 분석 보고서 생성기 (v2 — Depth 색상 + 텍스트 분석 포함)

Usage:
  python scripts/generate_deep_analysis_report.py --run-id simulation_20260701_180626
Output:
  outputs/reports/deep_analysis_{run_id}.pdf

변경 내역 (v2):
  - Turnover vs 수익률 → Depth별 색상 구분 + Violin 패널 추가
  - 에이전트별 최종 수익률 분포 (Depth별) 신규 차트 추가
  - 각 섹션 앞에 분석 배경·해석 텍스트 페이지 추가
  - run_metadata.json에서 Depth 정보 자동 로드
"""

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
random.seed(42)

# ── 폰트 설정 ─────────────────────────────────────────────────────────────
FONT_CANDIDATES = [
    "C:/Windows/Fonts/malgun.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/Library/Fonts/AppleGothic.ttf",
]
for font_path in FONT_CANDIDATES:
    if Path(font_path).exists():
        fp = fm.FontProperties(fname=font_path)
        matplotlib.rcParams["font.family"] = fp.get_name()
        break
matplotlib.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_START = "2026-04-29"  # 워밍업 3일 제외
SYSTEM_USERS = {"INSTITUTIONAL", ""}

# Depth별 색상 팔레트
DEPTH_COLORS = {0: "#7f8c8d", 1: "#1a6fa8", 2: "#e67e22"}
DEPTH_LABELS = {0: "Depth 0 (헤드라인만)", 1: "Depth 1 (요약 포함)", 2: "Depth 2 (키워드 검색)"}
DEPTH_MARKERS = {0: "o", 1: "s", 2: "^"}


# ── 공통 유틸 ─────────────────────────────────────────────────────────────

def flt(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def agent_id(row: dict) -> str:
    return str(row.get("agent_id") or row.get("user_id") or "")


def action_of(row: dict) -> str:
    return str(row.get("action") or row.get("direction") or row.get("trading_direction") or "").lower()


def quantity_of(row: dict) -> float:
    return flt(row.get("quantity") or row.get("executed_quantity") or row.get("filled_quantity") or row.get("volume"))


def close_price_of(row: dict) -> float:
    return flt(row.get("close_price") or row.get("closing_price") or row.get("announced_price"))


def announced_price_of(row: dict) -> float:
    return flt(row.get("announced_price") or row.get("executed_price") or row.get("close_price") or row.get("closing_price"))


def write_text_page(pdf: PdfPages, title: str, sections: list[tuple[str, list[str]]],
                    footnote: str = ""):
    """
    텍스트 전용 분석 페이지를 PDF에 추가한다.
    sections: [(섹션제목, [bullet_line, ...]), ...]
    """
    fig, ax = plt.subplots(figsize=(12, 9))
    ax.axis("off")
    fig.patch.set_facecolor("#fafafa")

    # 타이틀
    ax.text(0.5, 0.97, title, transform=ax.transAxes,
            ha="center", va="top", fontsize=16, fontweight="bold", color="#1a252f")
    ax.plot([0.05, 0.95], [0.945, 0.945], color="#bdc3c7", lw=1.0,
            transform=ax.transAxes)

    y = 0.905
    for sec_title, bullets in sections:
        if y < 0.05:
            break
        ax.text(0.06, y, f"■ {sec_title}", transform=ax.transAxes,
                ha="left", va="top", fontsize=11, fontweight="bold", color="#2c3e50")
        y -= 0.042
        for bullet in bullets:
            if y < 0.05:
                break
            ax.text(0.09, y, f"• {bullet}", transform=ax.transAxes,
                    ha="left", va="top", fontsize=9.5, color="#34495e",
                    wrap=True)
            # 긴 줄이면 추가 줄 내림
            line_len = len(bullet)
            y -= 0.033 if line_len < 80 else 0.048
        y -= 0.018

    if footnote:
        ax.text(0.5, 0.02, footnote, transform=ax.transAxes,
                ha="center", va="bottom", fontsize=8, color="#95a5a6",
                style="italic")

    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


# ── 데이터 로드 ───────────────────────────────────────────────────────────

def load_data(run_id: str) -> dict:
    log_dir = ROOT / "outputs" / "logs" / run_id

    orders = list(csv.DictReader(open(log_dir / "submitted_orders.csv", encoding="utf-8-sig")))
    fills = list(csv.DictReader(open(log_dir / "exchange_fills.csv", encoding="utf-8-sig")))
    daily = list(csv.DictReader(open(log_dir / "daily_exchange_summary.csv", encoding="utf-8-sig")))

    portfolio_events = []
    with open(log_dir / "portfolio_updates.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                portfolio_events.append(json.loads(line))

    # run_metadata.json에서 Depth 정보 로드
    agent_depths: dict[str, int] = {}
    metadata: dict = {}
    meta_path = log_dir / "run_metadata.json"
    if meta_path.exists():
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        raw_depths = metadata.get("agent_depths", {})
        agent_depths = {aid: int(d) for aid, d in raw_depths.items()}

    # submitted_orders에서도 depth 보완 시도 (news_depth 컬럼 존재 시)
    if not agent_depths:
        for o in orders:
            aid = o.get("agent_id") or o.get("user_id", "")
            d = o.get("news_depth")
            if aid and d is not None:
                agent_depths[aid] = int(d)

    daily_rows = sorted(daily, key=lambda r: (r.get("date", ""), flt(r.get("turn"))))
    by_date: dict[str, list[dict]] = defaultdict(list)
    for row in daily_rows:
        if row.get("date"):
            by_date[row["date"]].append(row)

    daily_sorted = []
    close_by_date: dict[str, float] = {}
    volume_by_date: dict[str, float] = {}
    for day in sorted(by_date):
        rows = by_date[day]
        pm_rows = [r for r in rows if str(r.get("subturn", "")).lower() == "pm"]
        close_row = pm_rows[-1] if pm_rows else rows[-1]
        close_by_date[day] = close_price_of(close_row)
        volume_by_date[day] = sum(flt(r.get("volume")) for r in rows)
        daily_sorted.append({**close_row, "date": day, "close_price": close_by_date[day], "volume": volume_by_date[day]})
    dates_all = [r["date"] for r in daily_sorted]

    prev_close = {dates_all[i]: close_by_date[dates_all[i - 1]]
                  for i in range(1, len(dates_all))}

    agent_fills = [f for f in fills if agent_id(f) not in SYSTEM_USERS]

    analysis_dates = [d for d in dates_all if d >= ANALYSIS_START]
    if not analysis_dates:
        analysis_dates = dates_all

    # 에이전트별 최종 수익률
    final_return: dict[str, float] = {}
    initial_value: dict[str, float] = {}
    for evt in portfolio_events:
        aid = evt.get("agent_id")
        state = evt.get("state", {})
        if aid and state.get("total_return_rate") is not None:
            final_return[aid] = state["total_return_rate"] * 100
        if aid and state.get("total_value") and not initial_value.get(aid):
            # 첫 번째 이벤트의 total_value를 초기값으로 추정
            pass
    # 마지막 이벤트로만 덮어씌워서 최종값 확정
    agent_timeline = defaultdict(list)
    for evt in portfolio_events:
        aid = evt.get("agent_id")
        if aid:
            agent_timeline[aid].append(evt)
    for aid, evts in agent_timeline.items():
        evts.sort(key=lambda e: (e.get("turn", 0), e.get("date", "")))
        last = evts[-1]["state"]
        if last.get("total_return_rate") is not None:
            final_return[aid] = last["total_return_rate"] * 100

    return {
        "orders": orders,
        "fills": fills,
        "agent_fills": agent_fills,
        "daily_sorted": daily_sorted,
        "close_by_date": close_by_date,
        "volume_by_date": volume_by_date,
        "dates_all": dates_all,
        "prev_close": prev_close,
        "portfolio_events": portfolio_events,
        "agent_timeline": agent_timeline,
        "analysis_dates": analysis_dates,
        "agent_depths": agent_depths,
        "final_return": final_return,
        "run_id": run_id,
        "metadata": metadata,
    }


# ── 표지 페이지 ───────────────────────────────────────────────────────────

def write_cover_page(data: dict, pdf: PdfPages):
    analysis_dates = data["analysis_dates"]
    agent_fills = data["agent_fills"]
    daily_sorted = data["daily_sorted"]
    agent_depths = data["agent_depths"]

    agents = sorted(set(agent_id(f) for f in agent_fills if agent_id(f)))
    first_price = close_price_of(daily_sorted[0]) if daily_sorted else 0
    last_price = close_price_of(daily_sorted[-1]) if daily_sorted else 0
    total_return = (last_price - first_price) / first_price * 100 if first_price else 0

    depth_counts = {0: 0, 1: 0, 2: 0}
    for d in agent_depths.values():
        depth_counts[int(d)] = depth_counts.get(int(d), 0) + 1
    depth_str = f"Depth 0: {depth_counts[0]}명  |  Depth 1: {depth_counts[1]}명  |  Depth 2: {depth_counts[2]}명"

    info_mode = data["metadata"].get("information_mode", "pre_close_cutoff")
    decision_space = data["metadata"].get("decision_space", "buy_sell_only")

    fig, ax = plt.subplots(figsize=(12, 9))
    ax.axis("off")

    lines = [
        ("심층 분석 보고서 v2", 0.87, 22, "bold", "#1a252f"),
        ("TwinMarket Deep Analysis Report", 0.81, 14, "normal", "#5d6d7e"),
        ("", 0.76, 1, "normal", "white"),
        (f"실험 ID: {data['run_id']}", 0.71, 12, "normal", "#2c3e50"),
        (f"분석 기간: {analysis_dates[0]} ~ {analysis_dates[-1]}  ({len(analysis_dates)}거래일)", 0.66, 11, "normal", "#2c3e50"),
        (f"에이전트: {len(agents)}명  ({depth_str})", 0.61, 11, "normal", "#2c3e50"),
        (f"종목: 삼성전자 005930  |  정보 모드: {info_mode}  |  의사결정 공간: {decision_space}", 0.56, 11, "normal", "#2c3e50"),
        (f"주가 변동: {first_price:,.0f}원 → {last_price:,.0f}원  ({total_return:+.1f}%)", 0.51, 11, "normal", "#c0392b" if total_return < 0 else "#1a6fa8"),
        ("", 0.44, 1, "normal", "white"),
        ("포함 분석 목록", 0.39, 13, "bold", "#1a6fa8"),
        ("1. Turnover vs 최종 수익률  (Depth별 색상 구분)", 0.34, 10.5, "normal", "#2c3e50"),
        ("2. 에이전트별 최종 수익률 분포  (Depth별 violin / box 비교)", 0.30, 10.5, "normal", "#2c3e50"),
        ("3. 매수/매도 의사결정 분포 & 검증 오류율", 0.26, 10.5, "normal", "#2c3e50"),
        ("4. Disposition Effect  (이익 vs 손실 실현 성향)", 0.22, 10.5, "normal", "#2c3e50"),
        ("5. 거래량 클러스터링  (전일 → 당일 자기상관)", 0.18, 10.5, "normal", "#2c3e50"),
        ("6. Gini 계수 & Lorenz Curve  (에이전트 간 거래 집중도)", 0.14, 10.5, "normal", "#2c3e50"),
        ("* 각 섹션 앞뒤에 분석 배경 및 해석 텍스트 페이지 포함", 0.07, 9, "normal", "#7f8c8d"),
    ]

    for text, y, size, weight, color in lines:
        ax.text(0.5, y, text, transform=ax.transAxes,
                ha="center", va="center", fontsize=size,
                fontweight=weight, color=color)

    ax.plot([0.08, 0.92], [0.78, 0.78], color="#bdc3c7", lw=1.5, transform=ax.transAxes)
    ax.plot([0.08, 0.92], [0.42, 0.42], color="#bdc3c7", lw=1.0, transform=ax.transAxes)
    fig.patch.set_facecolor("#fdfefe")
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


# ── 차트 1: Turnover vs 최종 수익률 (Depth별 색상) ─────────────────────

def plot_turnover_pnl_depth(data: dict, pdf: PdfPages):
    agent_fills = data["agent_fills"]
    final_return = data["final_return"]
    agent_depths = data["agent_depths"]

    # 에이전트별 총 거래금액(Turnover)
    turnover: dict[str, float] = defaultdict(float)
    for f in agent_fills:
        aid = agent_id(f)
        turnover[aid] += flt(f.get("executed_price")) * quantity_of(f)

    # 초기 포트폴리오 가치 추정 (첫 이벤트의 total_value - realized_pnl ≈ ini_cash)
    ini_cash_by_agent: dict[str, float] = {}
    for aid, evts in data["agent_timeline"].items():
        if evts:
            s = evts[0]["state"]
            v = s.get("total_value", 0) or 0
            ini_cash_by_agent[aid] = float(v) if v else 100_000_000

    agents = sorted(set(turnover) & set(final_return))
    depth_groups: dict[int, list] = {0: [], 1: [], 2: []}
    for aid in agents:
        ini = ini_cash_by_agent.get(aid, 100_000_000)
        t_ratio = turnover[aid] / ini if ini else 0  # Turnover ratio
        ret = final_return[aid]
        d = agent_depths.get(aid, 1)
        depth_groups[d].append((aid, t_ratio, ret))

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # ── 왼쪽: 산점도 ──
    ax = axes[0]
    all_x, all_y = [], []
    for d in [0, 1, 2]:
        pts = depth_groups[d]
        if not pts:
            continue
        xs = [p[1] for p in pts]
        ys = [p[2] for p in pts]
        all_x.extend(xs)
        all_y.extend(ys)
        ax.scatter(xs, ys,
                   c=DEPTH_COLORS[d], s=100, alpha=0.88,
                   marker=DEPTH_MARKERS[d],
                   edgecolors="white", linewidths=0.8,
                   label=DEPTH_LABELS[d], zorder=5)
        for aid, x, y in pts:
            ax.annotate(aid[-3:], (x, y), textcoords="offset points",
                        xytext=(4, 4), fontsize=5.5, color="#555", alpha=0.7)

    if len(all_x) > 2:
        z = np.polyfit(all_x, all_y, 1)
        px = np.linspace(min(all_x), max(all_x), 100)
        ax.plot(px, np.poly1d(z)(px), color="#636e72", lw=1.8, ls="--",
                alpha=0.75, label="추세선 (전체)", zorder=4)
        corr = np.corrcoef(all_x, all_y)[0, 1]
        ax.text(0.97, 0.04, f"Pearson r = {corr:.3f}",
                transform=ax.transAxes, ha="right", va="bottom",
                fontsize=10.5, color="#636e72",
                bbox=dict(facecolor="white", alpha=0.85, edgecolor="lightgray", pad=4))

    ax.axhline(0, color="gray", lw=1.0, ls="-", alpha=0.35)
    ax.set_xlabel("Turnover Ratio  (총 거래금액 / 초기 포트폴리오)", fontsize=11)
    ax.set_ylabel("최종 수익률 (%)", fontsize=11)
    ax.set_title("Turnover vs 최종 수익률\n(Depth별 색상 구분)", fontsize=12, fontweight="bold")
    ax.legend(fontsize=9.5, loc="upper right")
    ax.grid(alpha=0.22, ls=":")
    ax.set_facecolor("#f8f9fa")

    # ── 오른쪽: Violin + Strip 패널 ──
    ax2 = axes[1]
    group_data = []
    group_labels = []
    group_colors = []
    for d in [0, 1, 2]:
        pts = depth_groups[d]
        if pts:
            group_data.append([p[2] for p in pts])
            group_labels.append(f"Depth {d}\n(n={len(pts)})")
            group_colors.append(DEPTH_COLORS[d])

    if group_data:
        vp = ax2.violinplot(group_data, positions=range(len(group_data)),
                            showmedians=True, showextrema=True, widths=0.6)
        for i, (body, col) in enumerate(zip(vp["bodies"], group_colors)):
            body.set_facecolor(col)
            body.set_alpha(0.45)
        vp["cmedians"].set_color("#2c3e50")
        vp["cmins"].set_color("#636e72")
        vp["cmaxes"].set_color("#636e72")
        vp["cbars"].set_color("#636e72")

        # Strip plot (jitter)
        for i, (pts_d, col) in enumerate(zip(group_data, group_colors)):
            jitter = [random.uniform(-0.15, 0.15) for _ in pts_d]
            ax2.scatter([i + j for j in jitter], pts_d,
                        c=col, s=40, alpha=0.75, edgecolors="white",
                        linewidths=0.6, zorder=5)

        ax2.set_xticks(range(len(group_labels)))
        ax2.set_xticklabels(group_labels, fontsize=10)
        ax2.axhline(0, color="gray", lw=1.0, ls="--", alpha=0.4)

    ax2.set_ylabel("최종 수익률 (%)", fontsize=11)
    ax2.set_title("Depth 그룹별 수익률 분포\n(Violin + Strip)", fontsize=12, fontweight="bold")
    ax2.grid(axis="y", alpha=0.22, ls=":")
    ax2.set_facecolor("#f8f9fa")

    # 전체 수익률 통계
    all_rets = list(final_return.values())
    stats_text = (f"전체 중앙값: {np.median(all_rets):.2f}%  |  "
                  f"평균: {np.mean(all_rets):.2f}%  |  "
                  f"수익 에이전트: {sum(1 for r in all_rets if r>0)}/{len(all_rets)}명")

    fig.suptitle(f"에이전트 Turnover vs 최종 수익률  —  {data['run_id']}\n{stats_text}",
                 fontsize=12, fontweight="bold")
    fig.patch.set_facecolor("white")
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


# ── 차트 2 (신규): 에이전트별 최종 수익률 분포 (Depth별 상세) ─────────────

def plot_return_distribution_by_depth(data: dict, pdf: PdfPages):
    final_return = data["final_return"]
    agent_depths = data["agent_depths"]
    agent_fills = data["agent_fills"]

    # 에이전트별 총 거래 건수 (활동성 지표)
    trade_count: dict[str, int] = defaultdict(int)
    for f in agent_fills:
        trade_count[agent_id(f)] += 1

    agents_by_depth: dict[int, list[str]] = {0: [], 1: [], 2: []}
    for aid in final_return:
        d = agent_depths.get(aid, 1)
        agents_by_depth[d].append(aid)

    fig, axes = plt.subplots(2, 2, figsize=(15, 11))
    fig.suptitle(f"에이전트별 최종 수익률 분포 (Depth별 색상)  —  {data['run_id']}",
                 fontsize=13, fontweight="bold")

    # ── 패널 (0,0): 전체 에이전트 수익률 막대 (에이전트 ID 기준 정렬) ──
    ax00 = axes[0, 0]
    sorted_agents = sorted(final_return.items(), key=lambda x: x[1])
    s_aids = [a for a, _ in sorted_agents]
    s_rets = [r for _, r in sorted_agents]
    s_colors = [DEPTH_COLORS[agent_depths.get(a, 1)] for a in s_aids]

    bars = ax00.barh(range(len(s_aids)), s_rets, color=s_colors,
                     alpha=0.85, edgecolor="white", linewidth=0.5, height=0.75)
    ax00.axvline(0, color="#636e72", lw=1.0, ls="-", alpha=0.5)
    ax00.set_yticks(range(len(s_aids)))
    ax00.set_yticklabels(s_aids, fontsize=6.5)
    ax00.set_xlabel("최종 수익률 (%)", fontsize=10)
    ax00.set_title("전체 에이전트 최종 수익률\n(Depth별 색상, 오름차순)", fontsize=10, fontweight="bold")

    for d in [0, 1, 2]:
        ax00.barh([], [], color=DEPTH_COLORS[d], label=DEPTH_LABELS[d], alpha=0.85)
    ax00.legend(fontsize=7.5, loc="lower right")
    ax00.set_facecolor("#f8f9fa")
    ax00.grid(axis="x", alpha=0.2, ls=":")

    # ── 패널 (0,1): Depth별 박스플롯 ──
    ax01 = axes[0, 1]
    box_data = []
    box_labels = []
    box_colors = []
    for d in [0, 1, 2]:
        aids = agents_by_depth[d]
        rets = [final_return[a] for a in aids if a in final_return]
        if rets:
            box_data.append(rets)
            box_labels.append(f"Depth {d}\n(n={len(rets)})")
            box_colors.append(DEPTH_COLORS[d])

    if box_data:
        bp = ax01.boxplot(box_data, patch_artist=True, widths=0.5,
                          medianprops=dict(color="#2c3e50", lw=2.5),
                          whiskerprops=dict(color="#636e72", lw=1.2),
                          capprops=dict(color="#636e72", lw=1.5),
                          flierprops=dict(marker="o", markersize=5, alpha=0.6))
        for patch, col in zip(bp["boxes"], box_colors):
            patch.set_facecolor(col)
            patch.set_alpha(0.5)
        ax01.set_xticklabels(box_labels, fontsize=10)

        # 통계 텍스트 추가
        for i, (d_rets, lbl) in enumerate(zip(box_data, box_labels)):
            med = np.median(d_rets)
            mn = np.mean(d_rets)
            ax01.text(i + 1, max(d_rets) + 0.5,
                      f"μ={mn:.1f}%\nm={med:.1f}%",
                      ha="center", va="bottom", fontsize=7.5, color="#2c3e50")

    ax01.axhline(0, color="gray", lw=1.0, ls="--", alpha=0.4)
    ax01.set_ylabel("최종 수익률 (%)", fontsize=10)
    ax01.set_title("Depth별 수익률 박스플롯\n(μ=평균, m=중앙값)", fontsize=10, fontweight="bold")
    ax01.set_facecolor("#f8f9fa")
    ax01.grid(axis="y", alpha=0.22, ls=":")

    # ── 패널 (1,0): Depth별 히스토그램 ──
    ax10 = axes[1, 0]
    all_rets_flat = list(final_return.values())
    bin_edges = np.linspace(min(all_rets_flat) - 1, max(all_rets_flat) + 1, 20)

    for d in [0, 1, 2]:
        aids = agents_by_depth[d]
        rets = [final_return[a] for a in aids if a in final_return]
        if rets:
            ax10.hist(rets, bins=bin_edges, color=DEPTH_COLORS[d],
                      alpha=0.55, label=DEPTH_LABELS[d], edgecolor="white")

    ax10.axvline(0, color="#636e72", lw=1.5, ls="--", alpha=0.6)
    ax10.axvline(np.mean(all_rets_flat), color="#c0392b", lw=1.5, ls="-.",
                 alpha=0.8, label=f"전체 평균 ({np.mean(all_rets_flat):.2f}%)")
    ax10.set_xlabel("최종 수익률 (%)", fontsize=10)
    ax10.set_ylabel("에이전트 수", fontsize=10)
    ax10.set_title("Depth별 수익률 히스토그램", fontsize=10, fontweight="bold")
    ax10.legend(fontsize=8)
    ax10.set_facecolor("#f8f9fa")
    ax10.grid(alpha=0.22, ls=":")

    # ── 패널 (1,1): 거래 건수 vs 수익률 (Depth별 색상) ──
    ax11 = axes[1, 1]
    for d in [0, 1, 2]:
        aids = agents_by_depth[d]
        xs = [trade_count.get(a, 0) for a in aids if a in final_return]
        ys = [final_return[a] for a in aids if a in final_return]
        if xs:
            ax11.scatter(xs, ys, c=DEPTH_COLORS[d], s=80, alpha=0.82,
                         marker=DEPTH_MARKERS[d], edgecolors="white",
                         linewidths=0.7, label=DEPTH_LABELS[d], zorder=5)

    ax11.axhline(0, color="gray", lw=1.0, ls="-", alpha=0.35)
    all_xs = [trade_count.get(a, 0) for a in final_return]
    all_ys = list(final_return.values())
    if len(all_xs) > 2:
        z = np.polyfit(all_xs, all_ys, 1)
        px = np.linspace(min(all_xs), max(all_xs), 100)
        ax11.plot(px, np.poly1d(z)(px), color="#636e72", lw=1.5, ls="--",
                  alpha=0.7, zorder=3)
        corr = np.corrcoef(all_xs, all_ys)[0, 1]
        ax11.text(0.97, 0.04, f"r = {corr:.3f}",
                  transform=ax11.transAxes, ha="right", va="bottom",
                  fontsize=10, color="#636e72",
                  bbox=dict(facecolor="white", alpha=0.85, edgecolor="lightgray", pad=4))

    ax11.set_xlabel("체결 건수", fontsize=10)
    ax11.set_ylabel("최종 수익률 (%)", fontsize=10)
    ax11.set_title("체결 건수 vs 수익률\n(과잉거래 분석)", fontsize=10, fontweight="bold")
    ax11.legend(fontsize=8.5, loc="upper right")
    ax11.set_facecolor("#f8f9fa")
    ax11.grid(alpha=0.22, ls=":")

    fig.patch.set_facecolor("white")
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


# ── 차트 3: 매수/매도 분포 + 검증 오류율 ────────────────────────────────

def plot_order_fill_range(data: dict, pdf: PdfPages):
    orders = data["orders"]
    agent_fills = data["agent_fills"]
    analysis_dates = data["analysis_dates"]
    close_by_date = data["close_by_date"]

    C_BUY = "#1a6fa8"
    C_SELL = "#c0392b"
    C_ERR = "#8e44ad"
    C_PRICE = "#b7950b"

    submitted_by_date = defaultdict(lambda: {"buy": 0, "sell": 0, "invalid": 0})
    for o in orders:
        d = o.get("date")
        if d not in analysis_dates:
            continue
        action = action_of(o)
        if action in {"buy", "sell"}:
            submitted_by_date[d][action] += 1
        else:
            submitted_by_date[d]["invalid"] += 1

    filled_by_date = defaultdict(lambda: {"buy_qty": 0.0, "sell_qty": 0.0, "buy_count": 0, "sell_count": 0})
    for f in agent_fills:
        d = f.get("date")
        if d not in analysis_dates:
            continue
        action = action_of(f)
        qty = quantity_of(f)
        if action == "buy":
            filled_by_date[d]["buy_qty"] += qty
            filled_by_date[d]["buy_count"] += 1
        elif action == "sell":
            filled_by_date[d]["sell_qty"] += qty
            filled_by_date[d]["sell_count"] += 1

    N = len(analysis_dates)
    if N == 0:
        return

    fig, ax = plt.subplots(figsize=(max(18, N * 0.9), 9))
    ax2 = ax.twinx()

    x = np.arange(N)
    buy_qty = [filled_by_date[d]["buy_qty"] for d in analysis_dates]
    sell_qty = [filled_by_date[d]["sell_qty"] for d in analysis_dates]
    buy_count = [filled_by_date[d]["buy_count"] for d in analysis_dates]
    sell_count = [filled_by_date[d]["sell_count"] for d in analysis_dates]
    total_submitted = [submitted_by_date[d]["buy"] + submitted_by_date[d]["sell"] + submitted_by_date[d]["invalid"] for d in analysis_dates]
    invalid = [submitted_by_date[d]["invalid"] for d in analysis_dates]
    validation_error_rate = [
        (invalid[i] / total_submitted[i] * 100) if total_submitted[i] else 0.0
        for i in range(N)
    ]

    width = 0.38
    ax.bar(x - width / 2, buy_qty, width, color=C_BUY, alpha=0.82, label="매수 체결 수량")
    ax.bar(x + width / 2, [-v for v in sell_qty], width, color=C_SELL, alpha=0.82, label="매도 체결 수량")
    ax.axhline(0, color="#636e72", lw=1.0, alpha=0.6)

    for xi, bc, sc in zip(x, buy_count, sell_count):
        y_top = max(buy_qty[xi], 0)
        y_bottom = -max(sell_qty[xi], 0)
        if bc:
            ax.text(xi - width / 2, y_top, str(bc), ha="center", va="bottom", fontsize=7, color=C_BUY)
        if sc:
            ax.text(xi + width / 2, y_bottom, str(sc), ha="center", va="top", fontsize=7, color=C_SELL)

    prices = [close_by_date.get(d) for d in analysis_dates]
    ax2.plot(x, [p / 1000 for p in prices],
             color=C_PRICE, lw=2.0, ls="-", marker="o", ms=4, alpha=0.80, label="종가(천원)", zorder=3)
    ax3 = ax.twinx()
    ax3.spines["right"].set_position(("axes", 1.08))
    ax3.plot(x, validation_error_rate, color=C_ERR, lw=1.8, marker="x", ms=5,
             alpha=0.85, label="검증 오류율(%)", zorder=4)
    ax2.set_ylabel("종가 (천원)", color=C_PRICE, fontsize=11)
    ax2.tick_params(axis="y", colors=C_PRICE, labelsize=9)
    ax3.set_ylabel("검증 오류율 (%)", color=C_ERR, fontsize=11)
    ax3.tick_params(axis="y", colors=C_ERR, labelsize=9)
    ax3.set_ylim(0, max(5, max(validation_error_rate or [0]) * 1.25))

    short_labels = [d[5:] for d in analysis_dates]
    ax.set_xticks(x)
    ax.set_xticklabels(short_labels, rotation=35, ha="right", fontsize=9)
    ax.set_xlim(-0.65, N - 0.35)
    ax.set_ylabel("체결 수량 (매수 + / 매도 -)", fontsize=12)
    ax.set_xlabel("날짜", fontsize=10)

    legend_elements = [
        mpatches.Patch(facecolor=C_BUY, alpha=0.82, label="매수 체결 수량"),
        mpatches.Patch(facecolor=C_SELL, alpha=0.82, label="매도 체결 수량"),
        mlines.Line2D([0], [0], color=C_PRICE, lw=2, marker="o", ms=4, label="종가 (우축)"),
        mlines.Line2D([0], [0], color=C_ERR, lw=1.8, marker="x", ms=5, label="검증 오류율 (보조축)"),
    ]
    ax.legend(handles=legend_elements, loc="lower left", fontsize=8.5, ncol=4,
              bbox_to_anchor=(0.0, -0.22), borderaxespad=0, framealpha=0.92)

    ax.set_title(
        f"일별 매수/매도 의사결정 분포 & 검증 오류율\n"
        f"{data['run_id']}  |  공시가 기반 전량 체결",
        fontsize=12, fontweight="bold", pad=12)
    ax.set_facecolor("#f8f9fa")
    ax.grid(axis="y", alpha=0.20, ls=":", color="gray")
    fig.patch.set_facecolor("white")
    plt.tight_layout(rect=[0, 0.09, 1, 1])
    pdf.savefig(fig)
    plt.close(fig)


# ── 차트 4: Disposition Effect ────────────────────────────────────────────

def plot_disposition_effect(data: dict, pdf: PdfPages):
    portfolio_events = data["portfolio_events"]
    agent_depths = data["agent_depths"]
    agent_fills = data["agent_fills"]

    # 매도 체결 건별 평균단가 추적
    avg_cost_at_sell: list[dict] = []

    # 포트폴리오 이벤트에서 실현 PnL 델타 추출
    sell_gains = []
    sell_losses = []

    agent_timeline = data["agent_timeline"]
    for aid, events in agent_timeline.items():
        prev_realized = 0.0
        for evt in events:
            fills = evt.get("fills", [])
            state = evt.get("state", {})
            curr_realized = state.get("realized_pnl", 0.0) or 0.0

            sell_fills = [f for f in fills if action_of(f) == "sell"]
            if sell_fills:
                delta = curr_realized - prev_realized
                depth = agent_depths.get(aid, 1)
                if delta > 0:
                    sell_gains.append((delta, depth))
                elif delta < 0:
                    sell_losses.append((abs(delta), depth))

            prev_realized = curr_realized

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # 왼쪽: 이익 vs 손실 매도 횟수 비교 (Depth별 색상 누적 바)
    ax = axes[0]
    depth_gain_counts = {0: 0, 1: 0, 2: 0}
    depth_loss_counts = {0: 0, 1: 0, 2: 0}
    for _, d in sell_gains:
        depth_gain_counts[d] += 1
    for _, d in sell_losses:
        depth_loss_counts[d] += 1

    x_pos = [0, 1]
    bottoms = [0, 0]
    for d in [0, 1, 2]:
        gc = depth_gain_counts[d]
        lc = depth_loss_counts[d]
        if gc + lc == 0:
            continue
        ax.bar(0, gc, bottom=bottoms[0], color=DEPTH_COLORS[d],
               alpha=0.82, edgecolor="white", label=DEPTH_LABELS[d] if bottoms[0] == 0 else "")
        ax.bar(1, lc, bottom=bottoms[1], color=DEPTH_COLORS[d], alpha=0.82, edgecolor="white")
        bottoms[0] += gc
        bottoms[1] += lc

    total_gain = len(sell_gains)
    total_loss = len(sell_losses)
    total = total_gain + total_loss
    if total > 0:
        ax.text(0, total_gain + 0.5, str(total_gain), ha="center", va="bottom",
                fontsize=14, fontweight="bold", color="#1a6fa8")
        ax.text(1, total_loss + 0.5, str(total_loss), ha="center", va="bottom",
                fontsize=14, fontweight="bold", color="#c0392b")
        ax.text(0.5, 0.93,
                f"이익 실현 비율: {total_gain/total*100:.1f}%  |  손실 실현 비율: {total_loss/total*100:.1f}%\n"
                f"비율 {total_gain/total_loss:.2f}:1  →  {'이익 빠른 실현 (처분효과 존재)' if total_gain>total_loss else '손실 빠른 실현'}",
                transform=ax.transAxes, ha="center", va="top",
                fontsize=9, color="#2c3e50",
                bbox=dict(facecolor="#f8f9fa", alpha=0.9, edgecolor="lightgray", pad=5))

    ax.set_xticks([0, 1])
    ax.set_xticklabels(["이익 실현\n(Profit Realization)", "손실 실현\n(Loss Realization)"], fontsize=11)
    ax.set_ylabel("매도 이벤트 수", fontsize=11)
    ax.set_title("매도 거래 분류: 이익 vs 손실 실현\n(Depth별 누적 구성)", fontsize=11, fontweight="bold")
    ax.legend(fontsize=8.5, loc="upper right")
    ax.set_facecolor("#f8f9fa")
    ax.grid(axis="y", alpha=0.25, ls=":")

    # 오른쪽: 이익/손실 규모 분포
    ax2 = axes[1]
    if sell_gains:
        ax2.hist([g / 1000 for g, _ in sell_gains], bins=20, color="#1a6fa8",
                 alpha=0.70, label=f"이익 실현 (n={total_gain})", edgecolor="white")
    if sell_losses:
        ax2.hist([l / 1000 for l, _ in sell_losses], bins=20, color="#c0392b",
                 alpha=0.70, label=f"손실 실현 (n={total_loss})", edgecolor="white")
    ax2.set_xlabel("실현 손익 규모 (천 원)", fontsize=11)
    ax2.set_ylabel("빈도", fontsize=11)
    ax2.set_title("실현 손익 규모 분포\n(이익 vs 손실)", fontsize=11, fontweight="bold")
    ax2.legend(fontsize=10)
    ax2.set_facecolor("#f8f9fa")
    ax2.grid(alpha=0.25, ls=":")

    disposition_ratio = total_gain / total_loss if total_loss > 0 else float("inf")
    interpretation = ("이익을 손실보다 빠르게 실현하는 경향 (Disposition Effect 확인됨)"
                      if disposition_ratio > 1 else "손실을 이익보다 빠르게 실현하는 경향")

    fig.suptitle(
        f"Disposition Effect 분석  —  {data['run_id']}\n"
        f"이익 실현 {total_gain}건  /  손실 실현 {total_loss}건  |  해석: {interpretation}",
        fontsize=12, fontweight="bold")
    fig.patch.set_facecolor("white")
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


# ── 차트 5: 거래량 클러스터링 ─────────────────────────────────────────────

def plot_volume_clustering(data: dict, pdf: PdfPages):
    analysis_dates = data["analysis_dates"]
    volume_by_date = data["volume_by_date"]
    close_by_date = data["close_by_date"]
    prev_close = data["prev_close"]

    volumes = [volume_by_date[d] for d in analysis_dates if d in volume_by_date]
    if len(volumes) < 4:
        return

    # 가격 수익률 (절대값 → 변동성 클러스터링용)
    abs_rets = []
    for d in analysis_dates:
        if d in prev_close and prev_close[d] > 0:
            r = abs((close_by_date[d] - prev_close[d]) / prev_close[d] * 100)
            abs_rets.append(r)
        else:
            abs_rets.append(0.0)

    vol_t = volumes[1:]
    vol_t1 = volumes[:-1]
    ret_t = abs_rets[1:]
    ret_t1 = abs_rets[:-1]

    vol_corr = np.corrcoef(vol_t, vol_t1)[0, 1] if len(vol_t) > 2 else 0.0
    ret_corr = np.corrcoef(ret_t, ret_t1)[0, 1] if len(ret_t) > 2 else 0.0

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # 왼쪽: 거래량 자기상관
    ax = axes[0]
    ax.scatter(vol_t1, vol_t, color="#5d6d7e", alpha=0.80, s=80,
               edgecolors="white", linewidths=0.7, zorder=5)
    if len(vol_t) > 2:
        z = np.polyfit(vol_t1, vol_t, 1)
        px = np.linspace(min(vol_t1), max(vol_t1), 100)
        ax.plot(px, np.poly1d(z)(px), color="#e74c3c", lw=2, ls="--",
                alpha=0.85, label="추세선")
    ax.text(0.97, 0.97, f"r = {vol_corr:.3f}",
            transform=ax.transAxes, ha="right", va="top",
            fontsize=12, color="#e74c3c", fontweight="bold",
            bbox=dict(facecolor="white", alpha=0.85, edgecolor="lightgray", pad=4))
    ax.set_xlabel("volume_t-1 (전날 거래량)", fontsize=11)
    ax.set_ylabel("volume_t (당일 거래량)", fontsize=11)
    ax.set_title(f"거래량 자기상관\n(r = {vol_corr:.3f})", fontsize=11, fontweight="bold")
    ax.legend(fontsize=10)
    ax.set_facecolor("#f8f9fa")
    ax.grid(alpha=0.25, ls=":")

    # 오른쪽: 가격 변동성 자기상관
    ax2 = axes[1]
    ax2.scatter(ret_t1, ret_t, color="#1a6fa8", alpha=0.80, s=80,
                edgecolors="white", linewidths=0.7, zorder=5)
    if len(ret_t) > 2:
        z2 = np.polyfit(ret_t1, ret_t, 1)
        px2 = np.linspace(min(ret_t1), max(ret_t1), 100)
        ax2.plot(px2, np.poly1d(z2)(px2), color="#e74c3c", lw=2, ls="--",
                 alpha=0.85, label="추세선")
    ax2.text(0.97, 0.97, f"r = {ret_corr:.3f}",
             transform=ax2.transAxes, ha="right", va="top",
             fontsize=12, color="#e74c3c", fontweight="bold",
             bbox=dict(facecolor="white", alpha=0.85, edgecolor="lightgray", pad=4))
    ax2.set_xlabel("|수익률_t-1| (%)", fontsize=11)
    ax2.set_ylabel("|수익률_t| (%)", fontsize=11)
    ax2.set_title(f"가격 변동성 자기상관 (ARCH 효과)\n(r = {ret_corr:.3f})", fontsize=11, fontweight="bold")
    ax2.legend(fontsize=10)
    ax2.set_facecolor("#f8f9fa")
    ax2.grid(alpha=0.25, ls=":")

    fig.suptitle(
        f"거래량 & 변동성 클러스터링  —  {data['run_id']}\n"
        f"거래량 자기상관: r={vol_corr:.3f}  |  변동성 자기상관: r={ret_corr:.3f}",
        fontsize=12, fontweight="bold")
    fig.patch.set_facecolor("white")
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


# ── 차트 6: Gini 계수 + Lorenz Curve ─────────────────────────────────────

def plot_gini_lorenz(data: dict, pdf: PdfPages):
    agent_fills = data["agent_fills"]
    agent_depths = data["agent_depths"]

    # 거래금액 Gini
    turnover_val: dict[str, float] = defaultdict(float)
    # 거래 수량 Gini
    turnover_qty: dict[str, float] = defaultdict(float)
    for f in agent_fills:
        if f.get("date", "") >= ANALYSIS_START:
            uid = agent_id(f)
            qty = quantity_of(f)
            turnover_val[uid] += flt(f.get("executed_price")) * qty
            turnover_qty[uid] += qty

    if not turnover_val:
        return

    def lorenz_and_gini(d: dict) -> tuple[np.ndarray, np.ndarray, float]:
        vals = sorted(d.values())
        n = len(vals)
        total = sum(vals)
        if total == 0:
            return np.array([0, 1]), np.array([0, 1]), 0.0
        cumulative = np.cumsum(vals) / total
        x = np.linspace(0, 1, n)
        gini = 1 - 2 * np.trapezoid(cumulative, x)
        return x, cumulative, gini

    x_val, cum_val, gini_val = lorenz_and_gini(turnover_val)
    x_qty, cum_qty, gini_qty = lorenz_and_gini(turnover_qty)

    fig, axes = plt.subplots(1, 2, figsize=(14, 7))

    for ax, x_l, cum_l, gini, label in [
        (axes[0], x_val, cum_val, gini_val, "거래금액"),
        (axes[1], x_qty, cum_qty, gini_qty, "거래수량"),
    ]:
        ax.plot([0] + list(x_l), [0] + list(cum_l),
                color="#1a6fa8", lw=2.5, label="Lorenz Curve", zorder=5)
        ax.plot([0, 1], [0, 1], color="gray", lw=1.5, ls="--", alpha=0.6, label="완전 균등선")
        ax.fill_between([0] + list(x_l), [0] + list(cum_l), [0] + list(x_l),
                        alpha=0.15, color="#1a6fa8")
        ax.text(0.97, 0.04, f"Gini = {gini:.3f}",
                transform=ax.transAxes, ha="right", va="bottom",
                fontsize=13, color="#1a6fa8", fontweight="bold",
                bbox=dict(facecolor="white", alpha=0.9, edgecolor="#1a6fa8", pad=5))
        ax.set_xlabel("에이전트 누적 비율 (하위 → 상위)", fontsize=11)
        ax.set_ylabel(f"{label} 누적 비율", fontsize=11)
        ax.set_title(f"Lorenz Curve — {label} 집중도\nGini = {gini:.3f}", fontsize=11, fontweight="bold")
        ax.legend(fontsize=10)
        ax.set_facecolor("#f8f9fa")
        ax.grid(alpha=0.25, ls=":")

    values_sorted = sorted(turnover_val.values())
    n_a = len(values_sorted)
    total_v = sum(values_sorted)
    top10_share = sum(values_sorted[int(n_a * 0.9):]) / total_v * 100 if total_v else 0
    bottom50_share = sum(values_sorted[:n_a // 2]) / total_v * 100 if total_v else 0

    fig.suptitle(
        f"에이전트 간 거래 집중도  —  {data['run_id']}\n"
        f"거래금액 Gini={gini_val:.3f}  /  거래량 Gini={gini_qty:.3f}  "
        f"|  상위10% 거래비중: {top10_share:.1f}%  |  하위50% 비중: {bottom50_share:.1f}%",
        fontsize=11, fontweight="bold")
    fig.patch.set_facecolor("white")
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


# ── 메인 ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="심층 분석 보고서 생성 v2")
    parser.add_argument("--run-id", required=True, help="시뮬레이션 run_id")
    args = parser.parse_args()

    run_id = args.run_id
    print(f"[1/10] 데이터 로드 중... ({run_id})")
    data = load_data(run_id)

    # 기초 통계 계산
    all_rets = list(data["final_return"].values())
    n_profit = sum(1 for r in all_rets if r > 0)
    n_loss = sum(1 for r in all_rets if r <= 0)
    agent_fills = data["agent_fills"]
    total_fills = len(agent_fills)

    out_dir = ROOT / "outputs" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"deep_analysis_{run_id}.pdf"

    print(f"[2/10] PDF 생성 시작: {out_path}")
    with PdfPages(out_path) as pdf:
        print("[3/10] 표지 작성...")
        write_cover_page(data, pdf)

        # ── 섹션 1: Turnover vs 수익률 ──
        print("[4/10] [텍스트] 섹션 1 설명 페이지...")
        write_text_page(pdf,
            title="섹션 1  :  Turnover vs 최종 수익률 (Depth별 분석)",
            sections=[
                ("분석 목적", [
                    "에이전트의 총 거래 활동량(Turnover)과 최종 수익률 사이에 어떤 관계가 있는지 확인한다.",
                    "행동경제학의 과잉거래(overtrading) 가설(Barber & Odean, 2000): 거래를 많이 할수록 수익률이 낮아지는 경향.",
                    "정보 접근 깊이(Depth 0/1/2)에 따라 수익률 차이가 나타나는지도 동시에 분석한다.",
                ]),
                ("Depth 정의", [
                    "Depth 0: 뉴스 헤드라인만 제공. 요약 없음, 커뮤니티 접근 없음.",
                    "Depth 1: 헤드라인 + 요약본 10개 제공. 커뮤니티 읽기/쓰기 가능 (최대 5개 열람).",
                    "Depth 2: Depth 1 + 최근 7일 키워드 검색. 커뮤니티 최대 10개 열람.",
                    f"이번 실험: Depth 0 약 {sum(1 for d in data['agent_depths'].values() if d==0)}명, "
                    f"Depth 1 약 {sum(1 for d in data['agent_depths'].values() if d==1)}명, "
                    f"Depth 2 약 {sum(1 for d in data['agent_depths'].values() if d==2)}명 (balanced_depths=True로 균등 배분).",
                ]),
                ("Turnover Ratio 계산 방식", [
                    "Turnover Ratio = 총 체결 거래금액 / 초기 포트폴리오 가치.",
                    "공시가 기반 체결 로그의 매수 + 매도 거래금액을 합산.",
                    "초기 포트폴리오: 일반 투자자 1억 원, 고액 투자자 10억 원.",
                    f"분석 기간 총 체결 건수: {total_fills}건.",
                ]),
                ("해석 포인트", [
                    "scatter 좌측 하단 집중: 거래 적고 수익률도 낮음 (저정보 + 저활동).",
                    "우측 상단 집중: 활발히 거래하며 고수익 → 과잉거래 가설 반박 또는 Depth 2 효과.",
                    "Depth별 색상: Depth 2 에이전트가 더 높은 수익률을 보인다면 정보 접근이 성과에 기여하는 증거.",
                    "Violin 패널: Depth 그룹별 수익률 분포 형태 차이 (median, spread, skewness)에 주목.",
                ]),
            ],
            footnote=f"데이터 출처: exchange_fills.csv, portfolio_updates.jsonl, run_metadata.json  |  {run_id}"
        )
        print("[4b/10] 차트 1: Turnover vs 수익률 (Depth 색상)...")
        plot_turnover_pnl_depth(data, pdf)

        # ── 섹션 2: 수익률 분포 ──
        print("[5/10] [텍스트] 섹션 2 설명 페이지...")
        write_text_page(pdf,
            title="섹션 2  :  에이전트별 최종 수익률 분포 (Depth별)",
            sections=[
                ("분석 목적", [
                    "50명 에이전트의 최종 수익률이 어떻게 분포하는지, Depth 그룹별로 차이가 있는지 확인한다.",
                    f"전체 에이전트 수익 비율: {n_profit}/{len(all_rets)}명 수익, {n_loss}명 손실.",
                    f"전체 평균 수익률: {np.mean(all_rets):.2f}%  |  중앙값: {np.median(all_rets):.2f}%",
                ]),
                ("삼성전자 주가 맥락", [
                    "분석 기간 삼성전자(005930) 주가 흐름과 에이전트 포트폴리오 수익률을 비교한다.",
                    "새 거래소 구조에서는 에이전트가 호가를 제출하지 않고 공시된 시가/종가를 수용한다.",
                    "따라서 성과 차이는 가격 맞히기보다 buy/sell 방향과 수량 선택, 과잉거래 여부에서 발생한다.",
                ]),
                ("4개 패널 해석 가이드", [
                    "(좌상) 전체 수익률 막대 차트: 하위 → 상위 정렬. Depth별 색상으로 그룹 분포 확인.",
                    "(우상) Depth별 박스플롯: Q1, 중앙값, Q3, 아웃라이어. 각 Depth의 중심값(μ/m) 표시.",
                    "(좌하) Depth별 히스토그램: 0% 기준선 기준 좌우 비대칭 여부 (왜도) 확인.",
                    "(우하) 체결 건수 vs 수익률: 과잉거래 가설 검증. r이 음수이면 거래 많을수록 수익률 낮음.",
                ]),
            ],
            footnote=f"데이터 출처: portfolio_updates.jsonl, exchange_fills.csv  |  {run_id}"
        )
        print("[5b/10] 차트 2: 수익률 분포 (Depth별)...")
        plot_return_distribution_by_depth(data, pdf)

        # ── 섹션 3: 매수/매도 분포 ──
        print("[6/10] [텍스트] 섹션 3 설명 페이지...")
        write_text_page(pdf,
            title="섹션 3  :  매수/매도 의사결정 분포 & 검증 오류율",
            sections=[
                ("분석 목적", [
                    "공시가 기반 이진 매매 구조에서 날짜별 매수/매도 방향과 수량이 어떻게 분포하는지 확인한다.",
                    "에이전트는 가격을 제출하지 않으므로 호가 편차나 미체결 범위는 분석 대상이 아니다.",
                    "검증 오류율은 LLM 출력이 allowed_actions, 수량 범위, JSON 스키마를 위반한 비율을 나타낸다.",
                ]),
                ("공시가 기반 체결 규칙", [
                    "AM Turn은 공시된 시가, PM Turn은 장마감 이후 확정 종가로 즉시 체결한다.",
                    "프롬프트와 decision 검증 단계에서 유효한 action/quantity만 거래소로 전달한다.",
                    "거래소는 전달된 유효 주문을 공시가에 전량 체결하며 partial/clipping은 구현하지 않는다.",
                ]),
                ("차트 구성", [
                    "파란 막대: 날짜별 매수 체결 수량.",
                    "빨간 막대: 날짜별 매도 체결 수량(음수 방향으로 표시).",
                    "금색 선: 날짜별 종가 흐름.",
                    "보라색 선: decision validation error rate.",
                ]),
                ("읽는 법", [
                    "매수 막대가 큰 날은 에이전트 집단이 공시가에서 순매수 방향으로 기운 날이다.",
                    "매도 막대가 큰 날은 포지션 축소 또는 이익/손실 실현 성향이 강한 날이다.",
                    "검증 오류율이 높으면 프롬프트의 제약 설명이나 decision parser를 점검해야 한다.",
                ]),
            ],
            footnote="공시가 기반 이진 매매: 에이전트는 price를 제출하지 않고 buy/sell 및 quantity만 결정한다."
        )
        print("[6b/10] 차트 3: 매수/매도 분포 + 검증 오류율...")
        plot_order_fill_range(data, pdf)

        # ── 섹션 4: Disposition Effect ──
        print("[7/10] [텍스트] 섹션 4 설명 페이지...")
        write_text_page(pdf,
            title="섹션 4  :  Disposition Effect (처분 효과 분석)",
            sections=[
                ("처분 효과(Disposition Effect)란?", [
                    "행동경제학에서 투자자가 이익 포지션을 조기에 실현하고, 손실 포지션은 오래 보유하는 심리적 편향.",
                    "Shefrin & Statman (1985), Odean (1998) 등이 실제 시장에서 확인.",
                    "합리적 투자자라면 세금 최적화와 모멘텀 전략상 반대 행동(손실 조기 실현, 이익 포지션 유지)이 유리.",
                ]),
                ("LLM 에이전트에서의 처분 효과 측정", [
                    "매도 체결 발생 시 portfolio_updates.jsonl의 realized_pnl 델타 값 추출.",
                    "delta > 0: 이익 실현 매도 (avg_cost < executed_price).",
                    "delta < 0: 손실 실현 매도 (avg_cost > executed_price).",
                    "이익 실현 건수 / 손실 실현 건수 비율 → 1.0 초과이면 처분 효과 존재.",
                ]),
                ("페르소나 설계와의 연관성", [
                    "에이전트 페르소나에 bh_disposition_effect_category (high/medium/low)가 설정되어 있다.",
                    "high: 처분 효과 강함(이익 빨리 실현, 손실 오래 보유), low: 반대.",
                    "집계 결과가 페르소나 설계와 일치하는지 확인하는 것이 이 분석의 핵심.",
                    "LLM이 페르소나 지시문대로 행동했다면 이익 실현 > 손실 실현이 나타나야 한다.",
                ]),
            ],
            footnote="portfolio_updates.jsonl의 realized_pnl 필드 변화량으로 계산."
        )
        print("[7b/10] 차트 4: Disposition Effect...")
        plot_disposition_effect(data, pdf)

        # ── 섹션 5: 클러스터링 ──
        print("[8/10] [텍스트] 섹션 5 설명 페이지...")
        write_text_page(pdf,
            title="섹션 5  :  거래량 & 변동성 클러스터링",
            sections=[
                ("분석 목적", [
                    "실제 금융시장의 '정형화된 사실(Stylized Facts)' 중 하나인 변동성 클러스터링이 이 시뮬레이션에서도 나타나는지 확인.",
                    "변동성 클러스터링: 큰 가격 변동이 큰 가격 변동을 낳는 현상 (ARCH/GARCH 효과).",
                    "거래량 클러스터링: 거래량 많은 날 다음날에도 거래량이 많은 경향.",
                ]),
                ("지표 계산", [
                    "거래량 자기상관: Pearson r(volume_t-1, volume_t). 양수이면 클러스터링 존재.",
                    "변동성 자기상관: Pearson r(|ret_t-1|, |ret_t|). 양수이면 ARCH 효과 존재.",
                    "데이터: daily_exchange_summary.csv의 volume과 close_price/announced_price 사용.",
                ]),
                ("해석 가이드", [
                    "r > 0.3: 명확한 클러스터링 존재. 실제 시장과 유사한 패턴.",
                    "r ≈ 0: 무작위적 거래. 에이전트들이 독립적으로 행동.",
                    "r < 0: 반전(mean-reversion). 드문 패턴.",
                    "LLM 에이전트 시뮬레이션에서 클러스터링이 나타난다면, 에이전트들이 동일 뉴스에 집단적으로 반응하는 증거.",
                ]),
            ],
            footnote="daily_exchange_summary.csv 기준 분석. 분석 기간: " + ANALYSIS_START + " 이후."
        )
        print("[8b/10] 차트 5: 거래량 클러스터링...")
        plot_volume_clustering(data, pdf)

        # ── 섹션 6: Gini ──
        print("[9/10] [텍스트] 섹션 6 설명 페이지...")
        write_text_page(pdf,
            title="섹션 6  :  에이전트 간 거래 집중도 (Gini & Lorenz)",
            sections=[
                ("분석 목적", [
                    "50명 에이전트 중 일부가 거래를 독점하는지, 아니면 거래량이 고르게 분산되어 있는지 측정.",
                    "Gini 계수: 0(완전 평등) ~ 1(완전 독점). 실제 주식시장 개인 투자자 거래 Gini 약 0.7~0.9.",
                    "높은 Gini는 소수 에이전트가 체결을 독점 → 집단적 순매수 패턴이 그들에 의해 주도됨을 의미.",
                ]),
                ("거래 집중도가 발생하는 구조적 이유", [
                    "에이전트마다 Depth가 다름 → Depth 2 에이전트가 더 많은 정보를 바탕으로 방향/수량을 결정.",
                    "고액 에이전트(초기 자산 10억)는 절대 거래금액 자체가 크므로 금액 Gini에서 불리하게 작용.",
                    "decision_space=buy_sell_only: 모든 에이전트가 반드시 매수 또는 매도해야 하므로 hold 없음.",
                    "체결 수량: 공시가 기반 전량 체결 구조에서는 유효 주문의 수량 차이가 거래 집중도를 만든다.",
                ]),
                ("Lorenz Curve 읽는 법", [
                    "X축: 에이전트 누적 비율 (하위 0% → 상위 100%).",
                    "Y축: 해당 구간까지의 누적 거래금액 비율.",
                    "대각선(완전 평등선)으로부터 Lorenz Curve가 멀수록 불평등도 높음.",
                    "파란 음영 면적 × 2 = Gini 계수.",
                ]),
            ],
            footnote="분석 기간: " + ANALYSIS_START + " 이후. 거래금액(원) 기준과 거래수량(주) 기준 각각 계산."
        )
        print("[10/10] 차트 6: Gini + Lorenz Curve...")
        plot_gini_lorenz(data, pdf)

        d = pdf.infodict()
        d["Title"] = f"Deep Analysis Report v2 — {run_id}"
        d["Author"] = "TwinMarket Simulation System"
        d["Subject"] = "LLM 에이전트 주식 시장 시뮬레이션 심층 분석 (Depth별 수익률, 텍스트 분석 포함)"

    print(f"\n완료: {out_path}")
    print(f"페이지 구성: 표지 + (텍스트+차트) × 6 섹션 = 총 13페이지")


if __name__ == "__main__":
    main()
