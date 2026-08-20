from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .canonical_progressive_pass_metrics import iter_progressive_passes
from .database import DEFAULT_DB_PATH, connection
from .metric_registry import METRIC_SET_VERSION, MetricStatus, approved_for
from .spatial_plot_data import canonical_to_portrait

PERIODS = {"full": None, "first_half": "FirstHalf", "second_half": "SecondHalf"}
SUPPORTED_LAYERS = {"progressive_passes"}


def _approved_live_keys() -> set[str]:
    return {spec.key for spec in approved_for("live") if spec.status is MetricStatus.IMPLEMENT}


def metric_catalog() -> list[dict[str, str]]:
    return [{"key": spec.key, "label": spec.label} for spec in approved_for("live") if spec.status is MetricStatus.IMPLEMENT and spec.key in SUPPORTED_LAYERS]


def _metadata(value: Any) -> dict[str, Any]:
    if value is None: return {}
    if isinstance(value, dict): return dict(value)
    try:
        parsed = json.loads(str(value)); return dict(parsed) if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError): return {}


def _raw_events(conn, match_id: str, canonical_period: str | None) -> list[dict[str, Any]]:
    period_clause = ""; params: list[Any] = [match_id]
    if canonical_period is not None: period_clause = " AND period=?"; params.append(canonical_period)
    rows = conn.execute(
        """SELECT team_id,player_id,period,minute,expanded_minute,second,time_seconds,x,y,end_x,end_y,outcome,metadata_json,event_id
        FROM match_events WHERE match_id=? AND source='whoscored' AND event_type='raw_whoscored'""" + period_clause + " ORDER BY time_seconds,event_id",
        params,
    ).fetchall()
    events = []
    for team_id, player_id, period, minute, expanded_minute, second, time_seconds, x, y, end_x, end_y, outcome, metadata_json, event_id in rows:
        event = _metadata(metadata_json)
        event.update({"teamId": team_id, "playerId": player_id, "period": {"displayName": period}, "minute": minute,
                      "expandedMinute": expanded_minute if expanded_minute is not None else minute, "second": second, "time_seconds": time_seconds,
                      "x": x, "y": y, "endX": end_x, "endY": end_y})
        if event.get("eventId") is None and event.get("id") is None: event["eventId"] = event_id
        if "outcomeType" not in event and outcome is not None: event["outcomeType"] = {"displayName": "Successful" if bool(outcome) else "Unsuccessful"}
        events.append(event)
    return events


def _event_id(event: dict[str, Any]) -> str:
    return str(event.get("eventId", event.get("id")))


def _shape_progressive_pass(event: dict[str, Any], end_x, end_y) -> dict[str, Any]:
    start_x, start_y, ex, ey = float(event["x"]), float(event["y"]), float(end_x), float(end_y)
    portrait_x, portrait_y = canonical_to_portrait(start_x, start_y)
    portrait_end_x, portrait_end_y = canonical_to_portrait(ex, ey)
    period = event.get("period"); period_name = period.get("displayName") if isinstance(period, dict) else period
    return {"event_id": _event_id(event), "team_id": str(event.get("teamId") or ""), "player_id": str(event.get("playerId") or ""),
            "period": period_name, "minute": event.get("minute"), "second": event.get("second"), "time_seconds": event.get("time_seconds"),
            "x": start_x, "y": start_y, "end_x": ex, "end_y": ey,
            "portrait_x": portrait_x, "portrait_y": portrait_y, "portrait_end_x": portrait_end_x, "portrait_end_y": portrait_end_y,
            "source": "raw_whoscored", "metric_key": "progressive_passes"}


def get_live_pitch_metric_layer(match_id: str, *, metric: str = "progressive_passes", team_id: str | None = None, player_id: str | None = None,
                                player_ids: list[str] | tuple[str, ...] | None = None, period: str = "full", db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    if period not in PERIODS: raise ValueError("period must be full, first_half or second_half")
    if metric not in _approved_live_keys(): raise ValueError(f"Metric {metric!r} is not an implemented Live Player / Team metric")
    if metric not in SUPPORTED_LAYERS: raise ValueError(f"Metric {metric!r} does not yet have a canonical Pitch Plot event layer")
    selected_player_ids = tuple(dict.fromkeys(str(value) for value in (player_ids or ()) if str(value)))
    if player_id and selected_player_ids: raise ValueError("Use player_id or player_ids, not both")
    with connection(db_path, read_only=True) as conn:
        match = conn.execute("SELECT match_id FROM matches WHERE match_id=?", [match_id]).fetchone()
        if not match: raise ValueError(f"Unknown V2 match_id: {match_id}")
        events = _raw_events(conn, str(match[0]), PERIODS[period])
    if not events: raise ValueError(f"No raw WhoScored events found for {match_id}; refusing lossy Pitch Plot fallback")
    classified = [_shape_progressive_pass(event, end_x, end_y) for event, end_x, end_y in iter_progressive_passes(events, team_id=team_id, player_id=player_id)]
    layer = [event for event in classified if not selected_player_ids or event["player_id"] in selected_player_ids]
    return {"match_id": str(match[0]), "metric_set_version": METRIC_SET_VERSION, "surface": "live", "metric": metric, "period": period,
            "team_id": team_id, "player_id": player_id, "player_ids": list(selected_player_ids),
            "selection_mode": "multi" if selected_player_ids else ("single" if player_id else "all"),
            "source": "raw_whoscored", "events": layer, "catalog": metric_catalog()}
