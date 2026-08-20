"""Bible-conformant chance-creation metrics."""
from collections import Counter

NORMAL_PERIODS = {"FirstHalf", "SecondHalf"}

def _dn(value): return value.get("displayName") if isinstance(value, dict) else value

def _qualifiers(event): return {_dn(q.get("type")) for q in (event.get("qualifiers") or []) if isinstance(q, dict)}

def _identity(event, fallback_index):
    event_id = event.get("id")
    if event_id is not None: return ("id", str(event_id))
    return ("fallback", event.get("teamId"), event.get("playerId"), _dn(event.get("period")), event.get("expandedMinute", event.get("minute")), event.get("second"), _dn(event.get("type")), fallback_index)

def calculate_chance_metrics(events, team_id=None, player_id=None, assisted_source_event_ids=None):
    assisted_source_event_ids = {str(v) for v in (assisted_source_event_ids or ())}; seen = set(); out = Counter()
    for i, event in enumerate(events or []):
        if _dn(event.get("period")) not in NORMAL_PERIODS: continue
        if team_id is not None and event.get("teamId") != team_id: continue
        if player_id is not None and event.get("playerId") != player_id: continue
        identity = _identity(event, i)
        if identity in seen: continue
        seen.add(identity); q = _qualifiers(event)
        if "KeyPass" in q: out["key_passes"] += 1; out["chances_created"] += 1
        if "BigChanceCreated" in q: out["big_chances_created"] += 1
        event_id = event.get("id")
        if event_id is not None and str(event_id) in assisted_source_event_ids: out["assists"] += 1
    return dict(out)
