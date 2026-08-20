"""Bible-conformant corner metrics from canonical raw WhoScored/Opta events."""
from collections import Counter

NORMAL_PERIODS = {"FirstHalf", "SecondHalf"}

def _dn(value): return value.get("displayName") if isinstance(value, dict) else value

def qualifier_names(event): return {_dn(q.get("type")) for q in (event.get("qualifiers") or []) if isinstance(q, dict)}

def _identity(event, fallback_index):
    event_id = event.get("id")
    if event_id is not None: return ("id", str(event_id))
    return ("fallback", event.get("teamId"), event.get("playerId"), _dn(event.get("period")), event.get("expandedMinute", event.get("minute")), event.get("second"), fallback_index)

def _end(event):
    if event.get("endX") is not None and event.get("endY") is not None: return float(event["endX"]), float(event["endY"])
    ex = ey = None
    for q in event.get("qualifiers") or []:
        name = _dn((q or {}).get("type"))
        if name == "PassEndX": ex = float(q.get("value"))
        elif name == "PassEndY": ey = float(q.get("value"))
    return ex, ey

def canonical_corners(events, team_id=None, player_id=None):
    seen, corners = set(), []
    for i, event in enumerate(events or []):
        if _dn(event.get("period")) not in NORMAL_PERIODS: continue
        if team_id is not None and event.get("teamId") != team_id: continue
        if player_id is not None and event.get("playerId") != player_id: continue
        if _dn(event.get("type")) != "Pass" or "CornerTaken" not in qualifier_names(event): continue
        identity = _identity(event, i)
        if identity in seen: continue
        seen.add(identity); corners.append(event)
    return corners

def delivery_type(event):
    q = qualifier_names(event)
    if "Cross" not in q: return "short"
    end_x, end_y = _end(event)
    if end_x is None or end_y is None or end_x < 85.0: return "overhit"
    if 43.0 <= end_y <= 57.0: return "central"
    origin_y = float(event.get("y", 50.0))
    if origin_y < 50.0:
        if 30.0 <= end_y < 43.0: return "near_post"
        if 57.0 < end_y <= 70.0: return "far_post"
    else:
        if 57.0 < end_y <= 70.0: return "near_post"
        if 30.0 <= end_y < 43.0: return "far_post"
    return "overhit"

def calculate_corner_metrics(events, team_id=None, player_id=None, assisted_source_event_ids=None):
    assisted_source_event_ids = {str(v) for v in (assisted_source_event_ids or ())}; out = Counter()
    for corner in canonical_corners(events, team_id=team_id, player_id=player_id):
        outcome, q, delivery = _dn(corner.get("outcomeType")), qualifier_names(corner), delivery_type(corner)
        if outcome == "Successful": out["successful_corners"] += 1
        elif outcome == "Unsuccessful": out["unsuccessful_corners"] += 1
        out[f"corner_{delivery}"] += 1
        if "KeyPass" in q: out["corner_chances_created"] += 1
        source_id = corner.get("id")
        if source_id is not None and str(source_id) in assisted_source_event_ids: out["corner_assists"] += 1
    return dict(out)
