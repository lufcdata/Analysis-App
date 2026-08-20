"""Frozen Bible-conformant Possession Share V2 implementation."""
from collections import defaultdict

NORMAL_PERIODS = {"FirstHalf", "SecondHalf"}
BASE_FAMILIES = {"PASS", "SHOT", "KEEPER"}
DEFENSIVE_CANDIDATES = {"RECOVERY", "INTERCEPTION", "TACKLE"}
SHOT_TYPES = {"Goal", "SavedShot", "MissedShots", "ShotOnPost"}
KEEPER_TYPES = {"Save", "KeeperPickup", "Claim", "Punch", "KeeperSweeper"}

def _dn(value): return value.get("displayName") if isinstance(value, dict) else value

def _family(event):
    explicit = event.get("event_family") or event.get("eventFamily") or event.get("family")
    if explicit: return str(explicit).upper()
    etype = _dn(event.get("type"))
    if etype == "Pass": return "PASS"
    if etype in SHOT_TYPES: return "SHOT"
    if etype in KEEPER_TYPES: return "KEEPER"
    if etype == "BallRecovery": return "RECOVERY"
    if etype == "Interception": return "INTERCEPTION"
    if etype == "Tackle": return "TACKLE"
    return ""

def _clock_seconds(event):
    minute = event.get("expandedMinute", event.get("minute", 0)) or 0
    second = event.get("second", 0) or 0
    return float(minute) * 60.0 + float(second)

def _group_events(events):
    groups = {}
    for event in events or []:
        period = _dn(event.get("period"))
        if period not in NORMAL_PERIODS: continue
        family = _family(event)
        if not family: continue
        key = (period, _clock_seconds(event), event.get("teamId"), event.get("playerId"))
        group = groups.setdefault(key, {"period": period, "time": key[1], "teamId": key[2], "families": set()})
        group["families"].add(family)
    return sorted(groups.values(), key=lambda g: (0 if g["period"] == "FirstHalf" else 1, g["time"], str(g["teamId"])))

def _selected_controlled_groups(groups):
    base = [g for g in groups if g["families"] & BASE_FAMILIES]
    selected = list(base); by_period = defaultdict(list)
    for g in base: by_period[g["period"]].append(g)
    for candidate in groups:
        if not (candidate["families"] & DEFENSIVE_CANDIDATES): continue
        confirmed = any(later["teamId"] == candidate["teamId"] and 0.0 <= later["time"] - candidate["time"] <= 3.0 for later in by_period[candidate["period"]] if later["time"] >= candidate["time"])
        if confirmed: selected.append(candidate)
    unique = {(g["period"], g["time"], g["teamId"]): g for g in selected}
    return sorted(unique.values(), key=lambda g: (0 if g["period"] == "FirstHalf" else 1, g["time"], str(g["teamId"])))

def calculate_possession_metrics(events, team_id=None, player_id=None):
    if player_id is not None: return {}
    groups = _selected_controlled_groups(_group_events(events)); seconds = defaultdict(float)
    for period in NORMAL_PERIODS:
        period_groups = [g for g in groups if g["period"] == period]
        for current, nxt in zip(period_groups, period_groups[1:]):
            elapsed = max(0.0, nxt["time"] - current["time"])
            seconds[current["teamId"]] += min(3.0, elapsed)
    total = sum(seconds.values())
    if team_id is None: return {"possession_share_v2_by_team": {tid: (value / total * 100.0 if total else None) for tid, value in seconds.items()}}
    return {"possession": (seconds.get(team_id, 0.0) / total * 100.0) if total else None}
