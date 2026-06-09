#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config
from twinmarket_kr.persona.select import load_pool, match_agents, save_sys_100, verify_distribution
from twinmarket_kr.persona.slots import load_fixed_slots


def main() -> None:
    config.ensure_directories()
    slots = load_fixed_slots(config.FIXED_SLOTS_CSV)
    pool = load_pool()
    agents = match_agents(pool, slots)
    save_sys_100(agents, config.SYS_100_DB)
    report = verify_distribution(agents)
    report_path = config.OUTPUT_DIR / "persona_validation_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved: {config.SYS_100_DB}")
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
