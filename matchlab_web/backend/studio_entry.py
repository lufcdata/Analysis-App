from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import RedirectResponse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studio_main import app  # noqa: E402,F401
from main import DATA_DIR  # noqa: E402
from v2.match_metric_leaders import metric_catalog  # noqa: E402
from v2.metric_registry import METRIC_SET_VERSION  # noqa: E402


def _slug(value: str) -> str:
    value = unicodedata.normalize('NFKD', str(value or ''))
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')


def _recent_payloads():
    paths = sorted(DATA_DIR.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in paths:
        try:
            yield json.loads(path.read_text())
        except Exception:
            continue


@app.get('/canonical/metrics')
def canonical_metrics():
    return {
        'metric_set_version': METRIC_SET_VERSION,
        'live': metric_catalog(),
    }


@app.get('/team-logos/{team_slug}.png')
def team_logo(team_slug: str):
    wanted = _slug(team_slug)
    aliases = {
        'leeds': 'leeds-united',
        'brighton': 'brighton-hove-albion',
        'tottenham': 'tottenham-hotspur',
        'west-ham': 'west-ham-united',
        'wolves': 'wolverhampton-wanderers',
    }
    wanted = aliases.get(wanted, wanted)
    for payload in _recent_payloads():
        event = payload.get('basic', {}).get('event', payload.get('basic', {}))
        for key in ('homeTeam', 'awayTeam'):
            team = event.get(key, {}) or {}
            if _slug(team.get('name', '')) == wanted and team.get('id'):
                return RedirectResponse(f"https://img.sofascore.com/api/v1/team/{team['id']}/image", status_code=307)
    raise HTTPException(404, 'Team image is not available from the imported SofaScore matches.')


@app.get('/player-images/{player_slug}.png')
def player_image(player_slug: str):
    wanted = _slug(player_slug)
    for payload in _recent_payloads():
        lineups = payload.get('lineups', {}) or {}
        for side in ('home', 'away'):
            for row in (lineups.get(side, {}) or {}).get('players', []) or []:
                player = row.get('player', {}) or {}
                if _slug(player.get('name', '')) == wanted and player.get('id'):
                    return RedirectResponse(f"https://img.sofascore.com/api/v1/player/{player['id']}/image", status_code=307)
    raise HTTPException(404, 'Player image is not available from the imported SofaScore matches.')
