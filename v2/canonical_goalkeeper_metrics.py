"""Locked goalkeeper metrics scoped to canonical active windows."""
from collections import Counter

NORMAL_PERIODS = {"FirstHalf", "SecondHalf"}
SHOT_TYPES = {"Goal", "SavedShot", "MissedShots", "ShotOnPost"}

def _dn(value): return value.get("displayName") if isinstance(value, dict) else value

def _qnames(event): return {_dn(q.get("type")) for q in (event.get("qualifiers") or []) if isinstance(q, dict)}

def _clock(event):
    minute = event.get("expandedMinute", event.get("minute", 0)) or 0
    second = event.get("second", 0) or 0
    return float(minute) * 60.0 + float(second)

def _in_active_window(event, windows):
    period = _dn(event.get("period"))
    if period not in NORMAL_PERIODS: return False
    t = _clock(event)
    for window in windows or []:
        if window.get("period") != period: continue
        if float(window.get("start", 0.0)) <= t <= float(window.get("end", 999999.0)): return True
    return False

def _identity(event, index):
    value = event.get("eventId", event.get("id"))
    return str(value) if value is not None else (event.get("teamId"), event.get("playerId"), _dn(event.get("period")), _clock(event), _dn(event.get("type")), index)

def calculate_goalkeeper_metrics(events, team_id=None, player_id=None, active_windows=None):
    if team_id is None or player_id is None or not active_windows: return {}
    out = Counter(); seen = set()
    for index, event in enumerate(events or []):
        if not _in_active_window(event, active_windows): continue
        identity = _identity(event, index)
        if identity in seen: continue
        seen.add(identity)
        etype, event_team, qnames = _dn(event.get("type")), event.get("teamId"), _qnames(event)
        if event_team != team_id and etype in SHOT_TYPES and "OwnGoal" not in qnames:
            if etype == "Goal" or (etype == "SavedShot" and "Blocked" not in qnames): out["shots_on_target_faced"] += 1
            if etype == "SavedShot" and "Blocked" not in qnames: out["saves"] += 1
            if etype == "Goal": out["goals_conceded"] += 1
        if event_team == team_id and etype == "Goal" and "OwnGoal" in qnames: out["goals_conceded"] += 1
    out["clean_sheets"] = 1 if out["goals_conceded"] == 0 else 0
    faced = out["shots_on_target_faced"]
    out["save_percentage_percent"] = (out["saves"] / faced * 100.0) if faced else None
    return dict(out)
