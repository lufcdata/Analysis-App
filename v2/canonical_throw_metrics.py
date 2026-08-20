"""Bible-conformant throw-in metrics from canonical raw WhoScored events."""
from collections import Counter
from math import hypot

NORMAL_PERIODS = {"FirstHalf", "SecondHalf"}
THROW_IN_QUALIFIER_ID = 107
PENALTY_BOX_X_MIN, PENALTY_BOX_X_MAX = 83.0, 100.0
PENALTY_BOX_Y_MIN, PENALTY_BOX_Y_MAX = 21.1, 78.9
MIN_LONG_THROW_METRES = 20.0

def _dn(value): return value.get("displayName") if isinstance(value, dict) else value

def _qualifier_ids(event):
    ids = set()
    for qualifier in event.get("qualifiers", []) or []:
        qtype = qualifier.get("type", {}) if isinstance(qualifier, dict) else {}
        qid = qtype.get("value", qtype.get("id"))
        try: ids.add(int(qid))
        except (TypeError, ValueError): pass
    return ids

def _pass_end(event):
    end_x = end_y = None
    for qualifier in event.get("qualifiers", []) or []:
        if not isinstance(qualifier, dict): continue
        name = _dn(qualifier.get("type"))
        try:
            if name == "PassEndX": end_x = float(qualifier.get("value"))
            elif name == "PassEndY": end_y = float(qualifier.get("value"))
        except (TypeError, ValueError): continue
    return end_x, end_y

def _identity(event, fallback_index):
    for key in ("eventId", "id"):
        value = event.get(key)
        if value is not None: return (key, str(value))
    return ("fallback", event.get("teamId"), event.get("playerId"), _dn(event.get("period")), event.get("expandedMinute", event.get("minute")), event.get("second"), _dn(event.get("type")), fallback_index)

def _is_successful(event):
    outcome = event.get("outcomeType")
    if isinstance(outcome, dict): return outcome.get("value") == 1 or str(outcome.get("displayName", "")).lower() == "successful"
    return outcome == 1 or str(outcome).lower() == "successful"

def _inside_opposition_penalty_area(end_x, end_y):
    return end_x is not None and end_y is not None and PENALTY_BOX_X_MIN <= end_x <= PENALTY_BOX_X_MAX and PENALTY_BOX_Y_MIN <= end_y <= PENALTY_BOX_Y_MAX

def _throw_distance_metres(event, end_x, end_y):
    try: start_x, start_y = float(event.get("x")), float(event.get("y"))
    except (TypeError, ValueError): return None
    if end_x is None or end_y is None: return None
    return hypot((float(end_x)-start_x)*1.05, (float(end_y)-start_y)*0.68)

def canonical_throw_events(events, team_id=None, player_id=None):
    seen = set()
    for i, event in enumerate(events or []):
        if _dn(event.get("period")) not in NORMAL_PERIODS: continue
        if team_id is not None and event.get("teamId") != team_id: continue
        if player_id is not None and event.get("playerId") != player_id: continue
        if _dn(event.get("type")) != "Pass" or THROW_IN_QUALIFIER_ID not in _qualifier_ids(event): continue
        identity = _identity(event, i)
        if identity in seen: continue
        seen.add(identity); yield event

def calculate_throw_metrics(events, team_id=None, player_id=None):
    out = Counter()
    for event in canonical_throw_events(events, team_id=team_id, player_id=player_id):
        successful = _is_successful(event); out["throw_ins_total_throws"] += 1
        if successful: out["successful_throw_ins"] += 1
        else: out["unsuccessful_throw_ins"] += 1
        end_x, end_y = _pass_end(event); distance_m = _throw_distance_metres(event, end_x, end_y)
        if distance_m is None or distance_m < MIN_LONG_THROW_METRES or not _inside_opposition_penalty_area(end_x, end_y): continue
        out["long_throws_into_opposition_penalty_area"] += 1
        if successful: out["successful_long_throws_into_opposition_penalty_area"] += 1
        else: out["unsuccessful_long_throws_into_opposition_penalty_area"] += 1
    return dict(out)
