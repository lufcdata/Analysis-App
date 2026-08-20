from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .canonical_metric_engine import calculate_canonical_metrics
from .database import DEFAULT_DB_PATH, connection
from .metric_registry import METRIC_SET_VERSION, MetricStatus, approved_for
from .team_logos import logo_url

PERIODS = {"full": None, "first_half": "FirstHalf", "second_half": "SecondHalf"}
FIELD_TO_METRIC = {
    "goals": "goals", "possession": "possession", "touches": "touches", "penalty_box_touches": "penalty_box_touches",
    "shots": "shots", "shots_on_target": "shots_on_target", "set_piece_goals": "set_piece_goals", "big_chances": "big_chances",
    "chances_created": "chances_created", "progressive_passes": "progressive_passes", "successful_final_third_passes": "successful_final_third_passes",
    "successful_passes": "successful_passes", "accurate_long_passes": "accurate_long_passes", "pass_accuracy": "pass_accuracy",
    "accurate_crosses": "accurate_crosses", "successful_take_ons": "successful_take_ons", "ball_recoveries": "ball_recoveries",
    "tackles_won": "tackles_won", "interceptions": "interceptions", "ground_duels_won": "ground_duels_won",
    "aerial_duels_won": "aerial_duels_won", "clearances": "clearances", "corners": "corners", "saves": "saves", "red_cards": "red_cards",
}


def _assert_contract() -> None:
    approved = {spec.key for spec in approved_for("match_stats") if spec.status is MetricStatus.IMPLEMENT}
    unknown = set(FIELD_TO_METRIC.values()) - approved
    if unknown:
        raise RuntimeError(f"Match Centre contract contains non-approved metric keys: {sorted(unknown)}")


_assert_contract()


def _match_row(conn, match_id: str):
    raw = str(match_id).strip(); ws_id = None
    if raw.startswith("ws-match-") and raw[len("ws-match-"):].isdigit(): ws_id = int(raw[len("ws-match-"):])
    elif raw.isdigit(): ws_id = int(raw)
    row = conn.execute(
        """SELECT m.match_id,m.match_date,m.home_team_id,home_team.team_name,m.away_team_id,away_team.team_name,m.home_score,m.away_score
        FROM matches m JOIN teams home_team ON home_team.team_id=m.home_team_id JOIN teams away_team ON away_team.team_id=m.away_team_id
        WHERE m.match_id=? OR (? IS NOT NULL AND m.whoscored_match_id=?)""",
        [raw, ws_id, ws_id],
    ).fetchone()
    if not row: raise ValueError(f"Unknown V2 match_id: {match_id}")
    return row


def _stored_team_metrics(conn, match_id: str, team_id: str) -> dict[str, float | None]:
    rows = conn.execute(
        """SELECT metric_key, metric_value FROM canonical_metric_values
        WHERE metric_set_version=? AND match_id=? AND scope='team' AND team_id=? AND player_id=''""",
        [METRIC_SET_VERSION, match_id, team_id],
    ).fetchall()
    return {str(key): (None if value is None else float(value)) for key, value in rows}


def _metadata(value: Any) -> dict[str, Any]:
    if value is None: return {}
    if isinstance(value, dict): return dict(value)
    try:
        parsed = json.loads(str(value)); return dict(parsed) if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError): return {}


def _period_events(conn, match_id: str, canonical_period: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT team_id,player_id,period,minute,expanded_minute,second,x,y,end_x,end_y,outcome,metadata_json,event_id
        FROM match_events WHERE match_id=? AND source='whoscored' AND event_type='raw_whoscored' AND period=? ORDER BY time_seconds,event_id""",
        [match_id, canonical_period],
    ).fetchall()
    events = []
    for team_id, player_id, period, minute, expanded_minute, second, x, y, end_x, end_y, outcome, metadata_json, event_id in rows:
        event = _metadata(metadata_json)
        event.update({"teamId": team_id, "playerId": player_id, "period": {"displayName": period}, "minute": minute,
                      "expandedMinute": expanded_minute if expanded_minute is not None else minute, "second": second,
                      "x": x, "y": y, "endX": end_x, "endY": end_y})
        if event.get("eventId") is None and event.get("id") is None: event["eventId"] = event_id
        if "outcomeType" not in event and outcome is not None: event["outcomeType"] = {"displayName": "Successful" if bool(outcome) else "Unsuccessful"}
        events.append(event)
    if not events: raise ValueError(f"No raw WhoScored {canonical_period} events found for {match_id}; refusing period recalculation from lossy derived rows")
    return events


def _recalculated_team_metrics(conn, match_id: str, team_id: str, canonical_period: str) -> dict[str, float | None]:
    metrics = calculate_canonical_metrics(_period_events(conn, match_id, canonical_period), team_id=team_id, surface="match_stats")["metrics"]
    return {key: (None if value is None else float(value)) for key, value in metrics.items()}


def _shape(metrics: dict[str, float | None]) -> dict[str, float | None]:
    shaped = {field: metrics.get(metric_key) for field, metric_key in FIELD_TO_METRIC.items()}
    ground, aerial = shaped.get("ground_duels_won"), shaped.get("aerial_duels_won")
    shaped["duels_won"] = None if ground is None or aerial is None else ground + aerial
    return shaped


def get_canonical_match_stats(match_id: str, *, period: str = "full", db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    if period not in PERIODS: raise ValueError("period must be full, first_half or second_half")
    with connection(db_path, read_only=True) as conn:
        match = _match_row(conn, str(match_id)); canonical_match_id = str(match[0]); home_id, away_id = str(match[2]), str(match[4]); canonical_period = PERIODS[period]
        if canonical_period is None:
            home_metrics = _stored_team_metrics(conn, canonical_match_id, home_id); away_metrics = _stored_team_metrics(conn, canonical_match_id, away_id); source = "canonical_metric_values"
        else:
            home_metrics = _recalculated_team_metrics(conn, canonical_match_id, home_id, canonical_period); away_metrics = _recalculated_team_metrics(conn, canonical_match_id, away_id, canonical_period); source = "canonical_metric_engine"
        home, away = _shape(home_metrics), _shape(away_metrics)
        missing = sorted(field for field in FIELD_TO_METRIC if home.get(field) is None or away.get(field) is None)
        return {
            "match": {"match_id": canonical_match_id, "date": str(match[1]), "home_team_id": home_id, "home_team": match[3], "home_logo_url": logo_url(match[3]),
                      "away_team_id": away_id, "away_team": match[5], "away_logo_url": logo_url(match[5]), "home_score": match[6], "away_score": match[7]},
            "period": period, "canonical_period": canonical_period, "metric_set_version": METRIC_SET_VERSION, "source": source,
            "home": home, "away": away,
            "availability": {"possession": home.get("possession") is not None and away.get("possession") is not None, "missing_fields": missing},
        }
