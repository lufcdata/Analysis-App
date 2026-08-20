"""Bible-conformant goal and shot metrics from canonical raw WhoScored/Opta events."""
from collections import Counter

NORMAL_PERIODS = {"FirstHalf", "SecondHalf"}
SHOT_TYPES = {"Goal", "SavedShot", "MissedShots", "ShotOnPost"}
SET_PIECE_QUALIFIERS = {"FromCorner", "SetPiece", "DirectFreekick", "ThrowinSetPiece"}


def _dn(value):
    return value.get("displayName") if isinstance(value, dict) else value


def qualifier_names(event):
    return {_dn(q.get("type")) for q in (event.get("qualifiers") or []) if isinstance(q, dict)}


def _identity(event, fallback_index):
    event_id = event.get("id")
    if event_id is not None:
        return ("id", str(event_id))
    return ("fallback", event.get("teamId"), event.get("playerId"), _dn(event.get("period")), event.get("expandedMinute", event.get("minute")), event.get("second"), _dn(event.get("type")), fallback_index)


def canonical_events(events, team_id=None, player_id=None):
    seen = set()
    for i, event in enumerate(events or []):
        if _dn(event.get("period")) not in NORMAL_PERIODS:
            continue
        if team_id is not None and event.get("teamId") != team_id:
            continue
        if player_id is not None and event.get("playerId") != player_id:
            continue
        identity = _identity(event, i)
        if identity in seen:
            continue
        seen.add(identity)
        yield event


def _is_normal_goal(event, q):
    return _dn(event.get("type")) == "Goal" and _dn(event.get("outcomeType")) == "Successful" and "OwnGoal" not in q


def _is_normal_shot(event, q):
    return _dn(event.get("type")) in SHOT_TYPES and "OwnGoal" not in q


def _has_prefix(q, *prefixes):
    return any(any(name.startswith(prefix) for prefix in prefixes) for name in q if name)


def calculate_attack_metrics(events, team_id=None, player_id=None):
    out = Counter()
    for event in canonical_events(events, team_id=team_id, player_id=player_id):
        etype = _dn(event.get("type"))
        q = qualifier_names(event)
        if etype == "Goal" and "OwnGoal" in q:
            out["goals_own_goals"] += 1
        if _is_normal_goal(event, q):
            out["goals"] += 1
            if "RegularPlay" in q: out["goals_open_play"] += 1
            if "Penalty" in q: out["goals_penalties"] += 1
            if "FastBreak" in q: out["goals_fast_break"] += 1
            is_corner = "FromCorner" in q
            is_throw_set_piece = "ThrowinSetPiece" in q
            is_direct_fk = "DirectFreekick" in q
            is_generic_set_piece = "SetPiece" in q
            if (q & SET_PIECE_QUALIFIERS) and "Penalty" not in q: out["goals_set_pieces"] += 1
            if (is_direct_fk or is_generic_set_piece) and not (is_corner or is_throw_set_piece or "Penalty" in q): out["goals_free_kicks"] += 1
            if _has_prefix(q, "SmallBox"): out["goals_6_yard_box"] += 1
            elif _has_prefix(q, "OutOfBox"): out["goals_outside_box"] += 1
            elif _has_prefix(q, "Box"): out["goals_penalty_area"] += 1
            if "RightFoot" in q: out["goals_right_foot"] += 1
            elif "LeftFoot" in q: out["goals_left_foot"] += 1
            elif "Head" in q: out["goals_head"] += 1
            elif "OtherBodyPart" in q: out["goals_other"] += 1
        if not _is_normal_shot(event, q):
            continue
        out["shots"] += 1
        if etype == "Goal" or (etype == "SavedShot" and "Blocked" not in q): out["shots_on_target"] += 1
        elif etype in {"MissedShots", "ShotOnPost"}: out["shots_off_target"] += 1
        elif etype == "SavedShot" and "Blocked" in q: out["blocked_shots"] += 1
        if etype == "ShotOnPost": out["shots_woodwork"] += 1
        if "RegularPlay" in q: out["shots_open_play"] += 1
        if "DirectFreekick" in q: out["shots_direct_free_kick"] += 1
        if (q & SET_PIECE_QUALIFIERS) and "Penalty" not in q: out["shots_from_set_pieces"] += 1
        if "FastBreak" in q: out["shots_fast_break"] += 1
        if _has_prefix(q, "SmallBox"): out["shots_6_yard_box"] += 1
        elif _has_prefix(q, "OutOfBox", "ThirtyFivePlus"): out["shots_outside_box"] += 1
        elif _has_prefix(q, "Box", "DeepBox"): out["shots_penalty_area"] += 1
        if "RightFoot" in q: out["shots_right_foot"] += 1
        elif "LeftFoot" in q: out["shots_left_foot"] += 1
        elif "Head" in q: out["shots_head"] += 1
        elif "OtherBodyPart" in q: out["shots_other"] += 1
    return dict(out)
