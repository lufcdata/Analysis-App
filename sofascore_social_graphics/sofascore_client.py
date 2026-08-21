from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests

# SofaScore's current API host. Keep the www host as a fallback because
# behaviour can vary by network/provider.
BASE_URLS = (
    "https://api.sofascore.com/api/v1",
    "https://www.sofascore.com/api/v1",
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
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

    def _get_json(self, endpoint: str) -> dict[str, Any]:
        errors: list[str] = []

        for base_url in BASE_URLS:
            url = f"{base_url}{endpoint}"
            try:
                response = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as exc:
                errors.append(f"{base_url}: connection error ({exc})")
                continue

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    errors.append(f"{base_url}: returned non-JSON content")
                    continue

            if response.status_code == 429:
                errors.append(f"{base_url}: HTTP 429 rate limited")
            else:
                errors.append(f"{base_url}: HTTP {response.status_code}")

        joined = " | ".join(errors)
        raise SofaScoreError(
            "Could not load this match from SofaScore. "
            f"Tried the available API hosts: {joined}"
        )

    def _fetch_slice(self, event_id: str, name: str, endpoint: str, refresh: bool) -> dict[str, Any]:
        target = self._event_dir(event_id) / f"{name}.json"
        if target.exists() and not refresh:
            with target.open("r", encoding="utf-8") as handle:
                return json.load(handle)

        data = self._get_json(endpoint)
        with target.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        return data

    def fetch_match(self, event_id: str, refresh: bool = False) -> dict[str, Any]:
        event_id = str(event_id)
        return {
            "basic": self._fetch_slice(event_id, "basic", f"/event/{event_id}", refresh),
            "statistics": self._fetch_slice(
                event_id, "statistics", f"/event/{event_id}/statistics", refresh
            ),
            "lineups": self._fetch_slice(
                event_id, "lineups", f"/event/{event_id}/lineups", refresh
            ),
        }
