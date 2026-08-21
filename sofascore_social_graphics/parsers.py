from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from metrics import build_canonical_player_rows, format_metric_value, player_metric_value


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


def build_player_stat_rows(stats: dict[str, Any], hide_zero: bool = True) -> tuple[list[dict[str, Any]], Any]:
    # Single source of truth: public labels, ordering and supported player metrics
    # all come from metrics.METRICS, exactly like Metric Leaders.
    return build_canonical_player_rows(stats, hide_zero=hide_zero)


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
