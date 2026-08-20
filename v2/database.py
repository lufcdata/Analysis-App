"""DuckDB connection helpers for the LUFCDATA V2 API."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "football.duckdb"


def connect(db_path: str | Path = DEFAULT_DB_PATH, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    path = Path(db_path)
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


@contextmanager
def connection(db_path: str | Path = DEFAULT_DB_PATH, read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    conn = connect(db_path, read_only=read_only)
    try:
        yield conn
    finally:
        conn.close()
