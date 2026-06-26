from __future__ import annotations

import sqlite3
from pathlib import Path

from twinmarket_kr.db.schema import create_agents_table_sql, create_sim_tables_sql


def connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_sim_db(db_path: Path | str) -> None:
    with connect(db_path) as conn:
        for ddl in create_sim_tables_sql():
            conn.execute(ddl)
        conn.commit()


def init_agents_db(db_path: Path | str) -> None:
    with connect(db_path) as conn:
        conn.execute("DROP TABLE IF EXISTS agents")
        conn.execute(create_agents_table_sql())
        conn.commit()
