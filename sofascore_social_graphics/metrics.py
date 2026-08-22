from __future__ import annotations

import re
from typing import Any

# GOLDEN MATCHLAB METRIC MAP.
# Left side is the MatchLab display label. Right side identifies the SofaScore
# stat/metric (or a very similar provider label/key). No V2/canonical metric
# definitions and no historical metric-count contract are used here.
METRICS: list[dict[str, Any]] = [
    {"label": "Goals", "sofascore": "Goals", "match_keys": ["goals"], "player_keys": ["goals"]},
    {"label": "xG", "sofascore": "Expected Goals (xG)", "match_aliases": ["Expected goals"], "match_keys": ["expectedGoals"], "player_keys": ["expectedGoals", "expectedGoalsValue"]},
    {"label": "Possession", "sofascore": "Ball Possession", "match_aliases": ["Ball possession"], "match_keys": ["ballPossession"], "player_keys": ["ballPossession", "possession"]},
    {"label": "Touches", "sofascore": "Touches in opposition box", "match_aliases": ["Touches in Opposition Box"], "match_keys": ["touchesInOppBox", "touchesInOppositionBox"], "player_keys": ["touchesInOppBox", "touchesInOppositionBox"]},
    {"label": "Opposition Box Touches", "sofascore": "Penalty Box Touches", "match_aliases": ["Penalty box touches", "Touches in penalty area", "Touches in penalty box", "Touches inside opposition box"], "match_keys": ["penaltyBoxTouches", "touchesInPenaltyArea", "touchesInPenaltyBox", "touchesInsideOppositionBox"], "player_keys": ["penaltyBoxTouches", "touchesInPenaltyArea"]},
    {"label": "Shots", "sofascore": "Total Shots", "match_aliases": ["Total shots"], "match_keys": ["totalShotsOnGoal", "totalShots"], "player_keys": ["totalShots"]},
    {"label": "Shots On-Target", "sofascore": "Shots on target", "match_keys": ["shotsOnGoal", "shotsOnTarget"], "player_keys": ["onTargetScoringAttempt", "shotsOnTarget"]},
    {"label": "Shots Outside Box", "sofascore": "Shots outside box", "match_keys": ["totalShotsOutsideBox", "shotsOutsideBox"], "player_keys": ["shotFromOutsideTheBox", "shotsOutsideBox", "shotsFromOutsideTheBox"]},
    {"label": "Big Chances", "sofascore": "Big Chances", "match_aliases": ["Big chances"], "match_keys": ["bigChanceCreated", "bigChances"], "player_keys": ["bigChances", "bigChance", "bigChanceCreated"]},
    {"label": "Chances Created", "sofascore": "Key Passes", "match_aliases": ["Key passes", "Key Pass", "Chances created"], "match_keys": ["keyPasses", "keyPass", "chancesCreated"], "player_keys": ["keyPass", "keyPasses", "chancesCreated"]},
    {"label": "Successful Passes", "sofascore": "Accurate Passes", "match_aliases": ["Accurate passes"], "match_keys": ["accuratePasses"], "player_keys": ["accuratePass", "accuratePasses"]},
    {"label": "Total Passes", "sofascore": "Passes", "match_aliases": ["Total passes"], "match_keys": ["passes", "totalPasses"], "player_keys": ["totalPass", "totalPasses"]},
    {"label": "Successful Final Third Passes", "sofascore": "Passes In Final Third", "match_aliases": ["Passes in final third"], "match_keys": ["finalThirdPhaseStatistic", "accurateFinalThirdPasses", "passesInFinalThird"], "player_keys": ["accurateFinalThirdPasses", "successfulFinalThirdPasses"]},
    {"label": "Pass Accuracy", "sofascore": "Pass Accuracy", "match_aliases": ["Pass accuracy", "Passing accuracy", "Accurate passes percentage", "Accurate passes %"], "match_keys": ["passAccuracy", "accuratePassesPercentage", "accuratePassPercentage", "passAccuracyPercentage"], "player_keys": ["passAccuracy", "accuratePassPercentage", "accuratePassesPercentage"], "suffix": "%"},
    {"label": "Ball Carries", "sofascore": "Carries", "match_aliases": ["Ball carries", "Total carries"], "match_keys": ["ballCarriesCount", "ballCarries", "carries", "totalCarries"], "player_keys": ["ballCarriesCount", "ballCarries", "carries", "totalCarries"]},
    {"label": "Progressive Carries", "sofascore": "Progressive Carries", "match_aliases": ["Progressive carries", "Progressive ball carries"], "match_keys": ["progressiveBallCarriesCount", "progressiveBallCarries", "progressiveCarries"], "player_keys": ["progressiveBallCarriesCount", "progressiveBallCarries", "progressiveCarries"]},
    {"label": "Progressive Carrying Distance (m)", "sofascore": "Progressive Carrying Distance", "match_aliases": ["Progressive carrying distance", "Progressive carry distance", "Progressive ball carries distance"], "match_keys": ["totalProgressiveBallCarriesDistance", "progressiveBallCarriesDistance", "progressiveCarryingDistance", "progressiveCarryDistance"], "player_keys": ["totalProgressiveBallCarriesDistance", "progressiveBallCarriesDistance", "progressiveCarryingDistance", "progressiveCarryDistance"]},
    {"label": "Accurate Long Passes", "sofascore": "Long Balls", "match_aliases": ["Long balls", "Accurate long balls"], "match_keys": ["accurateLongBalls"], "player_keys": ["accurateLongBalls"]},
    {"label": "Final Third Entries", "sofascore": "Final Third Entries", "match_aliases": ["Final third entries"], "match_keys": ["finalThirdEntries"], "player_keys": ["finalThirdEntries"]},
    {"label": "Accurate Crosses", "sofascore": "Crosses", "match_aliases": ["Accurate crosses"], "match_keys": ["accurateCross", "accurateCrosses"], "player_keys": ["accurateCross", "accurateCrosses"]},
    {"label": "Ground Duels Won", "sofascore": "Ground Duels", "match_aliases": ["Ground duels"], "match_keys": ["groundDuelsPercentage", "groundDuelsWon"], "player_keys": ["groundDuelWon", "groundDuelsWon"]},
    {"label": "Aerial Duels Won", "sofascore": "Aerial Duels", "match_aliases": ["Aerial duels"], "match_keys": ["aerialDuelsPercentage", "aerialDuelsWon"], "player_keys": ["aerialWon", "aerialDuelsWon"]},
    {"label": "Duels Won", "sofascore": "Duels", "match_aliases": ["Duels won"], "match_keys": ["duelWonPercent", "duelsWon"], "player_keys": ["duelWon", "totalDuelsWon"]},
    {"label": "Ball Recoveries", "sofascore": "Recoveries", "match_aliases": ["Ball recoveries", "Recoveries"], "match_keys": ["ballRecovery"], "player_keys": ["ballRecovery"]},
    {"label": "Successful Take-Ons", "sofascore": "Dribbles", "match_aliases": ["Successful dribbles", "Dribbles"], "match_keys": ["dribblesPercentage", "successfulDribbles"], "player_keys": ["wonContest", "successfulDribbles"]},
    {"label": "Tackles Won", "sofascore": "Tackles Won", "match_aliases": ["Tackles won"], "match_keys": ["wonTacklePercent", "wonTackle", "tacklesWon"], "player_keys": ["wonTackle", "tacklesWon", "totalTackle"]},
    {"label": "Interceptions", "sofascore": "Interceptions", "match_keys": ["interceptionWon", "interceptions"], "player_keys": ["interceptionWon", "interceptions"]},
    {"label": "Clearances", "sofascore": "Clearances", "match_keys": ["totalClearance", "clearances"], "player_keys": ["totalClearance", "clearances"]},
    {"label": "Fouls", "sofascore": "Fouls", "match_keys": ["fouls"], "player_keys": ["fouls"]},
    {"label": "Fouled", "sofascore": "Was Fouled", "match_aliases": ["Was fouled"], "match_keys": ["wasFouled"], "player_keys": ["wasFouled"]},
    {"label": "Possession Lost", "sofascore": "Possession Lost", "match_aliases": ["Possession lost"], "match_keys": ["possessionLost", "dispossessed"], "player_keys": ["possessionLostCtrl", "possessionLost"]},
    {"label": "Corners", "sofascore": "Corner Kicks", "match_aliases": ["Corner kicks"], "match_keys": ["cornerKicks", "corners"], "player_keys": []},
    {"label": "Saves", "sofascore": "Goalkeeper Saves", "match_aliases": ["Goalkeeper saves"], "match_keys": ["goalkeeperSaves", "saves"], "player_keys": ["saves"]},
    {"label": "Assists", "sofascore": "Assists", "match_keys": ["assists"], "player_keys": ["goalAssist", "assists"]},
    {"label": "Penalties Won", "sofascore": "Penalties Won", "match_aliases": ["Penalties won"], "match_keys": ["penaltiesWon", "penaltyWon"], "player_keys": ["penaltyWon", "penaltiesWon"]},
    {"label": "Saves From Inside Box", "sofascore": "Saves From Inside Box", "match_aliases": ["Saves from inside box", "Saves inside box"], "match_keys": ["savedShotsFromInsideTheBox", "savesFromInsideBox"], "player_keys": ["savedShotsFromInsideTheBox"]},
    {"label": "High Claims", "sofascore": "High Claims", "match_aliases": ["High claims"], "match_keys": ["highClaims", "goodHighClaim"], "player_keys": ["highClaims", "goodHighClaim"]},
    {"label": "Red Cards", "sofascore": "Red Cards", "match_aliases": ["Red cards"], "match_keys": ["redCards"], "player_keys": ["redCards", "redCard", "directRedCards"]},
    {"label": "Defensive Actions", "sofascore": "Def. Contribution", "match_aliases": ["Defensive contribution", "Def. contribution"], "match_keys": ["defensiveContribution"], "player_keys": ["defensiveContribution"]},
]

METRIC_BY_LABEL = {m["label"]: m for m in METRICS}


def metric_key(label: str) -> str:
    return "_".join("".join(ch.lower() if ch.isalnum() else " " for ch in label).split())


def _norm(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^A-Za-z0-9]+", " ", text)
    return " ".join(text.lower().split())


def canonical_match_label(raw_name: str, raw_key: str | None = None) -> str | None:
    needles = {_norm(raw_name), _norm(raw_key)} - {""}
    for metric in METRICS:
        candidates = [metric.get("sofascore"), *metric.get("match_aliases", [])]
        candidates.extend(metric.get("match_keys", []))
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
        rows.append({"key": metric_key(metric["label"]), "label": metric["label"], "display": format_player_metric(stats, metric, value), "rank": value, "value": value})
    return rows, stats.get("minutesPlayed")
