"""Canonical production-readiness checks for the Metrics Bible stores.

Readiness is a database property, not a frontend inference. A season/range
leaderboard must never silently represent only the subset of matches that happened
to be materialised by Match Report requests.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical_materialize import _table_columns
from .database import DEFAULT_DB_PATH, connection
from .metric_registry import METRIC_SET_VERSION

RAW_REQUIRED_COLUMNS = {"match_id", "source", "event_type", "metadata_json", "event_id"}


def canonical_readiness(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Describe raw-source and canonical-store coverage without fabricating data."""
    db_path = Path(db_path)
    result: dict[str, Any] = {
        "metric_set_version": METRIC_SET_VERSION,
        "db_available": db_path.exists(),
        "raw_schema_ready": False,
        "raw_matches": 0,
        "canonical_team_matches": 0,
        "canonical_player_matches": 0,
        "canonical_exposure_matches": 0,
        "canonical_complete_matches": 0,
        "coverage_percent": 0.0,
        "missing_raw_columns": [],
        "missing_canonical_matches": [],
        "ready": False,
    }
    if not db_path.exists():
        return result

    with connection(db_path, read_only=True) as conn:
        tables = {str(row[0]) for row in conn.execute("SHOW TABLES").fetchall()}
        if "match_events" not in tables:
            result["missing_raw_columns"] = sorted(RAW_REQUIRED_COLUMNS)
            return result

        columns = _table_columns(conn, "match_events")
        missing = sorted(RAW_REQUIRED_COLUMNS - columns)
        result["missing_raw_columns"] = missing
        result["raw_schema_ready"] = not missing
        if missing:
            return result

        raw_ids = {
            str(row[0])
            for row in conn.execute(
                """
                SELECT DISTINCT match_id
                FROM match_events
                WHERE lower(source)='whoscored' AND event_type='raw_whoscored'
                """
            ).fetchall()
        }
        result["raw_matches"] = len(raw_ids)

        def materialised_ids(table: str, extra_where: str = "", params: list[object] | None = None) -> set[str]:
            if table not in tables:
                return set()
            rows = conn.execute(
                f"SELECT DISTINCT match_id FROM {table} WHERE metric_set_version=? {extra_where}",
                [METRIC_SET_VERSION, *(params or [])],
            ).fetchall()
            return {str(row[0]) for row in rows}

        team_ids = materialised_ids("canonical_metric_values", "AND scope='team'")
        player_ids = materialised_ids("canonical_metric_values", "AND scope='player'")
        exposure_ids = materialised_ids("canonical_player_exposure")
        complete_ids = raw_ids & team_ids & player_ids & exposure_ids
        missing_ids = sorted(raw_ids - complete_ids)

        result.update({
            "canonical_team_matches": len(team_ids & raw_ids),
            "canonical_player_matches": len(player_ids & raw_ids),
            "canonical_exposure_matches": len(exposure_ids & raw_ids),
            "canonical_complete_matches": len(complete_ids),
            "coverage_percent": round((len(complete_ids) / len(raw_ids) * 100.0), 2) if raw_ids else 0.0,
            "missing_canonical_matches": missing_ids,
            "ready": bool(raw_ids) and not missing_ids,
        })
        return result


def assert_canonical_ready(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Fail closed unless every raw match has team/player/exposure canonical data."""
    readiness = canonical_readiness(db_path)
    if not readiness["raw_schema_ready"]:
        missing = ", ".join(readiness["missing_raw_columns"]) or "unknown raw-source defect"
        raise RuntimeError(f"Canonical source schema is not ready: {missing}")
    if readiness["raw_matches"] <= 0:
        raise RuntimeError("No full-fidelity raw WhoScored matches are available")
    if not readiness["ready"]:
        missing = readiness["missing_canonical_matches"]
        preview = ", ".join(missing[:10])
        suffix = "..." if len(missing) > 10 else ""
        raise RuntimeError(
            f"Canonical database coverage is incomplete: {readiness['canonical_complete_matches']}/"
            f"{readiness['raw_matches']} matches ({readiness['coverage_percent']}%); missing {preview}{suffix}"
        )
    return readiness
