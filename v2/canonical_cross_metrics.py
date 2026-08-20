"""Bible-conformant cross metrics from raw WhoScored Pass events."""

NORMAL_PERIODS = {"FirstHalf", "SecondHalf"}
CROSS_QUALIFIER_ID = 2

def _dn(value): return value.get("displayName") if isinstance(value, dict) else value

def _is_successful(event):
    outcome = event.get("outcomeType")
    if isinstance(outcome, dict): return outcome.get("value") == 1 or str(outcome.get("displayName", "")).lower() == "successful"
    return outcome == 1 or str(outcome).lower() == "successful"

def _qualifier_ids(event):
    result = set()
    for qualifier in event.get("qualifiers", []) or []:
        if not isinstance(qualifier, dict): continue
        qtype = qualifier.get("type", {}) or {}; value = qtype.get("value", qtype.get("id"))
        try: result.add(int(value))
        except (TypeError, ValueError): pass
    return result

def _identity(event, index):
    for key in ("eventId", "id"):
        value = event.get(key)
        if value is not None: return (key, str(value))
    return ("fallback", index)

def calculate_cross_metrics(events, team_id=None, player_id=None):
    seen = set(); accurate = 0
    for index, event in enumerate(events or []):
        if _dn(event.get("period")) not in NORMAL_PERIODS: continue
        if _dn(event.get("type")) != "Pass": continue
        if team_id is not None and event.get("teamId") != team_id: continue
        if player_id is not None and event.get("playerId") != player_id: continue
        if CROSS_QUALIFIER_ID not in _qualifier_ids(event): continue
        identity = _identity(event, index)
        if identity in seen: continue
        seen.add(identity)
        if _is_successful(event): accurate += 1
    return {"accurate_crosses": accurate}
