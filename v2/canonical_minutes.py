"""Canonical player active-time and per-90 helpers."""
from typing import Dict, Iterable, Optional, Tuple

NORMAL_PERIODS = {"FirstHalf", "SecondHalf"}
PERCENTAGE_KEYS = {"pass_accuracy_percent", "save_percentage_percent", "possession"}


def _dn(value):
    return value.get("displayName") if isinstance(value, dict) else value


def _clock_seconds(event: Dict) -> float:
    minute = event.get("expandedMinute", event.get("minute", 0)) or 0
    second = event.get("second", 0) or 0
    return float(minute) * 60.0 + float(second)


def match_end_seconds(events: Iterable[Dict]) -> float:
    end_seconds = 0.0
    max_seconds = 0.0
    for event in events or []:
        t = _clock_seconds(event)
        max_seconds = max(max_seconds, t)
        if _dn(event.get("type")) == "End" and _dn(event.get("period")) in {"SecondHalf", "PostGame"}:
            end_seconds = max(end_seconds, t)
    return end_seconds or max(max_seconds, 90.0 * 60.0)


def player_active_window_seconds(events: Iterable[Dict], team_id, player_id, is_starter: bool) -> Optional[Tuple[float, float]]:
    on_times = []
    off_times = []
    all_events = list(events or [])
    for event in all_events:
        if event.get("teamId") != team_id or event.get("playerId") != player_id:
            continue
        etype = _dn(event.get("type"))
        if etype == "SubstitutionOn":
            on_times.append(_clock_seconds(event))
        elif etype == "SubstitutionOff":
            off_times.append(_clock_seconds(event))
    if is_starter:
        on = 0.0
    elif on_times:
        on = min(on_times)
    else:
        return None
    full_time = match_end_seconds(all_events)
    valid_offs = [t for t in off_times if t >= on]
    off = min(valid_offs) if valid_offs else full_time
    off = min(off, full_time)
    if off < on:
        return None
    return on, off


def minutes_played(events: Iterable[Dict], team_id, player_id, is_starter: bool) -> float:
    window = player_active_window_seconds(events, team_id, player_id, is_starter)
    if window is None:
        return 0.0
    on, off = window
    return round((off - on) / 60.0, 3)


def per_90(value, mins_played: float, metric_key: str):
    if metric_key in PERCENTAGE_KEYS:
        return value
    if value is None or mins_played is None or mins_played <= 0:
        return None
    return value / mins_played * 90.0
