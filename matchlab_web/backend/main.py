from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "sofascore_social_graphics"
if str(LEGACY) not in sys.path:
    sys.path.insert(0, str(LEGACY))

from parsers import (  # noqa: E402
    available_match_periods,
    build_metric_leader_rows,
    build_player_stat_rows,
    extract_match_statistics,
    extract_players,
    parse_match_info,
)
from metrics import (  # noqa: E402
    METRICS,
    available_player_metrics,
    format_metric_value,
    metric_key,
    player_metric_value,
)
from renderer import render_match_graphic, render_player_graphic  # noqa: E402
from leader_renderer import render_metric_leaders  # noqa: E402
from sofascore_client import SofaScoreClient, SofaScoreError  # noqa: E402

DATA_DIR = ROOT / "matchlab_web" / "data" / "matches"
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="MatchLab API", version="3.0.0-local-sofascore")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class MatchBundle(BaseModel):
    event_id: str
    basic: dict[str, Any]
    statistics: dict[str, Any]
    lineups: dict[str, Any]
    player_actions: dict[str, Any] = Field(default_factory=dict)


class SofaScoreImportRequest(BaseModel):
    source: str


def _path(event_id: str) -> Path:
    return DATA_DIR / f"{event_id}.json"


def _load(event_id: str) -> dict[str, Any]:
    path = _path(event_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Match has not been imported into MatchLab yet.")
    return json.loads(path.read_text())


def _extract_event_id(value: str) -> str:
    trimmed = value.strip()
    if trimmed.isdigit():
        return trimmed
    match = re.search(r"(?:id:|event/)(\d+)", trimmed, re.I) or re.search(r"[?&#]id=(\d+)", trimmed, re.I)
    if not match:
        raise HTTPException(status_code=400, detail="Could not find a SofaScore event ID in that URL.")
    return match.group(1)


def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _asset_stem(path: Path) -> str:
    stem = _slug(path.stem)
    return re.sub(r"-(icon|icon-v2|icon-2|png|logo|crest|badge|player)$", "", stem)


def _find_local_asset(wanted_slug: str, roots: tuple[Path, ...]) -> Path | None:
    aliases = {
        "leeds": "leeds-united",
        "brighton": "brighton-hove-albion",
        "tottenham": "tottenham-hotspur",
        "west-ham": "west-ham-united",
        "wolves": "wolverhampton-wanderers",
        "man-city": "manchester-city",
        "man-utd": "manchester-united",
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
            if aliases.get(stem, stem) == wanted:
                return path
    return None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def _period_code(period: str) -> str:
    mapping = {"full": "ALL", "first_half": "1ST", "second_half": "2ND"}
    if period not in mapping:
        raise HTTPException(400, "period must be full, first_half or second_half")
    return mapping[period]


def _match_stats_payload(event_id: str, period: str) -> tuple[Any, dict[str, float | None], dict[str, float | None]]:
    payload = _load(event_id)
    match = parse_match_info(payload["basic"])
    rows = extract_match_statistics(payload["statistics"], period=_period_code(period))
    by_label = {row["name"]: row for row in rows}
    home: dict[str, float | None] = {}
    away: dict[str, float | None] = {}
    for metric in METRICS:
        key = metric_key(metric["label"])
        row = by_label.get(metric["label"])
        home[key] = _number(row.get("home_value")) if row else None
        away[key] = _number(row.get("away_value")) if row else None
        if row and home[key] is None:
            home[key] = _number(row.get("home"))
        if row and away[key] is None:
            away[key] = _number(row.get("away"))
    if period == "full":
        home["goals"] = _number(match.home_score)
        away["goals"] = _number(match.away_score)
    return match, home, away


TEAM_ASSET_ROOTS = (ROOT / "assets" / "team_logos", ROOT / "assets" / "club_logos")
PLAYER_ASSET_ROOTS = (ROOT / "assets" / "player_images", ROOT / "assets" / "players")


@app.get("/health")
def health():
    return {"ok": True, "service": "matchlab-api"}


@app.post("/matches/import-sofascore")
def import_sofascore(request: SofaScoreImportRequest):
    event_id = _extract_event_id(request.source)
    client = SofaScoreClient(cache_dir=DATA_DIR / "_sofascore_cache", timeout=20)
    try:
        match_data = client.fetch_match(event_id, refresh=True)
    except SofaScoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"MatchLab importer failed: {type(exc).__name__}: {exc}") from exc

    payload = {
        "event_id": event_id,
        "basic": match_data["basic"],
        "statistics": match_data["statistics"],
        "lineups": match_data["lineups"],
        "player_actions": match_data.get("player_actions", {}) or {},
    }
    _path(event_id).write_text(json.dumps(payload, ensure_ascii=False))
    return {"ok": True, "event_id": event_id}


@app.post("/matches/import")
def import_match(bundle: MatchBundle):
    _path(bundle.event_id).write_text(json.dumps(bundle.model_dump(), ensure_ascii=False))
    return {"ok": True, "event_id": bundle.event_id}


@app.get("/matches")
def list_matches():
    output = []
    for path in sorted(DATA_DIR.glob("*.json"), reverse=True):
        payload = json.loads(path.read_text())
        output.append(parse_match_info(payload["basic"]).__dict__)
    return output


@app.get("/matches/{event_id}")
def get_match(event_id: str):
    payload = _load(event_id)
    match = parse_match_info(payload["basic"])
    players = extract_players(payload["lineups"], match)
    return {
        "match": match.__dict__,
        "statistics": extract_match_statistics(payload["statistics"]),
        "players": [
            {"id": p.player_id, "name": p.name, "team": p.team, "opponent": p.opponent, "side": p.side}
            for p in players
        ],
        "metrics": [{"key": m["key"], "label": m["label"]} for m in available_player_metrics(players)],
    }


@app.get("/canonical/metrics")
def golden_metrics():
    return {
        "live": [
            {"key": metric_key(m["label"]), "label": m["label"]}
            for m in METRICS if m.get("player_keys")
        ],
        "match_stats": [
            {"key": metric_key(m["label"]), "label": m["label"], "percent": m.get("suffix") == "%" or m["label"] == "Possession"}
            for m in METRICS
        ],
    }


@app.get("/matches/{event_id}/period-capabilities")
def period_capabilities(event_id: str):
    payload = _load(event_id)
    supplied = {code for code, _ in available_match_periods(payload["statistics"])}
    return {
        "match_stats": {"full": "ALL" in supplied, "first_half": "1ST" in supplied, "second_half": "2ND" in supplied},
        "player_stats": {"full": True, "first_half": False, "second_half": False},
        "metric_leaders": {"full": True, "first_half": False, "second_half": False},
    }


@app.get("/matches/{event_id}/studio-match-stats")
def studio_match_stats(event_id: str, period: str = Query("full")):
    match, home, away = _match_stats_payload(event_id, period)
    return {
        "event_id": event_id,
        "canonical_match_id": event_id,
        "period": period,
        "match": {
            "match_id": event_id,
            "date": match.date_text,
            "home_team_id": _slug(match.home_name),
            "home_team": match.home_name,
            "away_team_id": _slug(match.away_name),
            "away_team": match.away_name,
            "home_score": match.home_score,
            "away_score": match.away_score,
        },
        "home": home,
        "away": away,
        "availability": {"missing_fields": [k for k in home if home[k] is None or away[k] is None]},
    }


@app.get("/matches/{event_id}/players/{player_id}")
def get_player(event_id: str, player_id: str):
    payload = _load(event_id)
    match = parse_match_info(payload["basic"])
    players = extract_players(payload["lineups"], match)
    player = next((p for p in players if str(p.player_id) == str(player_id)), None)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    rows, minutes = build_player_stat_rows(player.stats, hide_zero=True)
    return {"player": player.__dict__ | {"stats": None}, "rows": rows, "minutes": minutes}


@app.get("/matches/{event_id}/canonical-player/{player_id}")
def canonical_player(event_id: str, player_id: str, period: str = Query("full")):
    if period != "full":
        raise HTTPException(400, "Player period data is only available for the full match from this SofaScore feed.")
    data = get_player(event_id, player_id)
    p = data["player"]
    return {
        "period": period,
        "player": {"id": str(p["player_id"]), "name": p["name"], "team": p["team"], "opponent": p["opponent"], "side": p["side"]},
        "rows": data["rows"],
    }


@app.get("/matches/{event_id}/leaders/{metric_key_value}")
def get_leaders(event_id: str, metric_key_value: str, scope: str = "all"):
    payload = _load(event_id)
    match = parse_match_info(payload["basic"])
    players = extract_players(payload["lineups"], match)
    metric = next((m for m in METRICS if metric_key(m["label"]) == metric_key_value), None)
    if metric is None:
        raise HTTPException(status_code=404, detail="Metric not available")
    return {"metric": {"key": metric_key_value, "label": metric["label"]}, "rows": build_metric_leader_rows(players, metric, scope=scope)}


@app.get("/matches/{event_id}/canonical-leaders/{metric_key_value}")
def canonical_leaders(event_id: str, metric_key_value: str, period: str = Query("full"), scope: str = Query("all"), limit: int = Query(15, ge=1, le=50)):
    if period != "full":
        raise HTTPException(400, "Metric Leader period data is only available for the full match from this SofaScore feed.")
    payload = _load(event_id)
    match = parse_match_info(payload["basic"])
    players = extract_players(payload["lineups"], match)
    metric = next((m for m in METRICS if metric_key(m["label"]) == metric_key_value), None)
    if metric is None:
        raise HTTPException(404, "Metric not available")
    filtered = [p for p in players if scope == "all" or p.side == scope]
    ranked = []
    for p in filtered:
        value = player_metric_value(p.stats, metric)
        if value is not None:
            ranked.append((p, value))
    ranked.sort(key=lambda x: (-x[1], x[0].name))
    top = ranked[:limit]
    leader_value = top[0][1] if top else 0
    return {
        "metric": metric_key_value,
        "label": metric["label"],
        "period": period,
        "leaders": [
            {
                "rank": i,
                "player_id": str(p.player_id),
                "player_name": p.name,
                "team_id": _slug(p.team),
                "team_name": p.team,
                "value": value,
                "display": format_metric_value(value, metric),
                "relative_to_leader": (value / leader_value) if leader_value else 0,
            }
            for i, (p, value) in enumerate(top, start=1)
        ],
    }


@app.get("/team-logos/{team_slug}.png")
def team_logo(team_slug: str):
    path = _find_local_asset(team_slug, TEAM_ASSET_ROOTS)
    if path:
        return FileResponse(path)
    raise HTTPException(404, "No approved local club crest is available.")


@app.get("/player-images/{player_slug}.png")
def player_image(player_slug: str):
    path = _find_local_asset(player_slug, PLAYER_ASSET_ROOTS)
    if path:
        return FileResponse(path)
    payloads = sorted(DATA_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for fp in payloads:
        try:
            payload = json.loads(fp.read_text())
            match = parse_match_info(payload["basic"])
            for p in extract_players(payload["lineups"], match):
                if _slug(p.name) == _slug(player_slug):
                    crest = _find_local_asset(p.team, TEAM_ASSET_ROOTS)
                    if crest:
                        return FileResponse(crest)
        except Exception:
            continue
    raise HTTPException(404, "No approved local player image or club crest is available.")


@app.get("/matches/{event_id}/graphics/match.png")
def match_png(event_id: str):
    payload = _load(event_id)
    match = parse_match_info(payload["basic"])
    png = render_match_graphic(match, extract_match_statistics(payload["statistics"]))
    return Response(content=png, media_type="image/png")


@app.get("/matches/{event_id}/graphics/player/{player_id}.png")
def player_png(event_id: str, player_id: str):
    data = get_player(event_id, player_id)
    p = data["player"]
    png = render_player_graphic(p["name"], p["opponent"], data["rows"], data["minutes"], team=p["team"])
    return Response(content=png, media_type="image/png")


@app.get("/matches/{event_id}/graphics/leaders/{metric_key_value}.png")
def leaders_png(event_id: str, metric_key_value: str, scope: str = "all"):
    payload = _load(event_id)
    match = parse_match_info(payload["basic"])
    data = get_leaders(event_id, metric_key_value, scope)
    scope_label = {"all": "ALL PLAYERS", "home": match.home_name.upper(), "away": match.away_name.upper()}.get(scope, "ALL PLAYERS")
    png = render_metric_leaders(match, data["metric"]["label"], scope_label, data["rows"])
    return Response(content=png, media_type="image/png")
