from __future__ import annotations

from pathlib import Path
from typing import Any

from .database import DEFAULT_DB_PATH, connection
from .metric_registry import METRIC_SET_VERSION, MetricKind, MetricStatus, approved_for
from .team_logos import logo_url


def _live_scalar_metrics():
    return tuple(spec for spec in approved_for("live") if spec.status is MetricStatus.IMPLEMENT and spec.kind is MetricKind.SCALAR)


def metric_catalog() -> list[dict[str, str]]:
    return [{"key": spec.key, "label": spec.label} for spec in _live_scalar_metrics()]


def get_match_metric_leaders(match_id: str, metric: str = "successful_passes", *, team_id: str | None = None, limit: int = 5, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    specs = {spec.key: spec for spec in _live_scalar_metrics()}; spec = specs.get(metric)
    if spec is None: raise ValueError(f"Metric {metric!r} is not an implemented Live Player / Team metric")
    limit = max(1, min(int(limit), 20))
    with connection(db_path, read_only=True) as conn:
        if not conn.execute("SELECT 1 FROM matches WHERE match_id=?", [match_id]).fetchone(): raise ValueError(f"Unknown V2 match_id: {match_id}")
        params: list[Any] = [METRIC_SET_VERSION, match_id, metric]; team_clause = ""
        if team_id: team_clause = " AND cmv.team_id=?"; params.append(team_id)
        rows = conn.execute(
            """SELECT cmv.player_id, p.player_name, cmv.team_id, t.team_name, cmv.metric_value
            FROM canonical_metric_values cmv JOIN players p ON p.player_id=cmv.player_id JOIN teams t ON t.team_id=cmv.team_id
            WHERE cmv.metric_set_version=? AND cmv.match_id=? AND cmv.scope='player' AND cmv.metric_key=? AND COALESCE(cmv.metric_value, 0) > 0""" + team_clause +
            " ORDER BY cmv.metric_value DESC, p.player_name ASC LIMIT ?", params + [limit]).fetchall()
    leader_value = float(rows[0][4]) if rows else 0.0; leaders = []
    for rank, (player_id, player_name, row_team_id, team_name, value) in enumerate(rows, start=1):
        numeric = float(value or 0)
        leaders.append({"rank": rank, "player_id": player_id, "player_name": player_name, "team_id": row_team_id, "team_name": team_name,
                        "team_logo_url": logo_url(team_name), "value": numeric, "relative_to_leader": (numeric / leader_value) if leader_value > 0 else 0.0})
    return {"match_id": match_id, "metric_set_version": METRIC_SET_VERSION, "metric": metric, "label": spec.label, "surface": "live",
            "scope": "team" if team_id else "both_teams", "team_id": team_id, "leaders": leaders, "catalog": metric_catalog()}
