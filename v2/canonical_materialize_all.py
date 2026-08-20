"""Populate every available raw WhoScored match into the Metrics Bible stores.

This runner is intentionally separate from Render web-service bootstrap. It is the
full-database preparation path used to make season/date-range leaderboard data
complete without making normal API startup or requests perform season-scale work.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical_materialize import _table_columns, materialize_match
from .database import DEFAULT_DB_PATH, connection
from .metric_registry import METRIC_SET_VERSION


RAW_DISCOVERY_COLUMNS = {"match_id", "source", "event_type", "metadata_json", "event_id"}


def discover_raw_match_ids(db_path: str | Path = DEFAULT_DB_PATH) -> list[str]:
    """Return matches backed by the full-fidelity WhoScored source contract.

    Do not filter on derivative columns such as ``period``. Historical production
    snapshots can encode period labels differently, while ``materialize_match``
    already normalises period values from the original metadata JSON. Keeping the
    discovery boundary aligned with that loader prevents valid raw matches from
    disappearing before the Metrics Bible engine sees them.
    """
    db_path = Path(db_path)
    with connection(db_path, read_only=True) as conn:
        existing = {str(row[0]) for row in conn.execute("SHOW TABLES").fetchall()}
        if "match_events" not in existing:
            raise ValueError("Production DuckDB has no match_events table; canonical materialisation cannot proceed")

        columns = _table_columns(conn, "match_events")
        missing = sorted(RAW_DISCOVERY_COLUMNS - columns)
        if missing:
            raise ValueError(
                "match_events is not full-fidelity WhoScored-ready; missing columns: "
                + ", ".join(missing)
            )

        return [
            str(row[0])
            for row in conn.execute(
                """
                SELECT DISTINCT match_id
                FROM match_events
                WHERE lower(source)='whoscored' AND event_type='raw_whoscored'
                ORDER BY match_id
                """
            ).fetchall()
        ]


def materialize_all(db_path: str | Path = DEFAULT_DB_PATH, *, force: bool = False) -> dict[str, Any]:
    db_path = Path(db_path)
    match_ids = discover_raw_match_ids(db_path)
    if not match_ids:
        raise ValueError(
            "No full-fidelity raw WhoScored matches were discovered; refusing to build an empty canonical leaderboard store"
        )

    reports = []
    failures = []
    for match_id in match_ids:
        try:
            reports.append(materialize_match(db_path, match_id, force=force))
        except Exception as exc:
            failures.append({"match_id": match_id, "error": f"{type(exc).__name__}: {exc}"})

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
        "failures": 0,
    }
