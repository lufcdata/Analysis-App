from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from metrics import build_canonical_player_rows, canonical_match_label, format_metric_value, player_metric_value


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
    tournament = event.get("tournament", {}).get("uniqueTournament", {}).get("name") or event.get("tournament", {}).get("name") or ""
    timestamp = event.get("startTimestamp")
    date_text = datetime.fromtimestamp(timestamp).strftime("%d %B %Y") if timestamp else ""
    return MatchInfo(str(event.get("id", "")), home.get("name", "Home"), away.get("name", "Away"), str(home_score), str(away_score), tournament, date_text)


def available_match_periods(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """Return only periods SofaScore actually supplied; never synthesize a half."""
    aliases = {"ALL": "Full Match", "1ST": "1st Half", "2ND": "2nd Half", "FIRST": "1st Half", "SECOND": "2nd Half"}
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for block in payload.get("statistics", []) or []:
        raw = str(block.get("period", "")).upper()
        label = aliases.get(raw)
        canonical = "1ST" if raw == "FIRST" else "2ND" if raw == "SECOND" else raw
        if label and canonical not in seen:
            found.append((canonical, label)); seen.add(canonical)
    order = {"ALL": 0, "1ST": 1, "2ND": 2}
    return sorted(found, key=lambda pair: order.get(pair[0], 99))


def extract_match_statistics(payload: dict[str, Any], period: str = "ALL") -> list[dict[str, Any]]:
    period = period.upper()
    aliases = {"ALL": {"ALL"}, "1ST": {"1ST", "FIRST"}, "2ND": {"2ND", "SECOND"}}
    selected = next((p for p in payload.get("statistics", []) or [] if str(p.get("period", "")).upper() in aliases.get(period, {period})), None)
    if not selected:
        return []

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in selected.get("groups", []) or []:
        for item in group.get("statisticsItems", []) or []:
            raw_name = item.get("name", item.get("key", "Stat"))
            raw_key = item.get("key")
            label = canonical_match_label(str(raw_name), str(raw_key) if raw_key is not None else None)
            if not label or label in seen:
                continue
            rows.append({
                "group": group.get("groupName", "Statistics"),
                "name": label,
                "source_name": raw_name,
                "key": raw_key,
                "home": item.get("home"),
                "away": item.get("away"),
                "home_value": item.get("homeValue"),
                "away_value": item.get("awayValue"),
            })
            seen.add(label)
    return rows


def extract_players(lineups_payload: dict[str, Any], match: MatchInfo) -> list[PlayerOption]:
    players: list[PlayerOption] = []
    for side in ("home", "away"):
        team_name = match.home_name if side == "home" else match.away_name
        opponent = match.away_name if side == "home" else match.home_name
        for row in (lineups_payload.get(side, {}) or {}).get("players", []) or []:
            player = row.get("player", {}) or {}; stats = row.get("statistics", {}) or {}
            if player.get("name"):
                players.append(PlayerOption(player.get("id", player.get("slug", player.get("name"))), player.get("name"), team_name, opponent, side, stats))
    return players


def build_player_stat_rows(stats: dict[str, Any], hide_zero: bool = True) -> tuple[list[dict[str, Any]], Any]:
    return build_canonical_player_rows(stats, hide_zero=hide_zero)


def build_metric_leader_rows(players: list[PlayerOption], metric: dict[str, Any], scope: str = "all") -> list[dict[str, Any]]:
    filtered = [p for p in players if scope == "all" or p.side == scope]
    rows: list[dict[str, Any]] = []
    for player in filtered:
        value = player_metric_value(player.stats, metric)
        if value is not None:
            rows.append({"name": player.name, "team": player.team, "value": value, "display": format_metric_value(value, metric)})
    rows.sort(key=lambda row: (-row["value"], row["name"]))
    for idx, row in enumerate(rows, start=1): row["rank"] = idx
    return rows
