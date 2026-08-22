from __future__ import annotations

import re
from typing import Any

# GOLDEN MATCHLAB METRIC MAP.
# Left side is the MatchLab display label. Right side identifies the SofaScore
# stat/metric (or a very similar provider label/key). No V2/canonical metric
# definitions and no historical metric-count contract are used here.
METRICS: list[dict[str, Any]] = [
    {"label": "Goals", "sofascore": "Goals", "player_keys": ["goals"]},
    {"label": "xG", "sofascore": "Expected Goals (xG)", "match_aliases": ["Expected goals"], "player_keys": ["expectedGoals", "expectedGoalsValue"]},
    {"label": "Possession", "sofascore": "Ball Possession", "match_aliases": ["Ball possession"], "player_keys": ["ballPossession", "possession"]},
    {"label": "Touches", "sofascore": "Touches in opposition box", "match_aliases": ["Touches in Opposition Box"], "player_keys": ["touchesInOppBox", "touchesInOppositionBox"]},
    {"label": "Opposition Box Touches", "sofascore": "Penalty Box Touches", "match_aliases": ["Penalty box touches"], "player_keys": ["penaltyBoxTouches"]},
    {"label": "Shots", "sofascore": "Total Shots", "match_aliases": ["Total shots"], "player_keys": ["totalShots"]},
    {"label": "Shots On-Target", "sofascore": "Shots on target", "player_keys": ["onTargetScoringAttempt"]},
    {"label": "Shots Outside Box", "sofascore": "Shots outside box", "player_keys": ["shotFromOutsideTheBox", "shotsOutsideBox"]},
    {"label": "Big Chances", "sofascore": "Big Chances", "match_aliases": ["Big chances"], "player_keys": ["bigChances", "bigChance"]},
    {"label": "Chances Created", "sofascore": "Key Passes", "match_aliases": ["Key passes"], "player_keys": ["keyPass"]},
    {"label": "Successful Passes", "sofascore": "Accurate Passes", "match_aliases": ["Accurate passes"], "player_keys": ["accuratePass"]},
    {"label": "Total Passes", "sofascore": "Passes", "match_aliases": ["Total passes"], "player_keys": ["totalPass"]},
    {"label": "Successful Final Third Passes", "sofascore": "Passes In Final Third", "match_aliases": ["Passes in final third"], "player_keys": ["accurateFinalThirdPasses", "successfulFinalThirdPasses"]},
    {"label": "Pass Accuracy", "sofascore": "Pass Accuracy", "match_aliases": ["Pass accuracy"], "player_keys": ["passAccuracy", "accuratePassPercentage"], "suffix": "%"},
    {"label": "Ball Carries", "sofascore": "Carries", "player_keys": ["carries", "totalCarries"]},
    {"label": "Progressive Carries", "sofascore": "Progressive Carries", "player_keys": ["progressiveCarries"]},
    {"label": "Progressive Carrying Distance (m)", "sofascore": "Progressive Carrying Distance", "player_keys": ["progressiveCarryingDistance"]},
    {"label": "Accurate Long Passes", "sofascore": "Long Balls", "match_aliases": ["Long balls"], "player_keys": ["accurateLongBalls"]},
    {"label": "Final Third Entries", "sofascore": "Final Third Entries", "match_aliases": ["Final third entries"], "player_keys": ["finalThirdEntries"]},
    {"label": "Accurate Crosses", "sofascore": "Crosses", "player_keys": ["accurateCross"]},
    {"label": "Ground Duels Won", "sofascore": "Ground Duels", "match_aliases": ["Ground duels"], "player_keys": ["groundDuelWon"]},
    {"label": "Aerial Duels Won", "sofascore": "Aerial Duels", "match_aliases": ["Aerial duels"], "player_keys": ["aerialWon"]},
    {"label": "Duels Won", "sofascore": "Duels", "player_keys": ["duelWon"]},
    {"label": "Ball Recoveries", "sofascore": "Recoveries", "match_aliases": ["Ball recoveries"], "player_keys": ["ballRecovery"]},
    {"label": "Successful Take-Ons", "sofascore": "Dribbles", "match_aliases": ["Successful dribbles"], "player_keys": ["wonContest"]},
    {"label": "Tackles Won", "sofascore": "Tackles Won", "match_aliases": ["Tackles won"], "player_keys": ["tacklesWon", "totalTackle"]},
    {"label": "Interceptions", "sofascore": "Interceptions", "player_keys": ["interceptionWon"]},
    {"label": "Clearances", "sofascore": "Clearances", "player_keys": ["totalClearance"]},
    {"label": "Fouls", "sofascore": "Fouls", "player_keys": ["fouls"]},
    {"label": "Fouled", "sofascore": "Was Fouled", "match_aliases": ["Was fouled"], "player_keys": ["wasFouled"]},
    {"label": "Possession Lost", "sofascore": "Possession Lost", "match_aliases": ["Possession lost"], "player_keys": ["possessionLostCtrl"]},
    {"label": "Corners", "sofascore": "Corner Kicks", "match_aliases": ["Corner kicks"], "player_keys": []},
    {"label": "Saves", "sofascore": "Goalkeeper Saves", "match_aliases": ["Goalkeeper saves"], "player_keys": ["saves"]},
    {"label": "Assists", "sofascore": "Assists", "player_keys": ["goalAssist"]},
    {"label": "Penalties Won", "sofascore": "Penalties Won", "match_aliases": ["Penalties won"], "player_keys": ["penaltyWon", "penaltiesWon"]},
    {"label": "Saves From Inside Box", "sofascore": "Saves From Inside Box", "match_aliases": ["Saves from inside box", "Saves inside box"], "player_keys": ["savedShotsFromInsideTheBox"]},
    {"label": "High Claims", "sofascore": "High Claims", "match_aliases": ["High claims"], "player_keys": ["highClaims", "goodHighClaim"]},
    {"label": "Red Cards", "sofascore": "Red Cards", "match_aliases": ["Red cards"], "player_keys": ["redCards", "redCard"]},
    {"label": "Defensive Actions", "sofascore": "Def. Contribution", "match_aliases": ["Defensive contribution"], "player_keys": ["defensiveContribution"]},
]

METRIC_BY_LABEL = {m["label"]: m for m in METRICS}


def metric_key(label: str) -> str:
    return "_".join("".join(ch.lower() if ch.isalnum() else " " for ch in label).split())


def _norm(value: Any) -> str:
    """Normalise SofaScore display labels and camelCase provider keys to the same form."""
    text = str(value or "").strip()
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^A-Za-z0-9]+", " ", text)
    return " ".join(text.lower().split())


def canonical_match_label(raw_name: str, raw_key: str | None = None) -> str | None:
    """Map a SofaScore label/key directly onto the Golden MatchLab display label."""
    needles = {_norm(raw_name), _norm(raw_key)} - {""}
    for metric in METRICS:
        candidates = [metric.get("sofascore"), *metric.get("match_aliases", [])]
        # Provider keys often use camelCase versions of the same SofaScore concept.
        candidates.extend(metric.get("player_keys", []))
        candidate_norms = {_norm(name) for name in candidates if name}
        if needles & candidate_norms:
            return str(metric["label"])
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def player_metric_value(stats: dict[str, Any], metric: dict[str, Any]) -> float | None:
    """Read provider-supplied player values only; no metric re-definition/recalculation."""
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
    return format_metric_value(value, metric)


def available_player_metrics(players) -> list[dict[str, Any]]:
    available: list[dict[str, Any]] = []
    for metric in METRICS:
        if not metric.get("player_keys"):
            continue
        if any(player_metric_value(p.stats, metric) is not None for p in players):
            available.append({**metric, "key": metric_key(metric["label"])})
    return available


def build_canonical_player_rows(stats: dict[str, Any], hide_zero: bool = True) -> tuple[list[dict[str, Any]], Any]:
    rows: list[dict[str, Any]] = []
    for metric in METRICS:
        if not metric.get("player_keys"):
            continue
        value = player_metric_value(stats, metric)
        if value is None or (hide_zero and value == 0):
            continue
        rows.append({
            "key": metric_key(metric["label"]),
            "label": metric["label"],
            "display": format_player_metric(stats, metric, value),
            "rank": value,
            "value": value,
        })
    return rows, stats.get("minutesPlayed")
