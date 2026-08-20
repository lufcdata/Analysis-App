"""Canonical discipline metrics from raw provider event semantics."""

CARD_EVENT_TYPE_ID = 17
SECOND_YELLOW_QUALIFIER_ID = 32
STRAIGHT_RED_QUALIFIER_ID = 33
DISMISSAL_QUALIFIER_IDS = {SECOND_YELLOW_QUALIFIER_ID, STRAIGHT_RED_QUALIFIER_ID}

def _numeric_id(value):
    if isinstance(value, dict): value = value.get("id")
    try: return int(value)
    except (TypeError, ValueError): return None

def _qualifier_ids(event):
    ids = set()
    for qualifier in event.get("qualifiers") or []:
        if not isinstance(qualifier, dict): continue
        qid = _numeric_id(qualifier.get("type"))
        if qid is None: qid = _numeric_id(qualifier.get("qualifierId", qualifier.get("id")))
        if qid is not None: ids.add(qid)
    return ids

def _is_player_dismissal(event):
    return _numeric_id(event.get("type")) == CARD_EVENT_TYPE_ID and bool(_qualifier_ids(event) & DISMISSAL_QUALIFIER_IDS)

def calculate_discipline_metrics(events, team_id=None, player_id=None, roster_player_ids=None, **_):
    if player_id is not None:
        return {"red_cards": sum(1 for event in events or [] if event.get("teamId") == team_id and event.get("playerId") == player_id and _is_player_dismissal(event))}
    if team_id is None or roster_player_ids is None: return {}
    roster = {str(value) for value in roster_player_ids if value is not None}
    return {"red_cards": sum(1 for event in events or [] if event.get("teamId") == team_id and event.get("playerId") is not None and str(event.get("playerId")) in roster and _is_player_dismissal(event))}
