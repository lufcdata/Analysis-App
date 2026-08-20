"""Bible-conformant take-on, defensive, duel, and foul metrics."""
from collections import Counter

NORMAL_PERIODS = {"FirstHalf", "SecondHalf"}

def _dn(value): return value.get("displayName") if isinstance(value, dict) else value

def _qualifiers(event): return {_dn(q.get("type")) for q in (event.get("qualifiers") or []) if isinstance(q, dict)}

def _identity(event, fallback_index):
    event_id = event.get("id")
    if event_id is not None: return ("id", str(event_id))
    return ("fallback", event.get("teamId"), event.get("playerId"), _dn(event.get("period")), event.get("expandedMinute", event.get("minute")), event.get("second"), _dn(event.get("type")), fallback_index)

def canonical_events(events, team_id=None, player_id=None):
    seen, out = set(), []
    for i, event in enumerate(events or []):
        if _dn(event.get("period")) not in NORMAL_PERIODS: continue
        if team_id is not None and event.get("teamId") != team_id: continue
        if player_id is not None and event.get("playerId") != player_id: continue
        identity = _identity(event, i)
        if identity in seen: continue
        seen.add(identity); out.append(event)
    out.sort(key=lambda e: (0 if _dn(e.get("period")) == "FirstHalf" else 1, e.get("expandedMinute", e.get("minute", 0)) or 0, e.get("second", 0) or 0, str(e.get("id", ""))))
    return out

def _seconds(event):
    minute = event.get("expandedMinute", event.get("minute", 0)) or 0
    return minute * 60 + (event.get("second", 0) or 0)

def calculate_defensive_duel_metrics(events, team_id=None, player_id=None):
    evs = canonical_events(events, team_id=team_id, player_id=player_id)
    out = Counter(); suppress_takeon_loss = set()
    for i, event in enumerate(evs):
        if _dn(event.get("type")) != "TakeOn" or _dn(event.get("outcomeType")) != "Unsuccessful": continue
        t0 = _seconds(event)
        for j in range(i + 1, min(len(evs), i + 6)):
            later = evs[j]
            if later.get("playerId") != event.get("playerId"): continue
            dt = _seconds(later) - t0
            if dt > 4: break
            if _dn(later.get("type")) == "Foul" and _dn(later.get("outcomeType")) == "Successful": suppress_takeon_loss.add(i); break
    for i, event in enumerate(evs):
        typ, outcome, q = _dn(event.get("type")), _dn(event.get("outcomeType")), _qualifiers(event)
        if typ == "TakeOn":
            out["take_on_attempts_total_take_ons"] += 1
            if outcome == "Successful": out["successful_take_ons"] += 1
            elif outcome == "Unsuccessful": out["unsuccessful_take_ons"] += 1
        if typ == "Tackle":
            if outcome == "Successful": out["tackles_won"] += 1
            elif outcome == "Unsuccessful": out["tackles_lost"] += 1
        elif typ == "Interception": out["interceptions"] += 1
        elif typ == "BallRecovery": out["ball_recoveries"] += 1
        elif typ == "Clearance" and "BlockedCross" not in q:
            out["clearances"] += 1
            if "Head" in q: out["headed_clearances"] += 1
        if typ == "Foul":
            if outcome == "Unsuccessful": out["fouls_committed"] += 1
            elif outcome == "Successful" and event.get("playerId") is not None: out["fouls_won"] += 1
        if typ == "Tackle": out["ground_duels_won"] += 1
        elif typ == "TakeOn":
            if outcome == "Successful": out["ground_duels_won"] += 1
            elif outcome == "Unsuccessful" and i not in suppress_takeon_loss: out["ground_duels_lost"] += 1
        elif typ == "Foul":
            if outcome == "Successful": out["ground_duels_won"] += 1
            elif outcome == "Unsuccessful": out["ground_duels_lost"] += 1
        elif typ in {"Dispossessed", "Challenge"}: out["ground_duels_lost"] += 1
        if typ == "Aerial":
            if outcome == "Successful": out["aerial_duels_won"] += 1
            elif outcome == "Unsuccessful": out["aerial_duels_lost"] += 1
    out["duels_won"] = out["ground_duels_won"] + out["aerial_duels_won"]
    out["duels_lost"] = out["ground_duels_lost"] + out["aerial_duels_lost"]
    return dict(out)
