from __future__ import annotations

from typing import Any

FIRST_HALF_NAMES = ("FirstHalf", "1H", "first_half")
SECOND_HALF_NAMES = ("SecondHalf", "2H", "second_half")


def format_match_clock(total_seconds: int | float | None) -> str | None:
    if total_seconds is None:
        return None
    seconds = max(0, int(total_seconds))
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes}:{remainder:02d}"


def _period_bounds(conn, match_id: str, period_names: tuple[str, ...]) -> tuple[int | None, int | None]:
    marks = ",".join("?" for _ in period_names)
    row = conn.execute(
        f"""SELECT MIN(time_seconds), MAX(time_seconds)
            FROM match_events
            WHERE match_id=? AND period IN ({marks}) AND time_seconds IS NOT NULL""",
        [match_id, *period_names],
    ).fetchone()
    if not row:
        return None, None
    start, end = row
    return (int(start) if start is not None else None,
            int(end) if end is not None else None)


def get_match_timing(conn, match_id: str) -> dict[str, Any]:
    first_start, first_end = _period_bounds(conn, match_id, FIRST_HALF_NAMES)
    second_start, second_end = _period_bounds(conn, match_id, SECOND_HALF_NAMES)
    row = conn.execute(
        """SELECT MIN(time_seconds), MAX(time_seconds), COUNT(*)
           FROM match_events
           WHERE match_id=? AND time_seconds IS NOT NULL""",
        [match_id],
    ).fetchone()
    match_start, full_time, timed_events = row if row else (None, None, 0)
    match_start = int(match_start) if match_start is not None else None
    full_time = int(full_time) if full_time is not None else None
    timing_complete = first_end is not None and second_start is not None and second_end is not None
    return {
        "match_start_seconds": match_start,
        "first_half_start_seconds": first_start,
        "first_half_end_seconds": first_end,
        "second_half_start_seconds": second_start,
        "second_half_end_seconds": second_end,
        "full_time_seconds": full_time,
        "match_start_display": format_match_clock(match_start),
        "first_half_end_display": format_match_clock(first_end),
        "second_half_start_display": format_match_clock(second_start),
        "second_half_end_display": format_match_clock(second_end),
        "full_time_display": format_match_clock(full_time),
        "timed_event_count": int(timed_events or 0),
        "timing_complete": bool(timing_complete),
        "source": "match_events.time_seconds",
    }
