#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

import config


PRIVATE_FIELDS = [
    "is_fake",
    "fake_news_id",
    "synthetic_id",
    "related_event_id",
    "linked_event_id",
    "linked_event_ids",
    "linked_event_offsets",
    "related_event",
    "related_events",
    "related_event_type",
    "misinformation_type",
    "misinformation_type_label",
    "false_information_class",
    "injection_phase",
    "injection_offset",
    "injection_window_policy",
    "time_slot",
    "feed_slot",
    "risk_level",
    "misinformation_risk_score",
    "claim_pattern",
    "false_claim",
    "correct_fact",
    "distortion_strategy",
    "target_effect",
    "why_false_or_misleading",
    "detection_clues",
    "replace_target_news_id",
    "replace_target_title",
    "replace_target_category",
    "replace_target_time",
    "replace_target_time_slot",
    "replace_target_feed_slot",
    "replace_target_feed_position",
    "replace_target_timestamp",
    "baseline_news_count",
    "real_news_count_after_replacement",
    "fake_news_count",
    "baseline_feed_source",
    "information_cutoff_date",
    "information_cutoff_timestamp",
    "event_date",
    "event_timestamp",
    "event_predictability",
    "event_timestamp_after_target",
    "leakage_safe",
    "data_leakage_control",
    "can_use_event_outcome",
    "uses_future_event_details",
    "source_generation_method",
    "agent_visible_label_removed",
    "generated_by",
    "prompt_version",
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def _write_csv(path: Path, rows: list[dict[str, Any]], preferred_fields: list[str]) -> None:
    fieldnames = [field for field in preferred_fields if any(field in row for row in rows)]
    extras = sorted({key for row in rows for key in row.keys()} - set(fieldnames))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[*fieldnames, *extras])
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in writer.fieldnames or []})


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return str(value).strip()


def _bool_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = _clean(value).lower()
    return "true" if text in {"1", "true", "yes", "y"} else "false"


def _category(row: dict[str, Any]) -> str:
    raw = _clean(row.get("replace_target_category") or row.get("category"))
    if raw in {"종목", "섹터", "경제"}:
        return raw
    return "종목"


def _public_news_id(row: dict[str, Any]) -> str:
    synthetic_id = _clean(row.get("fake_news_id") or row.get("synthetic_id"))
    day = _clean(row.get("date")).replace("-", "")
    category = _category(row)
    digest = hashlib.sha1(synthetic_id.encode("utf-8")).hexdigest()[:8]
    return f"news_{day}_{category}_{digest}"


def _fake_rows(fake_pkl_path: Path, *, approved_only: bool = True) -> list[dict[str, Any]]:
    df = pd.read_pickle(fake_pkl_path)
    rows = df.to_dict("records")
    result: list[dict[str, Any]] = []
    for raw in rows:
        if approved_only:
            final_approval = raw.get("final_approval", True)
            leakage_safe = raw.get("leakage_safe", raw.get("agent_visible_label_removed", True))
            if bool(final_approval) is not True:
                continue
            if bool(leakage_safe) is not True:
                continue
        date = _clean(raw.get("date"))
        title = _clean(raw.get("title"))
        daily_summary = _clean(raw.get("content") or raw.get("summary"))
        search_summary = _clean(raw.get("summary") or daily_summary)
        time_text = _clean(raw.get("time"))
        replace_target_news_id = _clean(raw.get("replace_target_news_id"))
        if not date or not title or not daily_summary or not time_text or not replace_target_news_id:
            continue
        row: dict[str, Any] = {
            "id": _public_news_id(raw),
            "title": title,
            "date": date,
            "time": time_text[:5],
            "category": _category(raw),
            "summary": daily_summary,
            "is_fake": "true",
            "synthetic_id": _clean(raw.get("synthetic_id") or raw.get("fake_news_id")),
            "fake_news_id": _clean(raw.get("fake_news_id") or raw.get("synthetic_id")),
            "replace_target_news_id": replace_target_news_id,
        }
        if search_summary and search_summary != daily_summary:
            row["search_summary"] = search_summary
        for field in PRIVATE_FIELDS:
            if field in {"is_fake", "synthetic_id", "fake_news_id", "replace_target_news_id"}:
                continue
            value = raw.get(field)
            if isinstance(value, (list, tuple, set)):
                row[field] = json.dumps(list(value), ensure_ascii=False)
            elif isinstance(value, bool):
                row[field] = _bool_text(value)
            else:
                row[field] = _clean(value)
        result.append(row)
    return result


def _replace_daily_rows(
    daily_rows: list[dict[str, Any]],
    fake_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    fake_by_target = {row["replace_target_news_id"]: row for row in fake_rows}
    replaced_targets: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in daily_rows:
        target_id = _clean(row.get("id"))
        fake = fake_by_target.get(target_id)
        if not fake:
            result.append(row)
            continue
        replaced_targets.add(target_id)
        result.append(
            {
                key: fake.get(key, "")
                for key in [
                    "id",
                    "title",
                    "date",
                    "time",
                    "category",
                    *PRIVATE_FIELDS,
                ]
                if key != "summary"
            }
        )
    missing_targets = sorted(set(fake_by_target) - replaced_targets)
    if missing_targets:
        raise ValueError(f"replace_target_news_id not found in daily csv: {missing_targets[:5]}")
    return result


def _event_manifest(event_pkl_path: Path | None) -> dict[str, Any]:
    if event_pkl_path is None or not event_pkl_path.exists():
        return {}
    df = pd.read_pickle(event_pkl_path)
    keep = [
        "event_id",
        "event_date",
        "event_title",
        "event_type",
        "impact_direction",
        "injection_dates",
        "injection_start_date",
        "injection_end_date",
    ]
    rows = []
    for row in df.to_dict("records"):
        item = {}
        for field in keep:
            value = row.get(field)
            if isinstance(value, (list, tuple, set)):
                item[field] = list(value)
            else:
                item[field] = _clean(value)
        rows.append(item)
    return {"event_count": len(rows), "events": rows}


def prepare_fake_news_injection(
    *,
    processed_csv_path: Path,
    daily_csv_path: Path,
    fake_pkl_path: Path,
    event_pkl_path: Path | None,
    output_processed_csv_path: Path,
    output_daily_csv_path: Path,
    manifest_path: Path,
    approved_only: bool = True,
) -> dict[str, Any]:
    processed = _read_csv(processed_csv_path)
    daily = _read_csv(daily_csv_path)
    fake_rows = _fake_rows(fake_pkl_path, approved_only=approved_only)

    existing_ids = {row.get("id", "") for row in processed}
    duplicate_ids = [row["id"] for row in fake_rows if row["id"] in existing_ids]
    if duplicate_ids:
        raise ValueError(f"fake public ids collide with existing news ids: {duplicate_ids[:5]}")

    processed_out = [*processed, *fake_rows]
    daily_out = _replace_daily_rows(daily, fake_rows)

    _write_csv(
        output_processed_csv_path,
        processed_out,
        ["id", "title", "date", "time", "category", "summary", "search_summary", *PRIVATE_FIELDS],
    )
    _write_csv(
        output_daily_csv_path,
        daily_out,
        ["id", "title", "date", "time", "category", *PRIVATE_FIELDS],
    )

    manifest = {
        "processed_csv": str(output_processed_csv_path),
        "daily_csv": str(output_daily_csv_path),
        "baseline_processed_csv": str(processed_csv_path),
        "baseline_daily_csv": str(daily_csv_path),
        "fake_pkl": str(fake_pkl_path),
        "event_pkl": str(event_pkl_path) if event_pkl_path else "",
        "baseline_processed_count": len(processed),
        "baseline_daily_count": len(daily),
        "fake_count": len(fake_rows),
        "processed_count": len(processed_out),
        "daily_count": len(daily_out),
        "replacement_mode": "replace_target_news_id",
        "fake_by_date": {},
        "events": _event_manifest(event_pkl_path),
    }
    for row in fake_rows:
        manifest["fake_by_date"].setdefault(row["date"], []).append(
            {
                "id": row["id"],
                "synthetic_id": row.get("synthetic_id", ""),
                "time": row.get("time", ""),
                "category": row.get("category", ""),
                "linked_event_id": row.get("linked_event_id", ""),
                "related_event": row.get("related_event", ""),
                "misinformation_type": row.get("misinformation_type", ""),
            }
        )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build injection news CSVs from fake news pkl.")
    parser.add_argument("--processed-csv", type=Path, default=config.PROCESSED_NEWS_CSV)
    parser.add_argument("--daily-csv", type=Path, default=config.DAILY_NEWS_SELECTION_CSV)
    parser.add_argument("--fake-pkl", type=Path, default=config.FAKE_NEWS_PKL)
    parser.add_argument("--event-pkl", type=Path, default=config.EVENT_PKL)
    parser.add_argument("--output-processed-csv", type=Path, default=config.PROCESSED_NEWS_INJECTION_CSV)
    parser.add_argument("--output-daily-csv", type=Path, default=config.DAILY_NEWS_SELECTION_INJECTION_CSV)
    parser.add_argument("--manifest", type=Path, default=config.OUTPUT_DIR / "fake_news_injection_manifest.json")
    parser.add_argument("--include-unapproved", action="store_true")
    args = parser.parse_args()

    manifest = prepare_fake_news_injection(
        processed_csv_path=args.processed_csv,
        daily_csv_path=args.daily_csv,
        fake_pkl_path=args.fake_pkl,
        event_pkl_path=args.event_pkl,
        output_processed_csv_path=args.output_processed_csv,
        output_daily_csv_path=args.output_daily_csv,
        manifest_path=args.manifest,
        approved_only=not args.include_unapproved,
    )
    print(json.dumps({k: v for k, v in manifest.items() if k != "fake_by_date" and k != "events"}, ensure_ascii=False, indent=2))
    print(f"manifest={args.manifest}")


if __name__ == "__main__":
    main()
