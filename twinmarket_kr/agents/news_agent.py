from __future__ import annotations

import csv
import pickle
import random
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import config


STOCK_KEYWORDS = ("삼성전자", "005930", "갤럭시", "DS부문", "파운드리", "HBM", "메모리", "반도체")
SECTOR_KEYWORDS = ("반도체", "HBM", "메모리", "파운드리", "AI 반도체", "2나노", "장비", "낸드", "DRAM")
ECONOMY_KEYWORDS = ("금리", "환율", "수출", "물가", "경기", "정책", "원달러", "외국인", "코스피", "미국")
CATEGORY_TARGETS = {"종목": 5, "섹터": 3, "경제": 2}
DEFAULT_DEPTH2_FIELDS = (
    {"field": "HBM", "keywords": ["HBM", "메모리", "고대역폭"]},
    {"field": "파운드리", "keywords": ["파운드리", "2나노", "수주"]},
    {"field": "반도체 업황", "keywords": ["반도체", "업황", "수출", "장비"]},
    {"field": "거시 수급", "keywords": ["금리", "환율", "외국인", "코스피"]},
)


def _select_daily(rows: list[dict[str, Any]], *, seed: int | None = None) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for category, target in CATEGORY_TARGETS.items():
        pool = [row for row in rows if row["category"] == category and row["id"] not in used_ids]
        picks = rng.sample(pool, min(target, len(pool)))
        selected.extend(picks)
        used_ids.update(row["id"] for row in picks)
    if len(selected) < sum(CATEGORY_TARGETS.values()):
        remains = [row for row in rows if row["id"] not in used_ids]
        selected.extend(rng.sample(remains, min(sum(CATEGORY_TARGETS.values()) - len(selected), len(remains))))
    return selected


def _parse_date(value: str) -> date:
    text = str(value).strip()[:10]
    return datetime.strptime(text, "%Y-%m-%d").date()


def _normalize_category(raw: str | None, title: str, summary: str) -> str:
    text = f"{raw or ''} {title} {summary}"
    if raw in {"종목", "stock"}:
        return "종목"
    if raw in {"섹터", "산업", "industry", "sector"}:
        return "섹터"
    if raw in {"경제", "economy", "macro"}:
        return "경제"
    if any(keyword in text for keyword in STOCK_KEYWORDS[:4]):
        return "종목"
    if any(keyword in text for keyword in SECTOR_KEYWORDS):
        return "섹터"
    return "경제"


def _summarize(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _importance(title: str, summary: str, category: str, time_text: str) -> float:
    text = f"{title} {summary}"
    score = 0.0
    score += sum(text.count(keyword) for keyword in STOCK_KEYWORDS) * 3
    score += sum(text.count(keyword) for keyword in SECTOR_KEYWORDS) * 2
    score += sum(text.count(keyword) for keyword in ECONOMY_KEYWORDS)
    score += {"종목": 2.0, "섹터": 1.0, "경제": 0.5}.get(category, 0)
    if any(token in title for token in ("속보", "급등", "급락", "최대", "실적", "수주")):
        score += 2
    if time_text:
        try:
            hour = int(time_text[:2])
            score += max(0, 16 - hour) / 20
        except ValueError:
            pass
    return score


def _raw_records(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        for key in ("records", "news", "data", "items"):
            if isinstance(raw.get(key), list):
                return [dict(item) for item in raw[key] if isinstance(item, dict)]
        return [dict(value) for value in raw.values() if isinstance(value, dict)]
    if hasattr(raw, "to_dict") and hasattr(raw, "columns"):
        return [dict(item) for item in raw.to_dict("records")]
    raise TypeError(f"unsupported raw news format: {type(raw)!r}")


def prepare_news(
    raw_pkl_path: Path | str = config.SAMSUNG_NEWS_RAW_PKL,
    processed_csv_path: Path | str = config.PROCESSED_NEWS_CSV,
    daily_csv_path: Path | str = config.DAILY_NEWS_SELECTION_CSV,
    *,
    daily_seed: int | None = None,
) -> tuple[int, int]:
    raw_path = Path(raw_pkl_path)
    if not raw_path.exists():
        raise FileNotFoundError(f"raw news pkl not found: {raw_path}")
    with raw_path.open("rb") as f:
        raw = pickle.load(f)

    seen: set[tuple[str, str]] = set()
    processed: list[dict[str, Any]] = []
    per_day_counter: dict[str, int] = defaultdict(int)
    for item in _raw_records(raw):
        title = str(item.get("title") or item.get("headline") or "").strip()
        if not title:
            continue
        date_text = str(item.get("date") or item.get("published_date") or item.get("datetime") or "")[:10]
        if not date_text:
            continue
        key = (date_text, title)
        if key in seen:
            continue
        seen.add(key)
        raw_time = str(item.get("time") or item.get("published_time") or item.get("datetime") or "")
        time_match = re.search(r"\d{2}:\d{2}", raw_time)
        time_text = time_match.group(0) if time_match else ""
        content = item.get("summary") or item.get("content") or item.get("body") or ""
        summary = _summarize(str(content))
        category = _normalize_category(str(item.get("category") or item.get("type") or ""), title, summary)
        per_day_counter[date_text] += 1
        news_id = f"news_{date_text.replace('-', '')}_{category}_{per_day_counter[date_text]:04d}"
        processed.append(
            {
                "id": news_id,
                "title": title,
                "date": date_text,
                "time": time_text,
                "category": category,
                "summary": summary,
                "importance": _importance(title, summary, category, time_text),
            }
        )

    processed.sort(key=lambda row: (row["date"], -row["importance"], row["time"], row["id"]))
    processed_path = Path(processed_csv_path)
    daily_path = Path(daily_csv_path)
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    with processed_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "title", "date", "time", "category", "summary"])
        writer.writeheader()
        for row in processed:
            writer.writerow({key: row[key] for key in writer.fieldnames or []})

    selected = []
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in processed:
        by_day[row["date"]].append(row)
    for day_index, (_, rows) in enumerate(sorted(by_day.items())):
        seed = None if daily_seed is None else daily_seed + day_index
        selected.extend(_select_daily(rows, seed=seed))

    with daily_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "title", "date", "time", "category"])
        writer.writeheader()
        for row in selected:
            writer.writerow({key: row[key] for key in writer.fieldnames or []})
    return len(processed), len(selected)


class NewsAgent:
    def __init__(
        self,
        processed_csv_path: Path | str = config.PROCESSED_NEWS_CSV,
        daily_csv_path: Path | str = config.DAILY_NEWS_SELECTION_CSV,
    ) -> None:
        self.processed_csv_path = Path(processed_csv_path)
        self.daily_csv_path = Path(daily_csv_path)
        self._processed = self._load_csv(self.processed_csv_path)
        self._daily = self._load_csv(self.daily_csv_path)
        self._by_id = {row["id"]: row for row in self._processed}
        self._by_title = {row["title"]: row for row in self._processed}

    def get_daily_titles(self, target_date: str) -> list[dict[str, str]]:
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "date": row["date"],
                "type": row.get("category", ""),
            }
            for row in self._daily
            if row.get("date") == target_date
        ]

    def read_news(
        self,
        *,
        ids: list[str] | None = None,
        titles: list[str] | None = None,
        allowed_ids: set[str] | None = None,
        max_items: int | None = None,
    ) -> list[dict[str, str]]:
        rows = []
        for news_id in ids or []:
            row = self._by_id.get(news_id)
            if row:
                rows.append(row)
        for title in titles or []:
            row = self._by_title.get(title)
            if row:
                rows.append(row)
        deduped = []
        seen = set()
        for row in rows:
            if row["id"] in seen:
                continue
            if allowed_ids is not None and row["id"] not in allowed_ids:
                continue
            deduped.append(row)
            seen.add(row["id"])
            if max_items is not None and len(deduped) >= max_items:
                break
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "date": row["date"],
                "content": row.get("summary", ""),
                "type": row.get("category", ""),
            }
            for row in deduped
        ]

    def search_news(
        self,
        *,
        fields: list[dict[str, Any]],
        current_date: str,
        max_fields: int = 4,
        max_per_field: int = 5,
        lookback_days: int = 7,
    ) -> dict[str, list[dict[str, str]]]:
        end = _parse_date(current_date)
        start = end - timedelta(days=lookback_days - 1)
        candidates = [
            row for row in self._processed if start <= _parse_date(row["date"]) <= end
        ]
        result: dict[str, list[dict[str, str]]] = {}
        for field in fields[:max_fields]:
            field_name = str(field.get("field", "")).strip() or "unknown"
            keywords = [str(keyword).strip() for keyword in field.get("keywords", []) if str(keyword).strip()]
            scored = []
            for row in candidates:
                haystack = f"{row['title']} {row.get('summary', '')}"
                score = sum(haystack.count(keyword) for keyword in keywords)
                if score > 0:
                    scored.append((score, row))
            scored.sort(key=lambda item: (-item[0], item[1]["date"], item[1]["title"]))
            result[field_name] = [
                {"id": row["id"], "title": row["title"], "date": row["date"], "type": row["category"]}
                for _, row in scored[:max_per_field]
            ]
        return result

    def search_news_flat(
        self,
        *,
        keywords: list[str],
        current_date: str,
        lookback_days: int = 7,
        top_n: int = 10,
    ) -> list[dict[str, Any]]:
        normalized_keywords = [str(keyword).strip() for keyword in keywords if str(keyword).strip()]
        if not normalized_keywords:
            return []
        end = _parse_date(current_date)
        start = end - timedelta(days=lookback_days - 1)
        candidates = [
            row for row in self._processed if start <= _parse_date(row["date"]) <= end
        ]
        scored: list[tuple[float, dict[str, str]]] = []
        for row in candidates:
            haystack = f"{row['title']} {row.get('summary', '')}"
            title_hits = sum(str(row["title"]).count(keyword) for keyword in normalized_keywords)
            body_hits = sum(str(row.get("summary", "")).count(keyword) for keyword in normalized_keywords)
            score = title_hits * 2.0 + body_hits
            if score > 0:
                scored.append((score, row))
        seen_ids = {row["id"] for _, row in scored}
        if len(scored) < top_n:
            for row in candidates:
                if row["id"] not in seen_ids:
                    scored.append((0.0, row))
                    seen_ids.add(row["id"])
        scored.sort(key=lambda item: (-item[0], -_parse_date(item[1]["date"]).toordinal(), item[1]["title"]))
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "date": row["date"],
                "category": row.get("category", ""),
                "summary": row.get("summary", ""),
                "relevance_score": score,
            }
            for score, row in scored[:top_n]
        ]

    def build_base_context(self, target_date: str, news_depth: int = 1) -> dict[str, Any]:
        return {
            "news_depth": news_depth,
            "daily_titles": self.get_daily_titles(target_date),
            "read_contents": [],
            "search_results": {},
            "search_read_contents": [],
            "limits": {
                "daily_read_max": 0 if news_depth <= 0 else 10,
                "search_fields_max": 0,
                "search_read_max": 10 if news_depth >= 2 else 0,
                "lookback_days": 7 if news_depth >= 2 else 0,
            },
        }

    def expand_context_from_selection(
        self,
        *,
        base_context: dict[str, Any],
        selected_news: list[Any] | None = None,
        current_date: str,
    ) -> dict[str, Any]:
        news_depth = 1 if base_context.get("news_depth") is None else int(base_context["news_depth"])
        daily_titles = base_context.get("daily_titles") or []
        allowed_daily_ids = {str(row.get("id")) for row in daily_titles if row.get("id")}
        if news_depth <= 0:
            read_contents: list[dict[str, str]] = []
        else:
            read_contents = self.read_news(
                ids=[str(row.get("id")) for row in daily_titles if row.get("id")],
                allowed_ids=allowed_daily_ids,
                max_items=10,
            )

        expanded = dict(base_context)
        expanded["read_contents"] = read_contents
        expanded.setdefault("search_results", {})
        expanded.setdefault("search_read_contents", [])
        return expanded

    @staticmethod
    def _normalize_selected_news(selected_news: list[Any]) -> tuple[list[str], list[str]]:
        ids: list[str] = []
        titles: list[str] = []
        for item in selected_news[:3]:
            if isinstance(item, dict):
                raw_id = item.get("id")
                raw_title = item.get("title")
                if raw_id:
                    ids.append(str(raw_id))
                if raw_title:
                    titles.append(str(raw_title))
            else:
                text = str(item).strip()
                if not text:
                    continue
                if text.startswith("news_"):
                    ids.append(text)
                else:
                    titles.append(text)
        return ids, titles

    @staticmethod
    def _load_csv(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open(encoding="utf-8-sig", newline="") as f:
            return [dict(row) for row in csv.DictReader(f)]
