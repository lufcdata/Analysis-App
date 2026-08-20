"""Locked Open-Play Progressive Passes calculation."""
from __future__ import annotations

from decimal import Decimal
from math import hypot
from typing import Dict, Iterable, Iterator, Tuple

from .canonical_pass_metrics import _canonical_passes, _decimal, _display_name, _is_successful

DEFENSIVE_THIRD_GATE = Decimal(100) / Decimal(3)
PITCH_X_SCALE_M = Decimal("1.05")
PITCH_Y_SCALE_M = Decimal("0.68")
GOAL_X = Decimal("100")
GOAL_Y = Decimal("50")
PROGRESSION_THRESHOLD_M = 9.144
RESTART_TAKING_QUALIFIERS = {"freekicktaken", "cornertaken", "throwin", "goalkicktaken", "penaltytaken"}


def _normalise_qualifier_name(value: object) -> str:
    return "".join(ch for ch in _display_name(value).casefold() if ch.isalnum())


def _is_explicit_restart_pass(event: Dict) -> bool:
    for qualifier in event.get("qualifiers", []) or []:
        if not isinstance(qualifier, dict):
            continue
        if _normalise_qualifier_name(qualifier.get("type")) in RESTART_TAKING_QUALIFIERS:
            return True
    return False


def _distance_to_goal_m(x: Decimal, y: Decimal) -> float:
    dx = float((GOAL_X - x) * PITCH_X_SCALE_M)
    dy = float((GOAL_Y - y) * PITCH_Y_SCALE_M)
    return hypot(dx, dy)


def iter_progressive_passes(events: Iterable[Dict], team_id=None, player_id=None) -> Iterator[Tuple[Dict, Decimal, Decimal]]:
    for event, end_x, end_y in _canonical_passes(events, team_id, player_id):
        if not _is_successful(event) or _is_explicit_restart_pass(event):
            continue
        start_x = _decimal(event.get("x"))
        start_y = _decimal(event.get("y"))
        if start_x is None or start_y is None:
            continue
        if start_x < DEFENSIVE_THIRD_GATE:
            continue
        start_distance = _distance_to_goal_m(start_x, start_y)
        end_distance = _distance_to_goal_m(end_x, end_y)
        if start_distance - end_distance >= PROGRESSION_THRESHOLD_M:
            yield event, end_x, end_y


def count_progressive_passes(events: Iterable[Dict], team_id=None, player_id=None) -> int:
    return sum(1 for _ in iter_progressive_passes(events, team_id=team_id, player_id=player_id))


def calculate_progressive_pass_metrics(events, team_id=None, player_id=None):
    return {"progressive_passes": count_progressive_passes(events, team_id=team_id, player_id=player_id)}
