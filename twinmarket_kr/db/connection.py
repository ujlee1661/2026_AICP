from __future__ import annotations

import sqlite3
from pathlib import Path

from twinmarket_kr.db.schema import create_agents_table_sql, create_sim_tables_sql


class ManagedConnection(sqlite3.Connection):
    """A sqlite connection whose context manager also releases the file handle."""

    def __exit__(self, exc_type, exc_value, traceback):  # type: ignore[no-untyped-def]
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect(db_path: Path | str, *, read_only: bool = False) -> sqlite3.Connection:
    path = Path(db_path)
    if read_only:
        if not path.exists():
            raise FileNotFoundError(f"SQLite database not found: {path}")
        # sys_100.db is shared reference data. Never acquire a write journal for it.
        target: str | Path = f"file:{path.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(
            target,
            uri=True,
            timeout=30.0,
            check_same_thread=False,
            factory=ManagedConnection,
        )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=30.0, check_same_thread=False, factory=ManagedConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if read_only:
        conn.execute("PRAGMA query_only = ON")
    else:
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
