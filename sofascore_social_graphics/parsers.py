from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from metrics import format_metric_value, player_metric_value


@dataclass
class MatchInfo:
    event_id: str
    home_name: str
    away_name: str
    home_score: str
    away_score: str
    tournament: str
    date_text: str


@dataclass
class PlayerOption:
    player_id: int | str
    name: str
    team: str
    opponent: str
    side: str
    stats: dict[str, Any]


def parse_match_info(basic_payload: dict[str, Any]) -> MatchInfo:
    event = basic_payload.get("event", basic_payload)
    home = event.get("homeTeam", {})
    away = event.get("awayTeam", {})
    home_score = event.get("homeScore", {}).get("display", event.get("homeScore", {}).get("current", ""))
    away_score = event.get("awayScore", {}).get("display", event.get("awayScore", {}).get("current", ""))
    tournament = (
        event.get("tournament", {}).get("uniqueTournament", {}).get("name")
        or event.get("tournament", {}).get("name")
        or ""
    )
    timestamp = event.get("startTimestamp")
    date_text = ""
    if timestamp:
        date_text = datetime.fromtimestamp(timestamp).strftime("%d %B %Y")

    return MatchInfo(
        event_id=str(event.get("id", "")),
        home_name=home.get("name", "Home"),
        away_name=away.get("name", "Away"),
        home_score=str(home_score),
        away_score=str(away_score),
        tournament=tournament,
        date_text=date_text,
    )


def extract_match_statistics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    periods = payload.get("statistics", [])
    selected = None
    for period in periods:
        if str(period.get("period", "")).upper() == "ALL":
            selected = period
            break
    if selected is None and periods:
        selected = periods[0]
    if not selected:
        return []

    rows: list[dict[str, Any]] = []
    for group in selected.get("groups", []):
        group_name = group.get("groupName", "Statistics")
        for item in group.get("statisticsItems", []):
            rows.append(
                {
                    "group": group_name,
                    "name": item.get("name", item.get("key", "Stat")),
                    "key": item.get("key"),
                    "home": item.get("home"),
                    "away": item.get("away"),
                    "home_value": item.get("homeValue"),
                    "away_value": item.get("awayValue"),
                }
            )
    return rows


def extract_players(lineups_payload: dict[str, Any], match: MatchInfo) -> list[PlayerOption]:
    players: list[PlayerOption] = []
    for side in ("home", "away"):
        team_name = match.home_name if side == "home" else match.away_name
        opponent = match.away_name if side == "home" else match.home_name
        block = lineups_payload.get(side, {}) or {}
        for row in block.get("players", []) or []:
            player = row.get("player", {}) or {}
            stats = row.get("statistics", {}) or {}
            if not player.get("name"):
                continue
            players.append(
                PlayerOption(
                    player_id=player.get("id", player.get("slug", player.get("name"))),
                    name=player.get("name"),
                    team=team_name,
                    opponent=opponent,
                    side=side,
                    stats=stats,
                )
            )
    return players


LABELS = {
    "goals": "Goals",
    "goalAssist": "Assists",
    "totalShots": "Shots",
    "onTargetScoringAttempt": "Shots On-Target",
    "shotOffTarget": "Shots off target",
    "blockedScoringAttempt": "Shots blocked",
    "bigChanceCreated": "Big chances created",
    "bigChanceMissed": "Big chances missed",
    "keyPass": "Chances Created",
    "touches": "Touches",
    "totalPass": "Total Passes",
    "accuratePass": "Successful Passes",
    "totalLongBalls": "Long balls attempted",
    "accurateLongBalls": "Accurate Long Passes",
    "totalCross": "Crosses attempted",
    "accurateCross": "Accurate Crosses",
    "totalContest": "Take-ons attempted",
    "wonContest": "Successful Take-Ons",
    "duelWon": "Duels Won",
    "duelLost": "Duels lost",
    "groundDuelWon": "Ground Duels Won",
    "groundDuelLost": "Ground duels lost",
    "aerialWon": "Aerial Duels Won",
    "aerialLost": "Aerial duels lost",
    "totalTackle": "Tackles Won",
    "interceptionWon": "Interceptions",
    "ballRecovery": "Ball Recoveries",
    "totalClearance": "Clearances",
    "outfielderBlock": "Blocks",
    "wasFouled": "Fouled",
    "fouls": "Fouls",
    "possessionLostCtrl": "Possession Lost",
    "saves": "Saves",
    "savedShotsFromInsideTheBox": "Saves inside box",
    "goalsPrevented": "Goals prevented",
    "expectedGoals": "xG",
    "touchesInOppBox": "Opposition Box Touches",
    "progressiveCarries": "Progressive Carries",
    "progressiveCarryingDistance": "Progressive Carrying Distance (m)",
    "finalThirdEntries": "Final Third Entries",
    "accurateFinalThirdPasses": "Successful Final Third Passes",
}

PAIR_FIELDS = [
    ("accuratePass", "totalPass", "Successful Passes"),
    ("accurateLongBalls", "totalLongBalls", "Accurate Long Passes"),
    ("accurateCross", "totalCross", "Accurate Crosses"),
    ("wonContest", "totalContest", "Successful Take-Ons"),
]

EXCLUDED_KEYS = {
    "rating",
    "minutesPlayed",
    "accuratePass",
    "totalPass",
    "accurateLongBalls",
    "totalLongBalls",
    "accurateCross",
    "totalCross",
    "wonContest",
    "totalContest",
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def build_player_stat_rows(stats: dict[str, Any], hide_zero: bool = True) -> tuple[list[dict[str, Any]], Any]:
    rows: list[dict[str, Any]] = []
    used = set()

    for success_key, total_key, label in PAIR_FIELDS:
        success = stats.get(success_key)
        total = stats.get(total_key)
        success_num = _number(success)
        total_num = _number(total)
        if success_num is None and total_num is None:
            continue
        rank = success_num if success_num is not None else 0.0
        if hide_zero and rank == 0 and (total_num or 0) == 0:
            continue
        display = f"{int(success_num or 0)}/{int(total_num or 0)}"
        rows.append({"label": label, "display": display, "rank": rank})
        used.update({success_key, total_key})

    for key, value in stats.items():
        if key in EXCLUDED_KEYS or key in used:
            continue
        num = _number(value)
        if num is None:
            continue
        if hide_zero and num == 0:
            continue
        label = LABELS.get(key)
        if not label:
            continue
        display = str(int(num)) if float(num).is_integer() else f"{num:g}"
        rows.append({"label": label, "display": display, "rank": num})

    rows.sort(key=lambda row: (-row["rank"], row["label"]))
    minutes = stats.get("minutesPlayed")
    return rows, minutes


def build_metric_leader_rows(players: list[PlayerOption], metric: dict[str, Any], scope: str = "all") -> list[dict[str, Any]]:
    filtered = players
    if scope in {"home", "away"}:
        filtered = [p for p in players if p.side == scope]

    rows: list[dict[str, Any]] = []
    for player in filtered:
        value = player_metric_value(player.stats, metric)
        if value is None:
            continue
        rows.append(
            {
                "name": player.name,
                "team": player.team,
                "value": value,
                "display": format_metric_value(value, metric),
            }
        )

    rows.sort(key=lambda row: (-row["value"], row["name"]))
    for idx, row in enumerate(rows, start=1):
        row["rank"] = idx
    return rows
