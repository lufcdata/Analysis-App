"""Bible-conformant parent Free-Kicks metric."""

NORMAL_PERIODS = {"FirstHalf", "SecondHalf"}
SHOT_TYPES = {"Goal", "SavedShot", "MissedShots", "ShotOnPost"}

def _dn(value): return value.get("displayName") if isinstance(value, dict) else value

def _qualifier_names(event): return {_dn(q.get("type")) for q in event.get("qualifiers", []) or [] if isinstance(q, dict)}

def _identity(event, fallback_index):
    for key in ("eventId", "id"):
        value = event.get(key)
        if value is not None: return (key, str(value))
    return ("fallback", event.get("teamId"), event.get("playerId"), _dn(event.get("period")), event.get("expandedMinute", event.get("minute")), event.get("second"), _dn(event.get("type")), fallback_index)

def _is_free_kick_restart(event):
    etype = _dn(event.get("type")); qualifiers = _qualifier_names(event)
    if etype == "Pass" and ({"FreekickTaken", "IndirectFreekickTaken"} & qualifiers): return True
    if etype in SHOT_TYPES and "DirectFreekick" in qualifiers: return True
    return False

def calculate_free_kick_metrics(events, team_id=None, player_id=None):
    seen = set(); total = 0
    for index, event in enumerate(events or []):
        if _dn(event.get("period")) not in NORMAL_PERIODS: continue
        if team_id is not None and event.get("teamId") != team_id: continue
        if player_id is not None and event.get("playerId") != player_id: continue
        if not _is_free_kick_restart(event): continue
        identity = _identity(event, index)
        if identity in seen: continue
        seen.add(identity); total += 1
    return {"free_kicks": total}
