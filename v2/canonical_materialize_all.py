"""Populate every available match into the versioned Metrics Bible stores."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical_materialize import materialize_match
from .database import DEFAULT_DB_PATH, connection
from .metric_registry import METRIC_SET_VERSION


def materialize_all(db_path: str | Path = DEFAULT_DB_PATH, *, force: bool = False) -> dict[str, Any]:
    db_path = Path(db_path)
    with connection(db_path, read_only=True) as conn:
        existing = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        if "match_events" not in existing:
            raise ValueError("Production DuckDB has no match_events table; canonical materialisation cannot proceed")
        match_ids = [
            str(row[0])
            for row in conn.execute(
                """
                SELECT DISTINCT match_id
                FROM match_events
                WHERE lower(source)='whoscored' AND event_type='raw_whoscored'
                  AND period IN ('FirstHalf','SecondHalf')
                ORDER BY match_id
                """
            ).fetchall()
        ]

    reports = []
    failures = []
    for match_id in match_ids:
        try:
            reports.append(materialize_match(db_path, match_id, force=force))
        except Exception as exc:
            failures.append({"match_id": match_id, "error": str(exc)})

    if failures:
        preview = "; ".join(f"{row['match_id']}: {row['error']}" for row in failures[:5])
        raise RuntimeError(
            f"Canonical Metrics Bible materialisation failed for {len(failures)} of {len(match_ids)} matches: {preview}"
        )

    return {
        "metric_set_version": METRIC_SET_VERSION,
        "matches_discovered": len(match_ids),
        "matches_materialised": sum(1 for row in reports if row.get("status") == "materialised"),
        "matches_already_materialised": sum(1 for row in reports if row.get("status") == "already_materialised"),
    }
