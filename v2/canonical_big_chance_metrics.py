"""Bible-conformant Big Chance family from canonical WhoScored-derived events."""
from collections import Counter

NORMAL_PERIODS = {"FirstHalf", "SecondHalf"}

def _dn(value): return value.get("displayName") if isinstance(value, dict) else value

def _identity(event, fallback_index):
    for key in ("source_event_id", "eventId", "id"):
        value = event.get(key)
        if value is not None: return (key, str(value), event.get("event_type"))
    return ("fallback", event.get("teamId"), event.get("playerId"), _dn(event.get("period")), event.get("expandedMinute", event.get("minute")), event.get("second"), event.get("event_type"), fallback_index)

def _native_type(event):
    value = event.get("event_type")
    if value is None: value = event.get("eventType")
    return str(value or "").strip().lower()

def canonical_big_chance_events(events, team_id=None, player_id=None):
    seen = set()
    for i, event in enumerate(events or []):
        period = _dn(event.get("period"))
        if period and period not in NORMAL_PERIODS: continue
        if team_id is not None and event.get("teamId") != team_id: continue
        if player_id is not None and event.get("playerId") != player_id: continue
        native_type = _native_type(event)
        if native_type not in {"big_chance", "big_chance_missed"}: continue
        identity = _identity(event, i)
        if identity in seen: continue
        seen.add(identity); yield event, native_type

def calculate_big_chance_metrics(events, team_id=None, player_id=None):
    out = Counter()
    for event, native_type in canonical_big_chance_events(events, team_id, player_id):
        if native_type == "big_chance": out["big_chances"] += 1
        else: out["big_chances_missed"] += 1
    out["big_chances_scored"] = max(0, out["big_chances"] - out["big_chances_missed"])
    return dict(out)
