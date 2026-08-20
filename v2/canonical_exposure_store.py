"""Canonical player exposure storage for minutes/per-90 denominators.

Exposure is deliberately separate from football metric values. Minutes played is
not a registry metric and must never be inserted into canonical_metric_values.
"""
from .metric_registry import METRIC_SET_VERSION

SCHEMA = """
CREATE TABLE IF NOT EXISTS canonical_player_exposure (
    metric_set_version TEXT NOT NULL,
    match_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    active_seconds REAL NOT NULL CHECK(active_seconds >= 0),
    PRIMARY KEY (metric_set_version, match_id, team_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_canonical_player_exposure_lookup
ON canonical_player_exposure(metric_set_version, team_id, player_id, match_id);
"""


def init_canonical_exposure_store(conn) -> None:
    conn.execute(SCHEMA)


def replace_player_exposure(conn, *, match_id, team_id, player_id, active_seconds) -> None:
    seconds = float(active_seconds)
    if seconds < 0:
        raise ValueError("active_seconds must be non-negative")
    conn.execute(
        "INSERT OR REPLACE INTO canonical_player_exposure "
        "(metric_set_version, match_id, team_id, player_id, active_seconds) "
        "VALUES (?, ?, ?, ?, ?)",
        (METRIC_SET_VERSION, str(match_id), str(team_id), str(player_id), seconds),
    )
