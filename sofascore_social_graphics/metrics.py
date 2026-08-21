from __future__ import annotations

from typing import Any

# Canonical MatchLab metric dictionary.
#
# `label` is the ONLY public-facing name used by MatchLab. SofaScore names and
# lineup keys are ingestion aliases only. Player Stats and Metric Leaders both
# read from this dictionary so a rename here propagates everywhere.
METRICS: list[dict[str, Any]] = [
    {"label": "Goals", "sofascore": "Goals", "player_keys": ["goals"]},
    {"label": "Assists", "sofascore": "Assists", "player_keys": ["goalAssist"]},
    {"label": "xG", "sofascore": "Expected Goals (xG)", "player_keys": ["expectedGoals", "expectedGoalsValue"]},
    {"label": "Possession", "sofascore": "Ball Possession", "player_keys": []},
    {"label": "Touches", "sofascore": "Touches", "player_keys": ["touches"]},
    {"label": "Opposition Box Touches", "sofascore": "Penalty Box Touches", "player_keys": ["touchesInOppBox", "touchesInOppositionBox", "penaltyBoxTouches"]},
    {"label": "Shots", "sofascore": "Total Shots", "player_keys": ["totalShots"]},
    {"label": "Shots On-Target", "sofascore": "Shots on target", "player_keys": ["onTargetScoringAttempt"]},
    {"label": "Shots Off-Target", "sofascore": "Shots off target", "player_keys": ["shotOffTarget"]},
    {"label": "Shots Blocked", "sofascore": "Blocked shots", "player_keys": ["blockedScoringAttempt"]},
    {"label": "Shots Outside Box", "sofascore": "Shots outside box", "player_keys": ["shotFromOutsideTheBox", "shotsOutsideBox"]},
    {"label": "Big Chances", "sofascore": "Big Chances", "player_keys": ["bigChanceCreated", "bigChanceMissed"]},
    {"label": "Big Chances Created", "sofascore": "Big Chances Created", "player_keys": ["bigChanceCreated"]},
    {"label": "Big Chances Missed", "sofascore": "Big Chances Missed", "player_keys": ["bigChanceMissed"]},
    {"label": "Chances Created", "sofascore": "Key Passes", "player_keys": ["keyPass"]},
    {"label": "Successful Passes", "sofascore": "Accurate Passes", "player_keys": ["accuratePass"], "total_key": "totalPass", "display_pair": True},
    {"label": "Total Passes", "sofascore": "Passes", "player_keys": ["totalPass"]},
    {"label": "Successful Final Third Passes", "sofascore": "Passes In Final Third", "player_keys": ["accurateFinalThirdPasses", "successfulFinalThirdPasses"]},
    {"label": "Pass Accuracy", "sofascore": "Pass Accuracy", "calculation": "pass_accuracy", "player_keys": ["accuratePass", "totalPass"], "suffix": "%"},
    {"label": "Ball Carries", "sofascore": "Carries", "player_keys": ["carries", "totalCarries"]},
    {"label": "Progressive Carries", "sofascore": "Progressive Carries", "player_keys": ["progressiveCarries"]},
    {"label": "Progressive Carrying Distance (m)", "sofascore": "Progressive Carrying Distance", "player_keys": ["progressiveCarryingDistance"]},
    {"label": "Accurate Long Passes", "sofascore": "Long Balls", "player_keys": ["accurateLongBalls"], "total_key": "totalLongBalls", "display_pair": True},
    {"label": "Final Third Entries", "sofascore": "Final Third Entries", "player_keys": ["finalThirdEntries"]},
    {"label": "Accurate Crosses", "sofascore": "Crosses", "player_keys": ["accurateCross"], "total_key": "totalCross", "display_pair": True},
    {"label": "Ground Duels Won", "sofascore": "Ground Duels", "player_keys": ["groundDuelWon"]},
    {"label": "Aerial Duels Won", "sofascore": "Aerial Duels", "player_keys": ["aerialWon"]},
    {"label": "Duels Won", "sofascore": "Duels", "player_keys": ["duelWon"]},
    {"label": "Ball Recoveries", "sofascore": "Recoveries", "player_keys": ["ballRecovery"]},
    {"label": "Successful Take-Ons", "sofascore": "Dribbles", "player_keys": ["wonContest"], "total_key": "totalContest", "display_pair": True},
    {"label": "Tackles Won", "sofascore": "Tackles Won", "player_keys": ["totalTackle", "tacklesWon"]},
    {"label": "Interceptions", "sofascore": "Interceptions", "player_keys": ["interceptionWon"]},
    {"label": "Blocks", "sofascore": "Blocks", "player_keys": ["outfielderBlock"]},
    {"label": "Clearances", "sofascore": "Clearances", "player_keys": ["totalClearance"]},
    {"label": "Fouls", "sofascore": "Fouls", "player_keys": ["fouls"]},
    {"label": "Fouled", "sofascore": "Was Fouled", "player_keys": ["wasFouled"]},
    {"label": "Possession Lost", "sofascore": "Possession Lost", "player_keys": ["possessionLostCtrl"]},
    {"label": "Corners", "sofascore": "Corner Kicks", "player_keys": []},
    {"label": "Saves", "sofascore": "Goalkeeper Saves", "player_keys": ["saves"]},
    {"label": "Saves Inside Box", "sofascore": "Saves inside box", "player_keys": ["savedShotsFromInsideTheBox"]},
    {"label": "Goals Prevented", "sofascore": "Goals prevented", "player_keys": ["goalsPrevented"]},
]

METRIC_BY_LABEL = {m["label"]: m for m in METRICS}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def player_metric_value(stats: dict[str, Any], metric: dict[str, Any]) -> float | None:
    calc = metric.get("calculation")
    if calc == "pass_accuracy":
        accurate = _number(stats.get("accuratePass"))
        total = _number(stats.get("totalPass"))
        if accurate is None or total in (None, 0):
            return None
        return (accurate / total) * 100.0

    if metric.get("label") == "Big Chances":
        values = [_number(stats.get(k)) for k in metric.get("player_keys", [])]
        present = [v for v in values if v is not None]
        return sum(present) if present else None

    for key in metric.get("player_keys", []):
        value = _number(stats.get(key))
        if value is not None:
            return value
    return None


def format_metric_value(value: float, metric: dict[str, Any]) -> str:
    if metric.get("suffix") == "%":
        return f"{value:.1f}%"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def format_player_metric(stats: dict[str, Any], metric: dict[str, Any], value: float) -> str:
    if metric.get("display_pair") and metric.get("total_key"):
        total = _number(stats.get(metric["total_key"]))
        if total is not None:
            return f"{int(value)}/{int(total)}"
    return format_metric_value(value, metric)


def available_player_metrics(players) -> list[dict[str, Any]]:
    available: list[dict[str, Any]] = []
    for metric in METRICS:
        if not metric.get("player_keys"):
            continue
        if any(player_metric_value(p.stats, metric) is not None for p in players):
            available.append(metric)
    return available


def build_canonical_player_rows(stats: dict[str, Any], hide_zero: bool = True) -> tuple[list[dict[str, Any]], Any]:
    """Build Player Stats rows from the same canonical dictionary as Metric Leaders."""
    rows: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for metric in METRICS:
        if not metric.get("player_keys"):
            continue
        value = player_metric_value(stats, metric)
        if value is None or (hide_zero and value == 0):
            continue
        label = metric["label"]
        if label in seen_labels:
            continue
        rows.append({
            "label": label,
            "display": format_player_metric(stats, metric, value),
            "rank": value,
        })
        seen_labels.add(label)
    return rows, stats.get("minutesPlayed")
