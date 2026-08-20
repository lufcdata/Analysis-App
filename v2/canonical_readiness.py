"""Canonical production-readiness checks for the Metrics Bible stores.

Readiness is a database property, not a frontend inference. A season/range
leaderboard must never silently represent only the subset of matches that happened
to be materialised by Match Report requests.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .canonical_materialize import _table_columns
from .database import DEFAULT_DB_PATH, connection
from .metric_registry import METRIC_SET_VERSION

RAW_REQUIRED_COLUMNS = {"match_id", "source", "event_type", "metadata_json", "event_id"}


def _parse_date(value: str | None):
    if value in (None, ""):
        return None
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _requested_match_ids(conn, *, date_from=None, date_to=None, team_ids: Iterable[str] = ()) -> set[str]:
    start = _parse_date(date_from)
    end = _parse_date(date_to)
    if start and end and start > end:
        raise ValueError("date_from must be on or before date_to")

    clauses = []
    params: list[object] = []
    if start:
        clauses.append("m.match_date>=?")
        params.append(start)
    if end:
        clauses.append("m.match_date<=?")
        params.append(end)

    teams = tuple(str(item) for item in (team_ids or ()))
    if teams:
        marks = ",".join("?" for _ in teams)
        clauses.append(f"(CAST(m.home_team_id AS VARCHAR) IN ({marks}) OR CAST(m.away_team_id AS VARCHAR) IN ({marks}))")
        params.extend(teams)
        params.extend(teams)

    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    rows = conn.execute(f"SELECT DISTINCT m.match_id FROM matches m{where}", params).fetchall()
    return {str(row[0]) for row in rows}


def canonical_readiness(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    date_from=None,
    date_to=None,
    team_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Describe raw-source and canonical-store coverage without fabricating data.

    When a date/team scope is supplied, readiness is calculated only for matches in
    that requested leaderboard range. This lets callers fail closed on partial
    range data without requiring unrelated seasons to be canonical first.
    """
    db_path = Path(db_path)
    result: dict[str, Any] = {
        "metric_set_version": METRIC_SET_VERSION,
        "db_available": db_path.exists(),
        "raw_schema_ready": False,
        "raw_matches": 0,
        "requested_matches": 0,
        "canonical_team_matches": 0,
        "canonical_player_matches": 0,
        "canonical_exposure_matches": 0,
        "canonical_complete_matches": 0,
        "coverage_percent": 0.0,
        "missing_raw_columns": [],
        "missing_raw_matches": [],
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

        all_raw_ids = {
            str(row[0])
            for row in conn.execute(
                """
                SELECT DISTINCT match_id
                FROM match_events
                WHERE lower(source)='whoscored' AND event_type='raw_whoscored'
                """
            ).fetchall()
        }
        result["raw_matches"] = len(all_raw_ids)

        requested_ids = _requested_match_ids(
            conn,
            date_from=date_from,
            date_to=date_to,
            team_ids=team_ids,
        )
        result["requested_matches"] = len(requested_ids)
        missing_raw = sorted(requested_ids - all_raw_ids)
        result["missing_raw_matches"] = missing_raw
        raw_ids = requested_ids & all_raw_ids

        def materialised_ids(table: str, extra_where: str = "", params: list[object] | None = None) -> set[str]:
            if table not in tables:
                return set()
            rows = conn.execute(
                f"SELECT DISTINCT match_id FROM {table} WHERE metric_set_version=? {extra_where}",
                [METRIC_SET_VERSION, *(params or [])],
            ).fetchall()
            return {str(row[0]) for row in rows}

        team_metric_ids = materialised_ids("canonical_metric_values", "AND scope='team'")
        player_metric_ids = materialised_ids("canonical_metric_values", "AND scope='player'")
        exposure_ids = materialised_ids("canonical_player_exposure")
        complete_ids = raw_ids & team_metric_ids & player_metric_ids & exposure_ids
        missing_ids = sorted(requested_ids - complete_ids)

        denominator = len(requested_ids)
        result.update({
            "canonical_team_matches": len(team_metric_ids & requested_ids),
            "canonical_player_matches": len(player_metric_ids & requested_ids),
            "canonical_exposure_matches": len(exposure_ids & requested_ids),
            "canonical_complete_matches": len(complete_ids),
            "coverage_percent": round((len(complete_ids) / denominator * 100.0), 2) if denominator else 0.0,
            "missing_canonical_matches": missing_ids,
            "ready": bool(requested_ids) and not missing_ids and not missing_raw,
        })
        return result


def assert_canonical_ready(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    date_from=None,
    date_to=None,
    team_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Fail closed unless every requested match has canonical Metrics Bible data."""
    readiness = canonical_readiness(
        db_path,
        date_from=date_from,
        date_to=date_to,
        team_ids=team_ids,
    )
    if not readiness["raw_schema_ready"]:
        missing = ", ".join(readiness["missing_raw_columns"]) or "unknown raw-source defect"
        raise RuntimeError(f"Canonical source schema is not ready: {missing}")
    if readiness["requested_matches"] <= 0:
        raise RuntimeError("No matches exist for the requested canonical range")
    if readiness["missing_raw_matches"]:
        missing = readiness["missing_raw_matches"]
        preview = ", ".join(missing[:10])
        suffix = "..." if len(missing) > 10 else ""
        raise RuntimeError(
            f"Requested range contains {len(missing)} matches without full-fidelity raw WhoScored data: {preview}{suffix}"
        )
    if not readiness["ready"]:
        missing = readiness["missing_canonical_matches"]
        preview = ", ".join(missing[:10])
        suffix = "..." if len(missing) > 10 else ""
        raise RuntimeError(
            f"Canonical database coverage is incomplete: {readiness['canonical_complete_matches']}/"
            f"{readiness['requested_matches']} requested matches ({readiness['coverage_percent']}%); missing {preview}{suffix}"
        )
    return readiness
