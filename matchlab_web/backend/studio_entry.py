from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

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


def _find_local_asset(wanted_slug: str, roots: tuple[Path, ...]) -> Path | None:
    aliases = {
        'leeds': 'leeds-united',
        'brighton': 'brighton-hove-albion',
        'tottenham': 'tottenham-hotspur',
        'west-ham': 'west-ham-united',
        'wolves': 'wolverhampton-wanderers',
    }
    wanted = aliases.get(_slug(wanted_slug), _slug(wanted_slug))
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob('*'):
            if not path.is_file() or path.suffix.lower() not in {'.png', '.webp', '.jpg', '.jpeg'}:
                continue
            stem = _slug(path.stem)
            if stem == wanted or aliases.get(stem, stem) == wanted:
                return path
    return None


def _recent_payloads():
    for path in sorted(DATA_DIR.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            yield json.loads(path.read_text())
        except Exception:
            continue


def _player_team(player_slug: str) -> str | None:
    wanted = _slug(player_slug)
    for payload in _recent_payloads():
        lineups = payload.get('lineups', {}) or {}
        basic = payload.get('basic', {}) or {}
        event = basic.get('event', basic)
        for side in ('home', 'away'):
            team = event.get(f'{side}Team', {}) or {}
            for row in (lineups.get(side, {}) or {}).get('players', []) or []:
                player = row.get('player', {}) or {}
                if _slug(player.get('name', '')) == wanted:
                    return str(team.get('name') or '') or None
    return None


TEAM_ASSET_ROOTS = (
    ROOT / 'assets' / 'team_logos',
    ROOT / 'assets' / 'club_logos',
    ROOT / 'sofascore_social_graphics' / 'assets' / 'team_logos',
    ROOT / 'sofascore_social_graphics' / 'assets' / 'club_logos',
)
PLAYER_ASSET_ROOTS = (
    ROOT / 'assets' / 'player_images',
    ROOT / 'assets' / 'players',
    ROOT / 'sofascore_social_graphics' / 'assets' / 'player_images',
    ROOT / 'sofascore_social_graphics' / 'assets' / 'players',
)


@app.get('/canonical/metrics')
def canonical_metrics():
    return {
        'metric_set_version': METRIC_SET_VERSION,
        'live': metric_catalog(),
    }


@app.get('/team-logos/{team_slug}.png')
def team_logo(team_slug: str):
    path = _find_local_asset(team_slug, TEAM_ASSET_ROOTS)
    if path:
        return FileResponse(path)
    raise HTTPException(404, 'No approved local club crest is available.')


@app.get('/player-images/{player_slug}.png')
def player_image(player_slug: str):
    path = _find_local_asset(player_slug, PLAYER_ASSET_ROOTS)
    if path:
        return FileResponse(path)

    team_name = _player_team(player_slug)
    if team_name:
        crest = _find_local_asset(team_name, TEAM_ASSET_ROOTS)
        if crest:
            return FileResponse(crest)

    raise HTTPException(404, 'No approved local player image or club crest is available.')
