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

    def fetch_player_actions(self, event_id: str, lineups: dict[str, Any], refresh: bool = False) -> dict[str, Any]:
        """Optional enrichment only. It is deliberately NOT part of MatchLab's core import path."""
        result: dict[str, Any] = {}
        for side in ("home", "away"):
            for row in (lineups.get(side, {}) or {}).get("players", []) or []:
                player = row.get("player") or {}
                pid = player.get("id")
                if not pid:
                    continue
                data = self._fetch_slice(
                    str(event_id),
                    f"actions_{pid}",
                    f"/event/{event_id}/player/{pid}/rating-breakdown",
                    refresh,
                    optional=True,
                )
                if data:
                    result[str(pid)] = data
        return result

    def fetch_match(self, event_id: str, refresh: bool = False) -> dict[str, Any]:
        """Fetch only the three provider payloads MatchLab actually needs to populate Studio.

        Keeping the import path to event + statistics + lineups avoids dozens of optional
        per-player requests from delaying or breaking a normal Load Match operation.
        """
        event_id = str(event_id)
        basic = self._fetch_slice(event_id, "basic", f"/event/{event_id}", refresh)
        statistics = self._fetch_slice(event_id, "statistics", f"/event/{event_id}/statistics", refresh)
        lineups = self._fetch_slice(event_id, "lineups", f"/event/{event_id}/lineups", refresh)
        return {
            "basic": basic,
            "statistics": statistics,
            "lineups": lineups,
            "player_actions": {},
        }
