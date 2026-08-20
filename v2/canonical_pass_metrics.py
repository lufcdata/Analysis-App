"""Bible-conformant pass-family calculations used by the Aug 18 metric registry."""
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, Optional, Tuple

FINAL_THIRD_X = Decimal(200) / Decimal(3)
PENALTY_BOX_X_MIN = Decimal("83.0")
PENALTY_BOX_X_MAX = Decimal("100.0")
PENALTY_BOX_Y_MIN = Decimal("21.1")
PENALTY_BOX_Y_MAX = Decimal("78.9")
DIRECTION_BOUNDARY = Decimal("2.0")
NORMAL_PERIODS = {"FirstHalf", "SecondHalf"}
PASS_EVENT_TYPE_ID = 1
LONGBALL_QUALIFIER_ID = 1
CROSS_QUALIFIER_ID = 2
THROW_IN_QUALIFIER_ID = 107


def _display_name(container: object) -> str:
    if isinstance(container, dict):
        return str(container.get("displayName", container.get("value", "")))
    return str(container or "")


def _numeric_id(value) -> Optional[int]:
    if isinstance(value, dict):
        value = value.get("id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal(value) -> Optional[Decimal]:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _is_pass(event: Dict) -> bool:
    return _numeric_id(event.get("type")) == PASS_EVENT_TYPE_ID or _display_name(event.get("type")) == "Pass"


def _is_normal_period(event: Dict) -> bool:
    return _display_name(event.get("period")) in NORMAL_PERIODS


def _is_successful(event: Dict) -> bool:
    outcome = event.get("outcomeType")
    if isinstance(outcome, dict):
        outcome_id = _numeric_id(outcome)
        if outcome_id is not None:
            return outcome_id == 1
        return _display_name(outcome).lower() == "successful"
    return outcome == 1 or str(outcome).lower() == "successful"


def _qualifier_ids(event: Dict):
    ids = set()
    for qualifier in event.get("qualifiers", []) or []:
        if not isinstance(qualifier, dict):
            continue
        qid = _numeric_id(qualifier.get("type"))
        if qid is None:
            qid = _numeric_id(qualifier.get("qualifierId", qualifier.get("id")))
        if qid is not None:
            ids.add(qid)
    return ids


def _pass_end(event: Dict) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    end_x = end_y = None
    for qualifier in event.get("qualifiers", []):
        if not isinstance(qualifier, dict):
            continue
        name = _display_name(qualifier.get("type"))
        if name == "PassEndX":
            end_x = _decimal(qualifier.get("value"))
        elif name == "PassEndY":
            end_y = _decimal(qualifier.get("value"))
    return end_x, end_y


def _stable_event_id(event: Dict, fallback_index: int) -> object:
    for key in ("eventId", "id"):
        value = event.get(key)
        if value is not None:
            return (key, value)
    return ("fallback", fallback_index)


def _canonical_pass_events(events: Iterable[Dict], team_id=None, player_id=None):
    seen = set()
    for index, event in enumerate(events or []):
        if not _is_pass(event) or not _is_normal_period(event):
            continue
        if team_id is not None and event.get("teamId") != team_id:
            continue
        if player_id is not None and event.get("playerId") != player_id:
            continue
        event_id = _stable_event_id(event, index)
        if event_id in seen:
            continue
        seen.add(event_id)
        yield event


def _canonical_passes(events: Iterable[Dict], team_id=None, player_id=None):
    for event in _canonical_pass_events(events, team_id, player_id):
        end_x, end_y = _pass_end(event)
        if end_x is None or end_y is None:
            continue
        yield event, end_x, end_y


def _canonical_long_passes(events: Iterable[Dict], team_id=None, player_id=None):
    for event in _canonical_pass_events(events, team_id, player_id):
        qualifier_ids = _qualifier_ids(event)
        if LONGBALL_QUALIFIER_ID not in qualifier_ids:
            continue
        if CROSS_QUALIFIER_ID in qualifier_ids or THROW_IN_QUALIFIER_ID in qualifier_ids:
            continue
        yield event


def count_long_passes(events: Iterable[Dict], team_id=None, player_id=None) -> int:
    return sum(1 for _ in _canonical_long_passes(events, team_id, player_id))


def count_accurate_long_passes(events: Iterable[Dict], team_id=None, player_id=None) -> int:
    return sum(1 for event in _canonical_long_passes(events, team_id, player_id) if _is_successful(event))


def count_unsuccessful_long_passes(events: Iterable[Dict], team_id=None, player_id=None) -> int:
    return sum(1 for event in _canonical_long_passes(events, team_id, player_id) if not _is_successful(event))


def count_successful_passes_into_final_third(events: Iterable[Dict], team_id=None, player_id=None) -> int:
    total = 0
    for event, end_x, _ in _canonical_passes(events, team_id, player_id):
        start_x = _decimal(event.get("x"))
        if start_x is not None and start_x < FINAL_THIRD_X and end_x >= FINAL_THIRD_X and _is_successful(event):
            total += 1
    return total


def count_successful_final_third_passes(events: Iterable[Dict], team_id=None, player_id=None) -> int:
    return sum(1 for event, end_x, _ in _canonical_passes(events, team_id, player_id) if end_x >= FINAL_THIRD_X and _is_successful(event))


def count_successful_passes_in_penalty_box(events: Iterable[Dict], team_id=None, player_id=None) -> int:
    return sum(
        1 for event, end_x, end_y in _canonical_passes(events, team_id, player_id)
        if PENALTY_BOX_X_MIN <= end_x <= PENALTY_BOX_X_MAX and PENALTY_BOX_Y_MIN <= end_y <= PENALTY_BOX_Y_MAX and _is_successful(event)
    )


def _direction_counts(events: Iterable[Dict], team_id=None, player_id=None):
    forward = backward = side = 0
    for event, end_x, _ in _canonical_passes(events, team_id, player_id):
        start_x = _decimal(event.get("x"))
        if start_x is None:
            continue
        delta_x = end_x - start_x
        if delta_x >= DIRECTION_BOUNDARY:
            forward += 1
        elif delta_x <= -DIRECTION_BOUNDARY:
            backward += 1
        else:
            side += 1
    return forward, backward, side


def calculate_pass_metrics(events, team_id=None, player_id=None):
    forward, backward, side = _direction_counts(events, team_id, player_id)
    return {
        "forward_passes": forward,
        "backward_passes": backward,
        "side_passes": side,
        "long_passes": count_long_passes(events, team_id, player_id),
        "accurate_long_passes": count_accurate_long_passes(events, team_id, player_id),
        "unsuccessful_long_passes": count_unsuccessful_long_passes(events, team_id, player_id),
        "successful_final_third_passes": count_successful_final_third_passes(events, team_id, player_id),
        "successful_passes_into_penalty_box": count_successful_passes_in_penalty_box(events, team_id, player_id),
    }
