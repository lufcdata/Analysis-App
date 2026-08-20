"""Materialise the Aug-18 Metrics Bible into the production DuckDB.

This is the production hard-cutover bridge:
full-fidelity raw WhoScored events -> canonical Bible engine -> versioned stores.
No legacy derived-stat table is used as a football-metric source.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .canonical_exposure_store import init_canonical_exposure_store, replace_player_exposure
from .canonical_metric_engine import calculate_canonical_metrics
from .canonical_metric_store import init_canonical_metric_store, replace_metric_values
from .canonical_minutes import player_active_window_seconds
from .canonical_pass_receiver_metrics import build_pass_receiver_assignments
from .database import DEFAULT_DB_PATH, connection
from .metric_registry import METRIC_SET_VERSION

NORMAL_PERIODS = {"FirstHalf", "SecondHalf"}


def _metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value))
        return dict(parsed) if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _display_name(value: Any) -> Any:
    return value.get("displayName") if isinstance(value, dict) else value


def _normalise_period(value: Any) -> str | None:
    raw = _display_name(value)
    if raw is None:
        return None
    text = str(raw).strip()
    compact = "".join(ch for ch in text.lower() if ch.isalnum())
    if compact in {"firsthalf", "1h", "first", "period1", "1"}:
        return "FirstHalf"
    if compact in {"secondhalf", "2h", "second", "period2", "2"}:
        return "SecondHalf"
    return text


def _table_columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall()}


def _raw_events(conn, match_id: str) -> list[dict[str, Any]]:
    """Load the full-fidelity WhoScored source rows for one match.

    Do not pre-filter on normalised derivative columns such as ``period``. Older
    valid snapshots can encode those labels differently; the original metadata
    JSON is the football source of truth and is normalised only after loading.
    """
    columns = _table_columns(conn, "match_events")
    required = {"match_id", "source", "event_type", "metadata_json", "event_id"}
    missing = sorted(required - columns)
    if missing:
        raise ValueError("match_events missing required raw-event columns: " + ", ".join(missing))

    def col(name: str, fallback: str = "NULL") -> str:
        return name if name in columns else fallback

    rows = conn.execute(
        f"""
        SELECT {col('team_id')},{col('player_id')},{col('period')},{col('minute')},
               {col('expanded_minute')},{col('second')},{col('time_seconds')},
               {col('x')},{col('y')},{col('end_x')},{col('end_y')},{col('outcome')},
               metadata_json,event_id
        FROM match_events
        WHERE match_id=? AND lower(source)='whoscored'
          AND event_type='raw_whoscored'
        ORDER BY COALESCE({col('time_seconds', '0')},0),event_id
        """,
        [match_id],
    ).fetchall()

    events: list[dict[str, Any]] = []
    for (
        team_id, player_id, period, minute, expanded_minute, second, time_seconds,
        x, y, end_x, end_y, outcome, metadata_json, event_id,
    ) in rows:
        event = _metadata(metadata_json)
        metadata_period = _normalise_period(event.get("period"))
        column_period = _normalise_period(period)
        canonical_period = metadata_period or column_period

        event.update({
            "teamId": None if team_id is None else str(team_id),
            "playerId": None if player_id is None else str(player_id),
            "minute": minute if minute is not None else event.get("minute"),
            "expandedMinute": (
                expanded_minute
                if expanded_minute is not None
                else event.get("expandedMinute", event.get("minute", minute))
            ),
            "second": second if second is not None else event.get("second"),
            "time_seconds": time_seconds,
            "x": x if x is not None else event.get("x"),
            "y": y if y is not None else event.get("y"),
            "endX": end_x if end_x is not None else event.get("endX"),
            "endY": end_y if end_y is not None else event.get("endY"),
        })
        if canonical_period is not None:
            event["period"] = {"displayName": canonical_period}
        if event.get("eventId") is None and event.get("id") is None:
            event["eventId"] = event_id
        if "outcomeType" not in event and outcome is not None:
            event["outcomeType"] = {"displayName": "Successful" if bool(outcome) else "Unsuccessful"}
        events.append(event)

    if not events:
        raise ValueError(
            f"No full-fidelity raw WhoScored events found for {match_id}; "
            "refusing to materialise Metrics Bible values from legacy derived rows"
        )
    return events


def _match_teams(conn, match_id: str) -> tuple[str, str]:
    row = conn.execute(
        "SELECT home_team_id,away_team_id FROM matches WHERE match_id=?",
        [match_id],
    ).fetchone()
    if not row:
        raise ValueError(f"Unknown V2 match_id: {match_id}")
    return str(row[0]), str(row[1])


def _players(conn, match_id: str) -> list[dict[str, Any]]:
    """Read the canonical roster while tolerating historical minutes column names."""
    pms_columns = _table_columns(conn, "player_match_stats")
    if not {"match_id", "player_id", "team_id"}.issubset(pms_columns):
        raise ValueError("player_match_stats is missing match/player/team identity columns")

    if "mins_played" in pms_columns:
        minutes_expr = "pms.mins_played"
    elif "minutes_played" in pms_columns:
        minutes_expr = "pms.minutes_played"
    elif "minutes" in pms_columns:
        minutes_expr = "pms.minutes"
    else:
        minutes_expr = "0"

    player_columns = _table_columns(conn, "players")
    position_expr = "p.position" if "position" in player_columns else "NULL"
    rows = conn.execute(
        f"""
        SELECT pms.player_id,pms.team_id,{minutes_expr},{position_expr}
        FROM player_match_stats pms
        LEFT JOIN players p ON p.player_id=pms.player_id
        WHERE pms.match_id=?
        ORDER BY pms.team_id,pms.player_id
        """,
        [match_id],
    ).fetchall()
    return [
        {
            "player_id": str(player_id),
            "team_id": str(team_id),
            "mins_played": float(mins_played or 0.0),
            "position": str(position or ""),
        }
        for player_id, team_id, mins_played, position in rows
    ]


def _is_substitute(events: list[dict[str, Any]], player_id: str) -> bool:
    for event in events:
        etype = _display_name(event.get("type"))
        if event.get("playerId") == player_id and etype == "SubstitutionOn":
            return True
    return False


def _goalkeeper_windows(events: list[dict[str, Any]], team_id: str, player_id: str, is_starter: bool):
    window = player_active_window_seconds(events, team_id, player_id, is_starter)
    if window is None:
        return None
    start, end = window
    return [{"period": period, "start": start, "end": end} for period in NORMAL_PERIODS]


def _already_materialised(conn, match_id: str) -> bool:
    team_rows = int(conn.execute(
        "SELECT COUNT(*) FROM canonical_metric_values WHERE metric_set_version=? AND match_id=? AND scope='team'",
        [METRIC_SET_VERSION, match_id],
    ).fetchone()[0])
    player_rows = int(conn.execute(
        "SELECT COUNT(*) FROM canonical_metric_values WHERE metric_set_version=? AND match_id=? AND scope='player'",
        [METRIC_SET_VERSION, match_id],
    ).fetchone()[0])
    return team_rows > 0 and player_rows > 0


def materialize_match(db_path: str | Path, match_id: str, *, force: bool = False) -> dict[str, Any]:
    match_id = str(match_id)
    with connection(db_path) as conn:
        init_canonical_metric_store(conn)
        init_canonical_exposure_store(conn)
        if not force and _already_materialised(conn, match_id):
            return {"match_id": match_id, "metric_set_version": METRIC_SET_VERSION, "status": "already_materialised"}

        events = _raw_events(conn, match_id)
        home_id, away_id = _match_teams(conn, match_id)
        players = _players(conn, match_id)
        if not players:
            raise ValueError(f"No player_match_stats roster found for {match_id}")

        identities = {row["player_id"] for row in players}
        identities.update(str(event["playerId"]) for event in events if event.get("playerId"))
        player_id_map = {player_id: player_id for player_id in identities}
        assignments = build_pass_receiver_assignments(events, player_id_map)

        team_reports: dict[str, Any] = {}
        for team_id in (home_id, away_id):
            roster = {row["player_id"] for row in players if row["team_id"] == team_id}
            result = calculate_canonical_metrics(
                events,
                team_id=team_id,
                player_id=None,
                canonical_player_id=None,
                player_id_map=player_id_map,
                pass_receiver_assignments=assignments,
                roster_player_ids=roster,
                surface="match_stats",
            )
            replace_metric_values(
                conn,
                match_id=match_id,
                scope="team",
                team_id=team_id,
                metrics=result["metrics"],
                surface="match_stats",
            )
            team_reports[team_id] = {
                "stored_metric_keys": sorted(result["metrics"]),
                "unimplemented_active_keys": result["unimplemented_active_keys"],
            }

        player_reports = []
        for row in players:
            player_id = row["player_id"]
            team_id = row["team_id"]
            is_starter = row["mins_played"] > 0 and not _is_substitute(events, player_id)
            active_window = player_active_window_seconds(events, team_id, player_id, is_starter)
            active_seconds = (
                max(0.0, active_window[1] - active_window[0])
                if active_window is not None
                else max(0.0, row["mins_played"] * 60.0)
            )
            replace_player_exposure(
                conn,
                match_id=match_id,
                team_id=team_id,
                player_id=player_id,
                active_seconds=active_seconds,
            )
            gk_windows = None
            if row["position"].upper().startswith("GK"):
                gk_windows = _goalkeeper_windows(events, team_id, player_id, is_starter)

            result = calculate_canonical_metrics(
                events,
                team_id=team_id,
                player_id=player_id,
                canonical_player_id=player_id,
                player_id_map=player_id_map,
                pass_receiver_assignments=assignments,
                goalkeeper_active_windows=gk_windows,
                surface="live",
            )
            metrics = dict(result["metrics"])
            metrics.pop("possession", None)
            replace_metric_values(
                conn,
                match_id=match_id,
                scope="player",
                team_id=team_id,
                player_id=player_id,
                metrics=metrics,
                surface="live",
            )
            player_reports.append({
                "player_id": player_id,
                "team_id": team_id,
                "active_seconds": active_seconds,
                "stored_metric_keys": sorted(metrics),
                "unimplemented_active_keys": result["unimplemented_active_keys"],
            })

        conn.commit()
        return {
            "match_id": match_id,
            "metric_set_version": METRIC_SET_VERSION,
            "status": "materialised",
            "raw_event_count": len(events),
            "pass_receiver_assignments": len(assignments),
            "teams": team_reports,
            "players": player_reports,
        }


def ensure_match_materialized(match_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    return materialize_match(db_path, match_id, force=False)
