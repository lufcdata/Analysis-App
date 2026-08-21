from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "sofascore_social_graphics"
if str(LEGACY) not in sys.path:
    sys.path.insert(0, str(LEGACY))

from parsers import (  # noqa: E402
    build_metric_leader_rows,
    build_player_stat_rows,
    extract_match_statistics,
    extract_players,
    parse_match_info,
)
from metrics import available_player_metrics  # noqa: E402
from renderer import render_match_graphic, render_player_graphic  # noqa: E402
from leader_renderer import render_metric_leaders  # noqa: E402

DATA_DIR = ROOT / "matchlab_web" / "data" / "matches"
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="MatchLab API", version="2.0.0")
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


def _path(event_id: str) -> Path:
    return DATA_DIR / f"{event_id}.json"


def _load(event_id: str) -> dict[str, Any]:
    path = _path(event_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Match has not been imported into MatchLab yet.")
    return json.loads(path.read_text())


@app.get("/health")
def health():
    return {"ok": True, "service": "matchlab-api"}


@app.post("/matches/import")
def import_match(bundle: MatchBundle):
    payload = bundle.model_dump()
    _path(bundle.event_id).write_text(json.dumps(payload, ensure_ascii=False))
    return {"ok": True, "event_id": bundle.event_id}


@app.get("/matches")
def list_matches():
    output = []
    for path in sorted(DATA_DIR.glob("*.json"), reverse=True):
        payload = json.loads(path.read_text())
        match = parse_match_info(payload["basic"])
        output.append(match.__dict__)
    return output


@app.get("/matches/{event_id}")
def get_match(event_id: str):
    payload = _load(event_id)
    match = parse_match_info(payload["basic"])
    players = extract_players(payload["lineups"], match)
    metrics = available_player_metrics(players)
    return {
        "match": match.__dict__,
        "statistics": extract_match_statistics(payload["statistics"]),
        "players": [
            {
                "id": p.player_id,
                "name": p.name,
                "team": p.team,
                "opponent": p.opponent,
                "side": p.side,
            }
            for p in players
        ],
        "metrics": metrics,
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


@app.get("/matches/{event_id}/leaders/{metric_key}")
def get_leaders(event_id: str, metric_key: str, scope: str = "all"):
    payload = _load(event_id)
    match = parse_match_info(payload["basic"])
    players = extract_players(payload["lineups"], match)
    metrics = available_player_metrics(players)
    metric = next((m for m in metrics if m.get("key") == metric_key), None)
    if metric is None:
        raise HTTPException(status_code=404, detail="Metric not available for this match")
    return {
        "metric": metric,
        "rows": build_metric_leader_rows(players, metric, scope=scope),
    }


@app.get("/matches/{event_id}/graphics/match.png")
def match_png(event_id: str):
    payload = _load(event_id)
    match = parse_match_info(payload["basic"])
    png = render_match_graphic(match, extract_match_statistics(payload["statistics"]))
    return Response(content=png, media_type="image/png")


@app.get("/matches/{event_id}/graphics/player/{player_id}.png")
def player_png(event_id: str, player_id: str):
    payload = _load(event_id)
    match = parse_match_info(payload["basic"])
    players = extract_players(payload["lineups"], match)
    player = next((p for p in players if str(p.player_id) == str(player_id)), None)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    rows, minutes = build_player_stat_rows(player.stats, hide_zero=True)
    png = render_player_graphic(player.name, player.opponent, rows, minutes, team=player.team)
    return Response(content=png, media_type="image/png")


@app.get("/matches/{event_id}/graphics/leaders/{metric_key}.png")
def leaders_png(event_id: str, metric_key: str, scope: str = "all"):
    payload = _load(event_id)
    match = parse_match_info(payload["basic"])
    players = extract_players(payload["lineups"], match)
    metrics = available_player_metrics(players)
    metric = next((m for m in metrics if m.get("key") == metric_key), None)
    if metric is None:
        raise HTTPException(status_code=404, detail="Metric not available for this match")
    rows = build_metric_leader_rows(players, metric, scope=scope)
    scope_label = {"all": "ALL PLAYERS", "home": match.home_name.upper(), "away": match.away_name.upper()}.get(scope, "ALL PLAYERS")
    png = render_metric_leaders(match, metric["label"], scope_label, rows)
    return Response(content=png, media_type="image/png")
