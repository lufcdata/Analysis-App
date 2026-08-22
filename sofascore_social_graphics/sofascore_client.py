from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests
from curl_cffi import requests as curl_requests

BASE_URLS = ("https://api.sofascore.com/api/v1", "https://www.sofascore.com/api/v1")
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://www.sofascore.com/",
    "Origin": "https://www.sofascore.com",
    "X-Requested-With": "XMLHttpRequest",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


class SofaScoreError(RuntimeError):
    pass


def extract_event_id(value: str) -> str:
    value = value.strip()
    if value.isdigit():
        return value
    for pattern in [r"(?:#|,|\?|&)id:(\d+)", r"(?:#|,|\?|&)id=(\d+)", r"/event/(\d+)"]:
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    match = re.search(r"id:(\d+)", value)
    if match:
        return match.group(1)
    raise ValueError("Could not find a SofaScore event ID in that URL/input.")


class SofaScoreClient:
    def __init__(self, cache_dir: str | Path = "data/cache", timeout: int = 20):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def _event_dir(self, event_id: str) -> Path:
        path = self.cache_dir / str(event_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _json_or_none(response: Any) -> dict[str, Any] | None:
        if getattr(response, "status_code", None) != 200:
            return None
        try:
            return response.json()
        except Exception:
            return None

    def _get_json(self, endpoint: str) -> dict[str, Any]:
        errors = []
        for base_url in BASE_URLS:
            try:
                response = curl_requests.get(
                    f"{base_url}{endpoint}",
                    headers=DEFAULT_HEADERS,
                    impersonate="chrome",
                    timeout=self.timeout,
                )
                data = self._json_or_none(response)
                if data is not None:
                    return data
                errors.append(f"browser transport {base_url}: HTTP {getattr(response, 'status_code', '?')}")
            except Exception as exc:
                errors.append(f"browser transport {base_url}: {type(exc).__name__}")

        for base_url in BASE_URLS:
            try:
                response = self.session.get(f"{base_url}{endpoint}", timeout=self.timeout)
            except requests.RequestException as exc:
                errors.append(f"requests {base_url}: connection error ({exc})")
                continue
            data = self._json_or_none(response)
            if data is not None:
                return data
            errors.append(f"requests {base_url}: HTTP {response.status_code}")

        raise SofaScoreError("Could not load this match from SofaScore. Results: " + " | ".join(errors))

    def _fetch_slice(self, event_id: str, name: str, endpoint: str, refresh: bool, optional: bool = False) -> dict[str, Any]:
        target = self._event_dir(event_id) / f"{name}.json"
        if target.exists() and not refresh:
            with target.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        try:
            data = self._get_json(endpoint)
        except SofaScoreError:
            if optional:
                return {}
            raise
        with target.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        return data

    @staticmethod
    def _all_items(statistics: dict[str, Any]) -> list[dict[str, Any]]:
        for period in statistics.get("statistics", []) or []:
            if str(period.get("period", "")).upper() == "ALL":
                items: list[dict[str, Any]] = []
                for group in period.get("groups", []) or []:
                    items.extend(group.get("statisticsItems", []) or [])
                return items
        return []

    @classmethod
    def _existing_stat_keys(cls, statistics: dict[str, Any]) -> set[str]:
        return {str(item.get("key")) for item in cls._all_items(statistics) if item.get("key")}

    @staticmethod
    def _sum_direct_player_key(lineups: dict[str, Any], side: str, aliases: tuple[str, ...]) -> float | None:
        total = 0.0
        found = False
        for row in (lineups.get(side, {}) or {}).get("players", []) or []:
            stats = row.get("statistics", {}) or {}
            for key in aliases:
                value = stats.get(key)
                if isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)):
                    total += float(value)
                    found = True
                    break
        return total if found else None

    @classmethod
    def _find_team_stat(cls, statistics: dict[str, Any], aliases: tuple[str, ...], side: str) -> float | None:
        wanted = set(aliases)
        for item in cls._all_items(statistics):
            if str(item.get("key", "")) not in wanted:
                continue
            for value_key in (f"{side}Value", side):
                value = item.get(value_key)
                if isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)):
                    return float(value)
                if isinstance(value, str):
                    match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
                    if match:
                        return float(match.group(0))
        return None

    @staticmethod
    def _drop_misleading_team_rows(statistics: dict[str, Any]) -> None:
        """Prevent narrower SofaScore rows being mistaken for Golden MatchLab metrics."""
        for period in statistics.get("statistics", []) or []:
            if str(period.get("period", "")).upper() != "ALL":
                continue
            for group in period.get("groups", []) or []:
                items = group.get("statisticsItems", []) or []
                group["statisticsItems"] = [item for item in items if str(item.get("key", "")) != "dispossessed"]

    def _add_direct_team_totals(self, statistics: dict[str, Any], lineups: dict[str, Any]) -> dict[str, Any]:
        self._drop_misleading_team_rows(statistics)
        existing = self._existing_stat_keys(statistics)
        specs: tuple[tuple[str, str, tuple[str, ...]], ...] = (
            ("Touches", "touches", ("touches", "totalTouches")),
            ("Key passes", "keyPasses", ("keyPass", "keyPasses")),
            ("Carries", "ballCarriesCount", ("ballCarriesCount", "ballCarries", "carries", "totalCarries")),
            ("Progressive carries", "progressiveBallCarriesCount", ("progressiveBallCarriesCount", "progressiveBallCarries", "progressiveCarries")),
            ("Progressive carrying distance", "totalProgressiveBallCarriesDistance", ("totalProgressiveBallCarriesDistance", "progressiveBallCarriesDistance", "progressiveCarryingDistance", "progressiveCarryDistance")),
            ("Was fouled", "wasFouled", ("wasFouled",)),
            ("Possession lost", "possessionLostCtrl", ("possessionLostCtrl",)),
            ("Assists", "assists", ("goalAssist", "assists")),
            ("Penalties won", "penaltiesWon", ("penaltyWon", "penaltiesWon")),
            ("Saves from inside box", "savedShotsFromInsideTheBox", ("savedShotsFromInsideTheBox", "savesFromInsideBox")),
            ("High claims", "highClaims", ("highClaims", "goodHighClaim")),
            ("Red cards", "redCards", ("redCards", "redCard", "directRedCards")),
            ("Def. contribution", "defensiveContribution", ("defensiveContribution",)),
        )

        synthetic: list[dict[str, Any]] = []
        for name, key, aliases in specs:
            if key in existing:
                continue
            home = self._sum_direct_player_key(lineups, "home", aliases)
            away = self._sum_direct_player_key(lineups, "away", aliases)
            if home is None and away is None:
                continue
            synthetic.append({
                "name": name,
                "key": key,
                "home": home,
                "away": away,
                "homeValue": home,
                "awayValue": away,
                "statisticsType": "positive",
                "matchlabSource": "direct-player-total",
            })

        all_period = next(
            (p for p in statistics.get("statistics", []) or [] if str(p.get("period", "")).upper() == "ALL"),
            None,
        )
        if all_period is None:
            return statistics
        if synthetic:
            all_period.setdefault("groups", []).append({"groupName": "MatchLab direct SofaScore totals", "statisticsItems": synthetic})
        return statistics

    def _add_pass_accuracy(self, statistics: dict[str, Any]) -> dict[str, Any]:
        """Golden Pass Accuracy = Successful Passes / Total Passes * 100."""
        if "passAccuracy" in self._existing_stat_keys(statistics):
            return statistics

        home_success = self._find_team_stat(statistics, ("accuratePasses", "accuratePass"), "home")
        away_success = self._find_team_stat(statistics, ("accuratePasses", "accuratePass"), "away")
        home_total = self._find_team_stat(statistics, ("passes", "totalPasses", "totalPass"), "home")
        away_total = self._find_team_stat(statistics, ("passes", "totalPasses", "totalPass"), "away")
        if home_success is None or away_success is None or not home_total or not away_total:
            return statistics

        home_accuracy = home_success / home_total * 100.0
        away_accuracy = away_success / away_total * 100.0
        all_period = next(
            (p for p in statistics.get("statistics", []) or [] if str(p.get("period", "")).upper() == "ALL"),
            None,
        )
        if all_period is None:
            return statistics
        all_period.setdefault("groups", []).append({
            "groupName": "MatchLab calculated metrics",
            "statisticsItems": [{
                "name": "Pass Accuracy",
                "key": "passAccuracy",
                "home": home_accuracy,
                "away": away_accuracy,
                "homeValue": home_accuracy,
                "awayValue": away_accuracy,
                "statisticsType": "positive",
                "matchlabSource": "successful-passes-div-total-passes",
            }],
        })
        return statistics

    def fetch_player_actions(self, event_id: str, lineups: dict[str, Any], refresh: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for side in ("home", "away"):
            for row in (lineups.get(side, {}) or {}).get("players", []) or []:
                player = row.get("player") or {}
                pid = player.get("id")
                if not pid:
                    continue
                data = self._fetch_slice(str(event_id), f"actions_{pid}", f"/event/{event_id}/player/{pid}/rating-breakdown", refresh, optional=True)
                if data:
                    result[str(pid)] = data
        return result

    def fetch_match(self, event_id: str, refresh: bool = False) -> dict[str, Any]:
        event_id = str(event_id)
        basic = self._fetch_slice(event_id, "basic", f"/event/{event_id}", refresh)
        statistics = self._fetch_slice(event_id, "statistics", f"/event/{event_id}/statistics", refresh)
        lineups = self._fetch_slice(event_id, "lineups", f"/event/{event_id}/lineups", refresh)
        statistics = self._add_direct_team_totals(statistics, lineups)
        statistics = self._add_pass_accuracy(statistics)
        return {
            "basic": basic,
            "statistics": statistics,
            "lineups": lineups,
            "player_actions": {},
        }
