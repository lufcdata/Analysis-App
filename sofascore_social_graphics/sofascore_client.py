from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://www.sofascore.com/api/v1"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/150 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.sofascore.com/",
}


class SofaScoreError(RuntimeError):
    pass


def extract_event_id(value: str) -> str:
    value = value.strip()
    if value.isdigit():
        return value

    patterns = [
        r"(?:#|,|\?|&)id:(\d+)",
        r"(?:#|,|\?|&)id=(\d+)",
        r"/event/(\d+)",
    ]
    for pattern in patterns:
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

    def _get_json(self, url: str) -> dict[str, Any]:
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            raise SofaScoreError(f"Could not connect to SofaScore: {exc}") from exc

        if response.status_code == 429:
            raise SofaScoreError("SofaScore rate-limited the request (HTTP 429). Try again later.")
        if response.status_code != 200:
            raise SofaScoreError(f"SofaScore returned HTTP {response.status_code} for {url}")
        try:
            return response.json()
        except ValueError as exc:
            raise SofaScoreError("SofaScore returned a non-JSON response.") from exc

    def _fetch_slice(self, event_id: str, name: str, endpoint: str, refresh: bool) -> dict[str, Any]:
        target = self._event_dir(event_id) / f"{name}.json"
        if target.exists() and not refresh:
            with target.open("r", encoding="utf-8") as handle:
                return json.load(handle)

        data = self._get_json(f"{BASE_URL}{endpoint}")
        with target.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        return data

    def fetch_match(self, event_id: str, refresh: bool = False) -> dict[str, Any]:
        event_id = str(event_id)
        return {
            "basic": self._fetch_slice(event_id, "basic", f"/event/{event_id}", refresh),
            "statistics": self._fetch_slice(event_id, "statistics", f"/event/{event_id}/statistics", refresh),
            "lineups": self._fetch_slice(event_id, "lineups", f"/event/{event_id}/lineups", refresh),
        }
