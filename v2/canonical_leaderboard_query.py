"""Rate-safe canonical leaderboard query layer for the Aug-18 live surface."""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from .canonical_minutes import per_90
from .canonical_metric_store import _assert_approved_metric_key
from .metric_registry import BY_KEY, METRIC_SET_VERSION, MetricKind, MetricStatus, approved_for
from .team_logos import logo_url

RATIO_DEFINITIONS = {
    "pass_accuracy_percent": ("successful_passes", "total_passes"),
    "save_percentage_percent": ("saves", "shots_on_target_faced"),
}


def _as_date(value: str | date | None) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _age_on(dob: date | None, on_date: date) -> int | None:
    if dob is None:
        return None
    return on_date.year - dob.year - ((on_date.month, on_date.day) < (dob.month, dob.day))


def _filters(*, date_from=None, date_to=None, team_ids: Iterable[str] = (), match_alias="m", value_alias="v"):
    clauses = []
    params: list[object] = []
    start = _as_date(date_from)
    end = _as_date(date_to)
    if start and end and start > end:
        raise ValueError("date_from must be on or before date_to")
    if start:
        clauses.append(f"{match_alias}.match_date>=?")
        params.append(start)
    if end:
        clauses.append(f"{match_alias}.match_date<=?")
        params.append(end)
    team_ids = tuple(str(item) for item in team_ids or ())
    if team_ids:
        marks = ",".join("?" for _ in team_ids)
        clauses.append(f"{value_alias}.team_id IN ({marks})")
        params.extend(team_ids)
    return clauses, params, start, end


def _metric_totals(conn, metric_key, *, scope="player", date_from=None, date_to=None, team_ids=()):
    clauses, params, _, _ = _filters(date_from=date_from, date_to=date_to, team_ids=team_ids)
    where = ["v.metric_set_version=?", "v.scope=?", "v.metric_key=?", *clauses]
    rows = conn.execute(
        "SELECT v.team_id,v.player_id,SUM(v.metric_value) FROM canonical_metric_values v JOIN matches m ON m.match_id=v.match_id WHERE " + " AND ".join(where) + " GROUP BY v.team_id,v.player_id",
        [METRIC_SET_VERSION, scope, metric_key, *params],
    ).fetchall()
    return {(str(team_id), str(player_id)): value for team_id, player_id, value in rows}


def _minutes_by_player(conn, *, date_from=None, date_to=None, team_ids=()):
    clauses, params, _, _ = _filters(date_from=date_from, date_to=date_to, team_ids=team_ids, value_alias="e")
    where = ["e.metric_set_version=?", *clauses]
    rows = conn.execute(
        "SELECT e.team_id,e.player_id,SUM(e.active_seconds) FROM canonical_player_exposure e JOIN matches m ON m.match_id=e.match_id WHERE " + " AND ".join(where) + " GROUP BY e.team_id,e.player_id",
        [METRIC_SET_VERSION, *params],
    ).fetchall()
    return {(str(team_id), str(player_id)): float(seconds or 0.0) / 60.0 for team_id, player_id, seconds in rows}


def _player_metadata(conn):
    rows = conn.execute("SELECT player_id,player_name,nationality,date_of_birth,position FROM players").fetchall()
    return {
        str(player_id): {
            "player_name": player_name,
            "nationality": nationality,
            "date_of_birth": dob,
            "position": position,
        }
        for player_id, player_name, nationality, dob, position in rows
    }


def _team_metadata(conn):
    rows = conn.execute("SELECT team_id,team_name FROM teams").fetchall()
    return {
        str(team_id): {"team_name": team_name, "team_logo_url": logo_url(team_name)}
        for team_id, team_name in rows
    }


def _team_match_counts(conn, *, date_from=None, date_to=None, team_ids=()):
    clauses, params, _, _ = _filters(date_from=date_from, date_to=date_to, team_ids=team_ids)
    where = ["v.metric_set_version=?", "v.scope='team'", *clauses]
    rows = conn.execute(
        "SELECT v.team_id,COUNT(DISTINCT v.match_id) FROM canonical_metric_values v JOIN matches m ON m.match_id=v.match_id WHERE " + " AND ".join(where) + " GROUP BY v.team_id",
        [METRIC_SET_VERSION, *params],
    ).fetchall()
    return {str(team_id): int(matches or 0) for team_id, matches in rows}


def metric_catalog(surface: str = "live") -> list[dict[str, object]]:
    return [
        {
            "key": spec.key,
            "label": spec.label,
            "kind": spec.kind.value,
            "per90": spec.kind is MetricKind.SCALAR and spec.key not in RATIO_DEFINITIONS,
        }
        for spec in approved_for(surface)
        if spec.status is MetricStatus.IMPLEMENT and spec.kind is MetricKind.SCALAR
    ]


def leaderboard_metadata(conn, *, surface: str = "live") -> dict[str, object]:
    if surface not in {"live", "match_stats"}:
        raise ValueError("surface must be live or match_stats")
    min_date, max_date = conn.execute("SELECT MIN(match_date),MAX(match_date) FROM matches").fetchone()
    total, with_dob = conn.execute("SELECT COUNT(*),COUNT(date_of_birth) FROM players").fetchone()
    teams = sorted(_team_metadata(conn).items(), key=lambda item: (item[1]["team_name"] or ""))
    return {
        "metric_set_version": METRIC_SET_VERSION,
        "surface": surface,
        "min_date": str(min_date) if min_date else None,
        "max_date": str(max_date) if max_date else None,
        "players_total": int(total or 0),
        "players_with_dob": int(with_dob or 0),
        "teams": [{"team_id": team_id, **meta} for team_id, meta in teams],
        "metrics": metric_catalog(surface),
    }


def leaderboard_rows(
    conn,
    metric_key: str,
    *,
    mode: str = "total",
    surface: str = "live",
    scope: str = "player",
    date_from=None,
    date_to=None,
    team_ids=(),
    min_minutes: float = 0,
    min_age: int = 15,
    max_age: int = 45,
    positions=(),
    limit: int | None = None,
):
    _assert_approved_metric_key(metric_key, surface=surface)
    if mode not in {"total", "per90"}:
        raise ValueError("mode must be total or per90")
    if scope not in {"player", "team"}:
        raise ValueError("scope must be player or team")
    if scope == "team" and mode == "per90":
        raise ValueError("per90 is not yet supported for canonical team leaderboard rows")
    if min_age > max_age:
        raise ValueError("min_age must be on or before max_age")

    spec = BY_KEY[metric_key]
    values = _metric_totals(conn, metric_key, scope=scope, date_from=date_from, date_to=date_to, team_ids=team_ids)

    if metric_key in RATIO_DEFINITIONS:
        numerator_key, denominator_key = RATIO_DEFINITIONS[metric_key]
        numerators = _metric_totals(conn, numerator_key, scope=scope, date_from=date_from, date_to=date_to, team_ids=team_ids)
        denominators = _metric_totals(conn, denominator_key, scope=scope, date_from=date_from, date_to=date_to, team_ids=team_ids)
        identities = set(numerators) | set(denominators)
        values = {}
        for identity in identities:
            numerator = float(numerators.get(identity) or 0.0)
            denominator = float(denominators.get(identity) or 0.0)
            values[identity] = (numerator / denominator * 100.0) if denominator > 0 else None

    team_meta = _team_metadata(conn)
    result = []

    if scope == "player":
        minutes = _minutes_by_player(conn, date_from=date_from, date_to=date_to, team_ids=team_ids)
        player_meta = _player_metadata(conn)
        positions = {str(item) for item in positions or ()}
        _, _, _, end = _filters(date_from=date_from, date_to=date_to, team_ids=team_ids)
        age_date = end or date.today()
        for (team_id, player_id), total in values.items():
            meta = player_meta.get(player_id)
            if not meta:
                continue
            mins = minutes.get((team_id, player_id), 0.0)
            if mins < float(min_minutes):
                continue
            age = _age_on(meta["date_of_birth"], age_date)
            if age is not None and not (int(min_age) <= age <= int(max_age)):
                continue
            if positions and str(meta["position"] or "") not in positions:
                continue
            value = total
            if mode == "per90" and metric_key not in RATIO_DEFINITIONS:
                value = per_90(total, mins, metric_key)
            result.append({
                "team_id": team_id,
                "team_name": team_meta.get(team_id, {}).get("team_name"),
                "team_logo_url": team_meta.get(team_id, {}).get("team_logo_url"),
                "player_id": player_id,
                "player_name": meta["player_name"],
                "nationality": meta["nationality"],
                "date_of_birth": str(meta["date_of_birth"]) if meta["date_of_birth"] else None,
                "age": age,
                "position": meta["position"],
                "metric_key": metric_key,
                "metric_label": spec.label,
                "metric_set_version": METRIC_SET_VERSION,
                "mode": mode,
                "value": value,
                "total": total,
                "minutes_played": mins,
            })
    else:
        matches = _team_match_counts(conn, date_from=date_from, date_to=date_to, team_ids=team_ids)
        for (team_id, _), total in values.items():
            result.append({
                "team_id": team_id,
                "team_name": team_meta.get(team_id, {}).get("team_name"),
                "team_logo_url": team_meta.get(team_id, {}).get("team_logo_url"),
                "matches": matches.get(team_id, 0),
                "metric_key": metric_key,
                "metric_label": spec.label,
                "metric_set_version": METRIC_SET_VERSION,
                "mode": mode,
                "value": total,
                "total": total,
            })

    result.sort(
        key=lambda row: (
            row["value"] is not None,
            row["value"] if row["value"] is not None else float("-inf"),
            row.get("player_name") or row.get("team_name") or "",
        ),
        reverse=True,
    )
    if limit is not None:
        return result[: max(0, int(limit))]
    return result
