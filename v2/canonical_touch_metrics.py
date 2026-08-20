"""Bible-conformant touch metrics from canonical raw WhoScored events."""
from collections import Counter

NORMAL_PERIODS = {"FirstHalf", "SecondHalf"}
FINAL_THIRD_START = 200.0 / 3.0
BOX_X_MIN = 83.0
BOX_X_MAX = 100.0
BOX_Y_MIN = 21.1
BOX_Y_MAX = 78.9


def _dn(value): return value.get("displayName") if isinstance(value, dict) else value

def _identity(event, fallback_index):
    event_id = event.get("id")
    if event_id is not None: return ("id", str(event_id))
    return ("fallback", event.get("teamId"), event.get("playerId"), _dn(event.get("period")), event.get("expandedMinute", event.get("minute")), event.get("second"), _dn(event.get("type")), fallback_index)

def canonical_touch_events(events, team_id=None, player_id=None):
    seen = set()
    for i, event in enumerate(events or []):
        if _dn(event.get("period")) not in NORMAL_PERIODS: continue
        if team_id is not None and event.get("teamId") != team_id: continue
        if player_id is not None and event.get("playerId") != player_id: continue
        if not event.get("isTouch", False): continue
        identity = _identity(event, i)
        if identity in seen: continue
        seen.add(identity); yield event

def calculate_touch_metrics(events, team_id=None, player_id=None):
    out = Counter()
    for event in canonical_touch_events(events, team_id=team_id, player_id=player_id):
        out["touches"] += 1
        x, y = event.get("x"), event.get("y")
        if x is None: continue
        x = float(x)
        if FINAL_THIRD_START <= x <= 100.0: out["final_third_touches"] += 1
        if y is not None:
            y = float(y)
            if BOX_X_MIN <= x <= BOX_X_MAX and BOX_Y_MIN <= y <= BOX_Y_MAX: out["penalty_box_touches"] += 1
    return dict(out)
