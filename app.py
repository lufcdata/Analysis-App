from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from v2.canonical_leaderboard_query import leaderboard_metadata, leaderboard_rows
from v2.canonical_materialize import ensure_match_materialized
from v2.canonical_match_stats import get_canonical_match_stats
from v2.canonical_readiness import canonical_readiness
from v2.database import DEFAULT_DB_PATH, connection
from v2.live_pitch_metric_layers import get_live_pitch_metric_layer
from v2.match_inventory import get_match_inventory
from v2.match_metric_leaders import get_match_metric_leaders
from v2.metric_registry import METRIC_SET_VERSION
from v2.spatial_plot_data import build_match_spatial_payload

app = Flask(__name__)
CORS(
    app,
    resources={r"/api/*": {"origins": [
        "https://lufcdata-frontend.onrender.com",
        "http://localhost:5173",
    ]}},
)

CONFIGURED_V2_DB_PATH = Path(os.environ.get("V2_DB_PATH", str(DEFAULT_DB_PATH)))
V2_DB_PATH = (
    CONFIGURED_V2_DB_PATH
    if CONFIGURED_V2_DB_PATH.exists() or not DEFAULT_DB_PATH.exists()
    else DEFAULT_DB_PATH
)
ASSET_ROOT = Path(__file__).resolve().parent / "assets"


def _csv(name: str) -> list[str]:
    value = (request.args.get(name) or "").strip()
    return [item.strip() for item in value.split(",") if item.strip()]


def _optional_int(name: str) -> int | None:
    value = request.args.get(name)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _optional_float(name: str) -> float | None:
    value = request.args.get(name)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc


def _require_db():
    if V2_DB_PATH.exists():
        return None
    return jsonify({
        "error": "V2 database is not available on this deployment",
        "db_path": str(V2_DB_PATH),
        "configured_db_path": str(CONFIGURED_V2_DB_PATH),
        "default_db_path": str(DEFAULT_DB_PATH),
    }), 503


def _ensure_match_metrics(match_id: str) -> None:
    """Populate the canonical Metrics Bible store for the requested match."""
    ensure_match_materialized(match_id, db_path=V2_DB_PATH)


def _runtime_diagnostics() -> dict[str, object]:
    diagnostics: dict[str, object] = {
        "raw_whoscored_rows": 0,
        "canonical_metric_rows": 0,
        "canonical_exposure_rows": 0,
        "materialized_matches": 0,
    }
    if not V2_DB_PATH.exists():
        diagnostics.update(canonical_readiness(V2_DB_PATH))
        return diagnostics

    try:
        readiness = canonical_readiness(V2_DB_PATH)
        missing_matches = list(readiness.pop("missing_canonical_matches", []))
        diagnostics.update(readiness)
        diagnostics["missing_canonical_matches_count"] = len(missing_matches)
        diagnostics["missing_canonical_matches_preview"] = missing_matches[:10]

        with connection(V2_DB_PATH, read_only=True) as conn:
            tables = {str(row[0]) for row in conn.execute("SHOW TABLES").fetchall()}
            if "match_events" in tables:
                event_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info('match_events')").fetchall()}
                if {"source", "event_type"}.issubset(event_columns):
                    diagnostics["raw_whoscored_rows"] = int(conn.execute(
                        "SELECT COUNT(*) FROM match_events WHERE lower(source)='whoscored' AND event_type='raw_whoscored'"
                    ).fetchone()[0])
            if "canonical_metric_values" in tables:
                diagnostics["canonical_metric_rows"] = int(conn.execute(
                    "SELECT COUNT(*) FROM canonical_metric_values WHERE metric_set_version=?",
                    [METRIC_SET_VERSION],
                ).fetchone()[0])
                diagnostics["materialized_matches"] = int(conn.execute(
                    "SELECT COUNT(DISTINCT match_id) FROM canonical_metric_values WHERE metric_set_version=?",
                    [METRIC_SET_VERSION],
                ).fetchone()[0])
            if "canonical_player_exposure" in tables:
                diagnostics["canonical_exposure_rows"] = int(conn.execute(
                    "SELECT COUNT(*) FROM canonical_player_exposure WHERE metric_set_version=?",
                    [METRIC_SET_VERSION],
                ).fetchone()[0])
    except Exception as exc:
        diagnostics["diagnostics_error"] = f"{type(exc).__name__}: {exc}"
    return diagnostics


def _server_error(exc: Exception):
    return jsonify({
        "error": str(exc),
        "error_type": type(exc).__name__,
        "metric_set_version": METRIC_SET_VERSION,
    }), 500


@app.get("/")
def root():
    return jsonify({"service": "LUFCDATA API", "api": "v2", "status": "ok"})


@app.get("/api/v2/health")
def health():
    return jsonify({
        "service": "LUFCDATA API",
        "api": "v2",
        "metric_set_version": METRIC_SET_VERSION,
        "db_path": str(V2_DB_PATH),
        "db_available": V2_DB_PATH.exists(),
        **_runtime_diagnostics(),
    })


@app.get("/assets/team_logos/<path:filename>")
def team_logo(filename: str):
    return send_from_directory(ASSET_ROOT / "team_logos", filename)


@app.get("/api/v2/matches")
def matches():
    unavailable = _require_db()
    if unavailable:
        return unavailable
    try:
        return jsonify(get_match_inventory(
            season_id=request.args.get("season_id") or None,
            matchday=_optional_int("matchday"),
            db_path=V2_DB_PATH,
        ))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return _server_error(exc)


@app.get("/api/v2/matches/<match_id>/spatial")
def match_spatial(match_id: str):
    unavailable = _require_db()
    if unavailable:
        return unavailable
    try:
        return jsonify(build_match_spatial_payload(
            match_id,
            team_id=request.args.get("team_id") or None,
            player_ids=_csv("player_ids"),
            periods=_csv("periods"),
            start_seconds=_optional_int("start_seconds"),
            end_seconds=_optional_int("end_seconds"),
            db_path=V2_DB_PATH,
        ))
    except ValueError as exc:
        message = str(exc)
        return jsonify({"error": message}), 404 if message.startswith("Unknown V2 match_id") else 400
    except Exception as exc:
        return _server_error(exc)


@app.get("/api/v2/matches/<match_id>/stats")
def match_stats(match_id: str):
    unavailable = _require_db()
    if unavailable:
        return unavailable
    try:
        _ensure_match_metrics(match_id)
        return jsonify(get_canonical_match_stats(
            match_id,
            period=request.args.get("period") or "full",
            db_path=V2_DB_PATH,
        ))
    except ValueError as exc:
        message = str(exc)
        return jsonify({"error": message}), 404 if message.startswith("Unknown V2 match_id") else 400
    except Exception as exc:
        return _server_error(exc)


@app.get("/api/v2/matches/<match_id>/metric-leaders")
def match_metric_leaders(match_id: str):
    unavailable = _require_db()
    if unavailable:
        return unavailable
    try:
        _ensure_match_metrics(match_id)
        return jsonify(get_match_metric_leaders(
            match_id,
            metric=request.args.get("metric") or "successful_passes",
            team_id=request.args.get("team_id") or None,
            limit=_optional_int("limit") or 5,
            db_path=V2_DB_PATH,
        ))
    except ValueError as exc:
        message = str(exc)
        return jsonify({"error": message}), 404 if message.startswith("Unknown V2 match_id") else 400
    except Exception as exc:
        return _server_error(exc)


@app.get("/api/v2/matches/<match_id>/pitch-metric")
def match_pitch_metric(match_id: str):
    unavailable = _require_db()
    if unavailable:
        return unavailable
    try:
        return jsonify(get_live_pitch_metric_layer(
            match_id,
            metric=request.args.get("metric") or "progressive_passes",
            team_id=request.args.get("team_id") or None,
            player_id=request.args.get("player_id") or None,
            player_ids=_csv("player_ids"),
            period=request.args.get("period") or "full",
            db_path=V2_DB_PATH,
        ))
    except ValueError as exc:
        message = str(exc)
        return jsonify({"error": message}), 404 if message.startswith("Unknown V2 match_id") else 400
    except Exception as exc:
        return _server_error(exc)


@app.get("/api/v2/leaderboard/meta")
def leaderboard_meta():
    unavailable = _require_db()
    if unavailable:
        return unavailable
    try:
        surface = (request.args.get("surface") or "live").lower()
        with connection(V2_DB_PATH, read_only=True) as conn:
            return jsonify(leaderboard_metadata(conn, surface=surface))
    except ValueError as exc:
        return jsonify({"error": str(exc), "metric_set_version": METRIC_SET_VERSION}), 400
    except Exception as exc:
        return _server_error(exc)


@app.get("/api/v2/leaderboard")
def leaderboard():
    unavailable = _require_db()
    if unavailable:
        return unavailable
    try:
        scope = (request.args.get("scope") or "player").lower()
        mode = (request.args.get("mode") or "total").lower()
        surface = (request.args.get("surface") or "live").lower()
        metric = (request.args.get("metric") or "goals").strip()
        kwargs = {
            "mode": mode,
            "surface": surface,
            "scope": scope,
            "date_from": request.args.get("date_from"),
            "date_to": request.args.get("date_to"),
            "team_ids": _csv("team_ids"),
            "min_minutes": _optional_float("min_minutes") or 0,
            "min_age": _optional_int("min_age") or 15,
            "max_age": _optional_int("max_age") or 45,
            "positions": _csv("positions"),
            "limit": _optional_int("limit"),
        }
        with connection(V2_DB_PATH, read_only=True) as conn:
            rows = leaderboard_rows(conn, metric, **kwargs)
        return jsonify({
            "metric_set_version": METRIC_SET_VERSION,
            "surface": surface,
            "scope": scope,
            "mode": mode,
            "metric": metric,
            "date_from": kwargs["date_from"],
            "date_to": kwargs["date_to"],
            "rows": rows,
        })
    except ValueError as exc:
        return jsonify({"error": str(exc), "metric_set_version": METRIC_SET_VERSION}), 400
    except Exception as exc:
        return _server_error(exc)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
