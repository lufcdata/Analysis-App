"""Locked successful passer→receiver assignment engine."""
from collections import Counter, defaultdict
from math import hypot

NORMAL_PERIODS = {"FirstHalf", "SecondHalf"}
TOUCH_TYPES = {"Pass", "BallTouch", "TakeOn", "Goal", "SavedShot", "MissedShots", "ShotOnPost", "Tackle", "Interception", "Clearance", "Dispossessed", "Challenge", "Aerial"}


def _dn(value):
    return value.get("displayName") if isinstance(value, dict) else value


def _clock(event):
    return int(event.get("expandedMinute", event.get("minute", 0)) or 0) * 60 + int(event.get("second", 0) or 0)


def _successful_pass(event):
    return _dn(event.get("type")) == "Pass" and _dn(event.get("outcomeType")) == "Successful"


def _touch_evidence(event):
    return bool(event.get("isTouch")) or _dn(event.get("type")) in TOUCH_TYPES


def _xy(event):
    x, y = event.get("x"), event.get("y")
    return (float(x), float(y)) if x is not None and y is not None else None


def _end_xy(event):
    x, y = event.get("endX"), event.get("endY")
    if x is not None and y is not None:
        return float(x), float(y)
    values = {}
    for q in event.get("qualifiers") or []:
        if not isinstance(q, dict):
            continue
        name = _dn(q.get("type"))
        if name in {"PassEndX", "PassEndY"}:
            try:
                values[name] = float(q.get("value"))
            except (TypeError, ValueError):
                pass
    if "PassEndX" in values and "PassEndY" in values:
        return values["PassEndX"], values["PassEndY"]
    return None


def _stable_player_id(source_player_id, player_id_map):
    if source_player_id is None:
        return None
    if player_id_map is None:
        raise ValueError("canonical player_id_map is required for receiver assignment")
    value = player_id_map.get(source_player_id)
    if value is None:
        value = player_id_map.get(str(source_player_id))
    if not value:
        raise ValueError(f"unresolved canonical player identity: {source_player_id}")
    return str(value)


def _reverse_direction_reject(pass_event, candidate):
    if _dn(candidate.get("type")) != "Pass":
        return False
    p_start, p_end = _xy(pass_event), _end_xy(pass_event)
    c_start, c_end = _xy(candidate), _end_xy(candidate)
    if not all((p_start, p_end, c_start, c_end)):
        return False
    reverse_distance = hypot(c_end[0] - p_start[0], c_end[1] - p_start[1])
    forward_distance = hypot(p_end[0] - c_start[0], p_end[1] - c_start[1])
    return reverse_distance <= 3.0 and reverse_distance <= forward_distance - 2.0


def build_pass_receiver_assignments(events, player_id_map):
    groups = defaultdict(list)
    ordered_times = defaultdict(set)
    for index, event in enumerate(events or []):
        period = _dn(event.get("period"))
        if period not in NORMAL_PERIODS:
            continue
        event = dict(event)
        event["_source_index"] = index
        t = _clock(event)
        groups[(period, t)].append(event)
        ordered_times[period].add(t)
    for period in ordered_times:
        ordered_times[period] = sorted(ordered_times[period])
    assignments = []
    seen = set()
    for index, p in enumerate(events or []):
        period = _dn(p.get("period"))
        if period not in NORMAL_PERIODS or not _successful_pass(p):
            continue
        source_id = p.get("eventId", p.get("id", index))
        identity = (period, str(source_id))
        if identity in seen:
            continue
        seen.add(identity)
        team = p.get("teamId")
        passer_source = p.get("playerId")
        passer = _stable_player_id(passer_source, player_id_map)
        t = _clock(p)
        same_second = [e for e in groups[(period, t)] if e.get("teamId") == team and e.get("playerId") not in (None, passer_source) and _touch_evidence(e)]
        receiver_event = None
        if len(same_second) == 1 and not _reverse_direction_reject(p, same_second[0]):
            receiver_event = same_second[0]
        if receiver_event is None:
            later_time = next((x for x in ordered_times[period] if x > t and any(e.get("teamId") == team and e.get("playerId") not in (None, passer_source) and _touch_evidence(e) for e in groups[(period, x)])), None)
            if later_time is not None:
                candidates = [e for e in groups[(period, later_time)] if e.get("teamId") == team and e.get("playerId") not in (None, passer_source) and _touch_evidence(e)]
                endpoint = _end_xy(p)
                if endpoint and candidates:
                    ranked = []
                    for e in candidates:
                        start = _xy(e)
                        if start is None:
                            continue
                        canonical_id = _stable_player_id(e.get("playerId"), player_id_map)
                        ranked.append((hypot(endpoint[0] - start[0], endpoint[1] - start[1]), canonical_id, e))
                    if ranked:
                        receiver_event = min(ranked, key=lambda row: (row[0], row[1]))[2]
        if receiver_event is None:
            continue
        receiver = _stable_player_id(receiver_event.get("playerId"), player_id_map)
        assignments.append({"source_pass_id": str(source_id), "period": period, "time_seconds": t, "team_source_id": team, "passer_id": passer, "receiver_id": receiver})
    return assignments


def calculate_pass_receiver_metrics(events, player_id=None, player_id_map=None, assignments=None, **_):
    if player_id is None:
        return {}
    rows = assignments if assignments is not None else build_pass_receiver_assignments(events, player_id_map)
    received = sum(1 for row in rows if row["receiver_id"] == player_id)
    made = sum(1 for row in rows if row["passer_id"] == player_id)
    return {"passes_received": received, "passes_made": made}


def pass_combination_counts(assignments, passer_id=None, receiver_id=None):
    counts = Counter()
    for row in assignments:
        if passer_id is not None and row["passer_id"] != passer_id:
            continue
        if receiver_id is not None and row["receiver_id"] != receiver_id:
            continue
        counts[(row["passer_id"], row["receiver_id"])] += 1
    return dict(counts)
