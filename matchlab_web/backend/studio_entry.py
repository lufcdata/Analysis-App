from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Query
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studio_main import app, _resolve_match  # noqa: E402,F401
from main import DATA_DIR, _load, extract_match_statistics  # noqa: E402
from v2.canonical_match_stats import get_canonical_match_stats  # noqa: E402
from v2.match_metric_leaders import metric_catalog  # noqa: E402
from v2.metric_registry import METRIC_SET_VERSION  # noqa: E402


# Locked 21 Aug Matchday Studio Match Stats list. The UI must expose exactly
# these 33 rows, in this order. Canonical V2 values win wherever the Metrics
# Bible engine already supplies the metric. Provider rows are used only for
# genuine match/period values that are not yet emitted by the V2 Match Stats
# surface; they are never estimated from full-match totals.
MATCH_STATS_33: tuple[tuple[str, str, str | None], ...] = (
    ("goals", "Goals", "goals"),
    ("xg", "xG", None),
    ("possession", "Possession", "possession"),
    ("touches", "Touches", "touches"),
    ("opposition_box_touches", "Opposition Box Touches", "penalty_box_touches"),
    ("shots", "Shots", "shots"),
    ("shots_on_target", "Shots On-Target", "shots_on_target"),
    ("shots_outside_box", "Shots Outside Box", None),
    ("big_chances", "Big Chances", "big_chances"),
    ("chances_created", "Chances Created", "chances_created"),
    ("successful_passes", "Successful Passes", "successful_passes"),
    ("total_passes", "Total Passes", None),
    ("successful_final_third_passes", "Successful Final Third Passes", "successful_final_third_passes"),
    ("pass_accuracy", "Pass Accuracy", "pass_accuracy"),
    ("ball_carries", "Ball Carries", None),
    ("progressive_carries", "Progressive Carries", None),
    ("progressive_carrying_distance_m", "Progressive Carrying Distance (m)", None),
    ("accurate_long_passes", "Accurate Long Passes", "accurate_long_passes"),
    ("final_third_entries", "Final Third Entries", None),
    ("accurate_crosses", "Accurate Crosses", "accurate_crosses"),
    ("ground_duels_won", "Ground Duels Won", "ground_duels_won"),
    ("aerial_duels_won", "Aerial Duels Won", "aerial_duels_won"),
    ("duels_won", "Duels Won", "duels_won"),
    ("ball_recoveries", "Ball Recoveries", "ball_recoveries"),
    ("successful_take_ons", "Successful Take-Ons", "successful_take_ons"),
    ("tackles_won", "Tackles Won", "tackles_won"),
    ("interceptions", "Interceptions", "interceptions"),
    ("clearances", "Clearances", "clearances"),
    ("fouls", "Fouls", None),
    ("fouled", "Fouled", None),
    ("possession_lost", "Possession Lost", None),
    ("corners", "Corners", "corners"),
    ("saves", "Saves", "saves"),
)

if len(MATCH_STATS_33) != 33:
    raise RuntimeError("Matchday Studio Match Stats contract must contain exactly 33 metrics")


def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _asset_stem(path: Path) -> str:
    stem = _slug(path.stem)
    stem = re.sub(r"-(icon|icon-v2|icon-2|png|logo|crest|badge|player)$", "", stem)
    return stem


def _find_local_asset(wanted_slug: str, roots: tuple[Path, ...]) -> Path | None:
    aliases = {
        "leeds": "leeds-united", "leeds-png": "leeds-united",
        "brighton": "brighton-hove-albion",
        "tottenham": "tottenham-hotspur",
        "west-ham": "west-ham-united",
        "wolves": "wolverhampton-wanderers",
        "man-city": "manchester-city",
        "man-utd": "manchester-united", "scum": "manchester-united",
        "newcastle": "newcastle-united",
        "forest": "nottingham-forest",
    }
    wanted = aliases.get(_slug(wanted_slug), _slug(wanted_slug))
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.name.startswith("._") or "__MACOSX" in path.parts:
                continue
            if path.suffix.lower() not in {".png", ".webp", ".jpg", ".jpeg"}:
                continue
            stem = _asset_stem(path)
            normalized = aliases.get(stem, stem)
            if stem == wanted or normalized == wanted:
                return path
    return None


def _recent_payloads():
    for path in sorted(DATA_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            yield json.loads(path.read_text())
        except Exception:
            continue


def _player_team(player_slug: str) -> str | None:
    wanted = _slug(player_slug)
    for payload in _recent_payloads():
        lineups = payload.get("lineups", {}) or {}
        basic = payload.get("basic", {}) or {}
        event = basic.get("event", basic)
        for side in ("home", "away"):
            team = event.get(f"{side}Team", {}) or {}
            for row in (lineups.get(side, {}) or {}).get("players", []) or []:
                player = row.get("player", {}) or {}
                if _slug(player.get("name", "")) == wanted:
                    return str(team.get("name") or "") or None
    return None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        return float(text)
    except ValueError:
        return None


def _provider_period(period: str) -> str:
    return {"full": "ALL", "first_half": "1ST", "second_half": "2ND"}[period]


def _provider_match_values(event_id: str, period: str) -> tuple[dict[str, float | None], dict[str, float | None]]:
    payload = _load(event_id)
    rows = extract_match_statistics(payload["statistics"], period=_provider_period(period))
    home: dict[str, float | None] = {}
    away: dict[str, float | None] = {}
    by_label = {label: key for key, label, _ in MATCH_STATS_33}
    for row in rows:
        key = by_label.get(str(row.get("name") or ""))
        if not key:
            continue
        home[key] = _number(row.get("home_value"))
        away[key] = _number(row.get("away_value"))
        if home[key] is None:
            home[key] = _number(row.get("home"))
        if away[key] is None:
            away[key] = _number(row.get("away"))
    return home, away


TEAM_ASSET_ROOTS = (
    ROOT / "assets" / "team_logos",
    ROOT / "assets" / "club_logos",
    ROOT / "sofascore_social_graphics" / "assets" / "team_logos",
    ROOT / "sofascore_social_graphics" / "assets" / "club_logos",
)
PLAYER_ASSET_ROOTS = (
    ROOT / "assets" / "player_images",
    ROOT / "assets" / "players",
    ROOT / "sofascore_social_graphics" / "assets" / "player_images",
    ROOT / "sofascore_social_graphics" / "assets" / "players",
)


@app.get("/canonical/metrics")
def canonical_metrics():
    return {
        "metric_set_version": METRIC_SET_VERSION,
        "live": metric_catalog(),
        "match_stats": [{"key": key, "label": label} for key, label, _ in MATCH_STATS_33],
        "match_stats_count": len(MATCH_STATS_33),
    }


@app.get("/matches/{event_id}/studio-match-stats")
def studio_match_stats(event_id: str, period: str = Query("full")):
    if period not in {"full", "first_half", "second_half"}:
        raise HTTPException(400, "period must be full, first_half or second_half")

    match_id = _resolve_match(event_id)
    try:
        canonical = get_canonical_match_stats(match_id, period=period)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    provider_home, provider_away = _provider_match_values(event_id, period)
    canonical_home = canonical.get("home", {}) or {}
    canonical_away = canonical.get("away", {}) or {}

    home: dict[str, float | None] = {}
    away: dict[str, float | None] = {}
    sources: dict[str, str] = {}
    missing: list[str] = []
    for key, _label, canonical_key in MATCH_STATS_33:
        ch = canonical_home.get(canonical_key) if canonical_key else None
        ca = canonical_away.get(canonical_key) if canonical_key else None
        if canonical_key and ch is not None and ca is not None:
            home[key], away[key], sources[key] = ch, ca, "canonical-v2"
        else:
            home[key], away[key] = provider_home.get(key), provider_away.get(key)
            sources[key] = "sofascore-period-raw"
        if home[key] is None or away[key] is None:
            missing.append(key)

    return {
        "event_id": event_id,
        "canonical_match_id": match_id,
        "period": period,
        "match": canonical["match"],
        "home": home,
        "away": away,
        "availability": {"missing_fields": missing},
        "metric_contract": "matchlab-stats-33-2026-08-21",
        "metric_contract_count": 33,
        "metric_sources": sources,
        "metric_set_version": METRIC_SET_VERSION,
    }


@app.get("/team-logos/{team_slug}.png")
def team_logo(team_slug: str):
    path = _find_local_asset(team_slug, TEAM_ASSET_ROOTS)
    if path:
        return FileResponse(path)
    raise HTTPException(404, "No approved local club crest is available.")


@app.get("/player-images/{player_slug}.png")
def player_image(player_slug: str):
    # Strict image policy: approved local player photo first, then approved local club crest.
    # There is deliberately no SofaScore/CDN image fallback here.
    path = _find_local_asset(player_slug, PLAYER_ASSET_ROOTS)
    if path:
        return FileResponse(path)

    team_name = _player_team(player_slug)
    if team_name:
        crest = _find_local_asset(team_name, TEAM_ASSET_ROOTS)
        if crest:
            return FileResponse(crest)

    raise HTTPException(404, "No approved local player image or club crest is available.")
