"""Versioned storage boundary for Aug-18 canonical scalar metrics."""
from typing import Mapping

from .metric_registry import BY_KEY, METRIC_SET_VERSION, MetricKind, MetricStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS canonical_metric_values (
    metric_set_version TEXT NOT NULL,
    match_id TEXT NOT NULL,
    scope TEXT NOT NULL CHECK(scope IN ('player','team')),
    team_id TEXT NOT NULL,
    player_id TEXT NOT NULL DEFAULT '',
    metric_key TEXT NOT NULL,
    metric_value REAL,
    PRIMARY KEY (metric_set_version, match_id, scope, team_id, player_id, metric_key)
);
CREATE INDEX IF NOT EXISTS idx_canonical_metric_values_lookup
ON canonical_metric_values(metric_set_version, scope, metric_key, team_id, player_id, match_id);
"""


def init_canonical_metric_store(conn) -> None:
    conn.execute(SCHEMA)


def _assert_approved_metric_key(metric_key: str, surface: str = "live") -> None:
    spec = BY_KEY.get(metric_key)
    if spec is None:
        raise ValueError(f"Refusing non-canonical metric key: {metric_key}")
    if spec.status is not MetricStatus.IMPLEMENT:
        raise ValueError(f"Refusing unavailable metric key: {metric_key}")
    if spec.kind is not MetricKind.SCALAR:
        raise ValueError(f"Refusing relationship metric in scalar store: {metric_key}")
    if surface not in spec.surfaces:
        raise ValueError(f"Metric {metric_key} is not approved for surface {surface}")


def replace_metric_values(conn, *, match_id, scope: str, team_id, player_id=None, metrics: Mapping[str, object], surface: str = "live") -> None:
    if scope not in {"player", "team"}:
        raise ValueError("scope must be player or team")
    if scope == "player" and player_id is None:
        raise ValueError("player scope requires canonical player_id")
    canonical_player_id = "" if player_id is None else str(player_id)
    rows = []
    for metric_key, value in metrics.items():
        _assert_approved_metric_key(metric_key, surface=surface)
        numeric_value = None if value is None else float(value)
        rows.append((METRIC_SET_VERSION, str(match_id), scope, str(team_id), canonical_player_id, metric_key, numeric_value))
    conn.execute(
        "DELETE FROM canonical_metric_values WHERE metric_set_version=? AND match_id=? AND scope=? AND team_id=? AND player_id=?",
        (METRIC_SET_VERSION, str(match_id), scope, str(team_id), canonical_player_id),
    )
    if rows:
        conn.executemany(
            "INSERT INTO canonical_metric_values (metric_set_version, match_id, scope, team_id, player_id, metric_key, metric_value) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def aggregate_metric(conn, *, metric_key: str, scope: str = "player", start_match_id=None):
    _assert_approved_metric_key(metric_key)
    where = ["metric_set_version=?", "scope=?", "metric_key=?"]
    params = [METRIC_SET_VERSION, scope, metric_key]
    if start_match_id is not None:
        where.append("match_id>=?")
        params.append(str(start_match_id))
    sql = "SELECT team_id, player_id, SUM(metric_value) AS metric_value FROM canonical_metric_values WHERE " + " AND ".join(where) + " GROUP BY team_id, player_id"
    return conn.execute(sql, params).fetchall()
