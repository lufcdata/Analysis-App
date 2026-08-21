from __future__ import annotations

import inspect
import re
import unicodedata
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from main import (
    SofaScoreImportRequest,
    import_sofascore as legacy_import_sofascore,
    _load,
    extract_players,
    parse_match_info,
)
from v2.canonical_match_stats import PERIODS, _period_events, get_canonical_match_stats
from v2.canonical_metric_engine import calculate_canonical_metrics
from v2.database import DEFAULT_DB_PATH, connection
from v2.match_metric_leaders import get_match_metric_leaders, metric_catalog
from v2.metric_registry import BY_KEY, METRIC_SET_VERSION, MetricKind, MetricStatus, approved_for
from v2.team_logos import logo_url

app = FastAPI(title='MatchLab Studio API', version='2.1.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])


def _norm(value: str) -> str:
    value = unicodedata.normalize('NFKD', str(value or ''))
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]+', '', value.lower())


def _date(value: str) -> str | None:
    for fmt in ('%d %B %Y', '%d %b %Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except (TypeError, ValueError):
            pass
    return None


def _resolve_match(event_id: str) -> str:
    try:
        return str(get_canonical_match_stats(str(event_id), period='full')['match']['match_id'])
    except Exception:
        pass
    payload = _load(event_id)
    sofa = parse_match_info(payload['basic'])
    iso = _date(sofa.date_text)
    if not iso:
        raise HTTPException(404, 'Could not resolve imported match date in canonical V2 database.')
    with connection(DEFAULT_DB_PATH, read_only=True) as conn:
        rows = conn.execute(
            '''SELECT m.match_id,h.team_name,a.team_name
               FROM matches m JOIN teams h ON h.team_id=m.home_team_id JOIN teams a ON a.team_id=m.away_team_id
               WHERE CAST(m.match_date AS DATE)=CAST(? AS DATE)''', [iso]
        ).fetchall()
    for match_id, home, away in rows:
        if _norm(home) == _norm(sofa.home_name) and _norm(away) == _norm(sofa.away_name):
            return str(match_id)
    raise HTTPException(404, f'Could not link {sofa.home_name} v {sofa.away_name} to canonical V2.')


def _live_specs():
    return tuple(s for s in approved_for('live') if s.status is MetricStatus.IMPLEMENT and s.kind is MetricKind.SCALAR)


def _display(label: str, value: float | None) -> str:
    if value is None:
        return '—'
    num = float(value)
    text = str(int(num)) if num.is_integer() else f'{num:.1f}'.rstrip('0').rstrip('.')
    if '%' in label or 'Accuracy' in label or 'Percentage' in label or label == 'Possession':
        text += '%'
    return text


def _resolve_player(match_id: str, player_name: str) -> tuple[str, str, str]:
    target = _norm(player_name)
    with connection(DEFAULT_DB_PATH, read_only=True) as conn:
        rows = conn.execute(
            '''SELECT DISTINCT p.player_id,p.player_name,cmv.team_id
               FROM canonical_metric_values cmv JOIN players p ON p.player_id=cmv.player_id
               WHERE cmv.metric_set_version=? AND cmv.match_id=? AND cmv.scope='player' ''',
            [METRIC_SET_VERSION, match_id]
        ).fetchall()
    for pid, name, team_id in rows:
        if _norm(name) == target:
            return str(pid), str(name), str(team_id)
    raise HTTPException(404, f'Could not link {player_name} to canonical V2 player.')


def _stored_player(match_id: str, player_id: str) -> dict[str, float | None]:
    with connection(DEFAULT_DB_PATH, read_only=True) as conn:
        rows = conn.execute(
            '''SELECT metric_key,metric_value FROM canonical_metric_values
               WHERE metric_set_version=? AND match_id=? AND scope='player' AND player_id=?''',
            [METRIC_SET_VERSION, match_id, player_id]
        ).fetchall()
    return {str(k): (None if v is None else float(v)) for k, v in rows}


def _period_player(match_id: str, player_id: str, team_id: str, period_name: str) -> dict[str, float | None]:
    sig = inspect.signature(calculate_canonical_metrics)
    kwargs: dict[str, Any] = {'surface': 'live', 'player_id': player_id}
    if 'team_id' in sig.parameters:
        kwargs['team_id'] = team_id
    result = calculate_canonical_metrics(_period_events(match_id, period_name), **kwargs)
    return {str(k): (None if v is None else float(v)) for k, v in result['metrics'].items()}


def _player_rows(match_id: str, player_id: str, team_id: str, period: str):
    if period not in PERIODS:
        raise HTTPException(400, 'period must be full, first_half or second_half')
    p = PERIODS[period]
    metrics = _stored_player(match_id, player_id) if p is None else _period_player(match_id, player_id, team_id, p)
    out = []
    for spec in _live_specs():
        value = metrics.get(spec.key)
        if value is not None:
            out.append({'key': spec.key, 'label': spec.label, 'value': value, 'display': _display(spec.label, value)})
    return out


def _period_leaders(match_id: str, metric: str, period: str, team_id: str | None, limit: int):
    if period == 'full':
        return get_match_metric_leaders(match_id, metric, team_id=team_id, limit=limit)
    spec = BY_KEY.get(metric)
    if not spec or spec.status is not MetricStatus.IMPLEMENT or 'live' not in spec.surfaces:
        raise HTTPException(404, 'Metric is not available for Metric Leaders.')
    period_name = PERIODS.get(period)
    if not period_name:
        raise HTTPException(400, 'period must be full, first_half or second_half')
    with connection(DEFAULT_DB_PATH, read_only=True) as conn:
        params: list[Any] = [METRIC_SET_VERSION, match_id]
        clause = ''
        if team_id:
            clause = ' AND cmv.team_id=?'; params.append(team_id)
        players = conn.execute(
            '''SELECT DISTINCT cmv.player_id,p.player_name,cmv.team_id,t.team_name
               FROM canonical_metric_values cmv JOIN players p ON p.player_id=cmv.player_id JOIN teams t ON t.team_id=cmv.team_id
               WHERE cmv.metric_set_version=? AND cmv.match_id=? AND cmv.scope='player' ''' + clause,
            params
        ).fetchall()
    events = _period_events(match_id, period_name)
    rows = []
    for pid, name, tid, team in players:
        result = calculate_canonical_metrics(events, team_id=str(tid), player_id=str(pid), surface='live')
        value = result['metrics'].get(metric)
        if isinstance(value, (int, float)) and float(value) > 0:
            rows.append({'player_id': str(pid), 'player_name': str(name), 'team_id': str(tid), 'team_name': str(team), 'team_logo_url': logo_url(str(team)), 'value': float(value)})
    rows.sort(key=lambda r: (-r['value'], r['player_name']))
    rows = rows[:limit]
    top = rows[0]['value'] if rows else 0
    for rank, row in enumerate(rows, 1):
        row['rank'] = rank; row['relative_to_leader'] = row['value'] / top if top else 0
    return {'match_id': match_id, 'metric': metric, 'label': spec.label, 'period': period, 'leaders': rows, 'catalog': metric_catalog()}


@app.get('/health')
def health():
    return {'ok': True, 'service': 'matchlab-studio-api', 'mode': 'canonical-v2'}


@app.post('/matches/import-sofascore')
def import_sofascore(request: SofaScoreImportRequest):
    return legacy_import_sofascore(request)


@app.get('/matches/{event_id}')
def base_match(event_id: str):
    payload = _load(event_id)
    match = parse_match_info(payload['basic'])
    players = extract_players(payload['lineups'], match)
    return {
        'match': match.__dict__,
        'players': [{'id': p.player_id, 'name': p.name, 'team': p.team, 'opponent': p.opponent, 'side': p.side} for p in players],
        'metrics': metric_catalog(),
    }


@app.get('/matches/{event_id}/canonical')
def canonical_match(event_id: str, period: str = Query('full')):
    match_id = _resolve_match(event_id)
    try:
        data = get_canonical_match_stats(match_id, period=period)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {'event_id': event_id, 'canonical_match_id': match_id, **data}


@app.get('/matches/{event_id}/canonical-player/{player_id}')
def canonical_player(event_id: str, player_id: str, period: str = Query('full')):
    payload = _load(event_id)
    sofa_match = parse_match_info(payload['basic'])
    players = extract_players(payload['lineups'], sofa_match)
    sofa = next((p for p in players if str(p.player_id) == str(player_id)), None)
    if not sofa:
        raise HTTPException(404, 'Player not found in imported SofaScore lineup.')
    match_id = _resolve_match(event_id)
    canonical_id, name, team_id = _resolve_player(match_id, sofa.name)
    return {
        'event_id': event_id,
        'canonical_match_id': match_id,
        'period': period,
        'player': {'id': str(player_id), 'canonical_player_id': canonical_id, 'name': name, 'team': sofa.team, 'opponent': sofa.opponent, 'side': sofa.side},
        'rows': _player_rows(match_id, canonical_id, team_id, period),
        'metric_set_version': METRIC_SET_VERSION,
    }


@app.get('/matches/{event_id}/canonical-leaders/{metric}')
def canonical_leaders(event_id: str, metric: str, period: str = Query('full'), scope: str = Query('all'), limit: int = Query(10, ge=1, le=20)):
    match_id = _resolve_match(event_id)
    full = get_canonical_match_stats(match_id, period='full')
    team_id = None
    if scope == 'home': team_id = str(full['match']['home_team_id'])
    elif scope == 'away': team_id = str(full['match']['away_team_id'])
    elif scope != 'all': raise HTTPException(400, 'scope must be all, home or away')
    return {'event_id': event_id, 'canonical_match_id': match_id, **_period_leaders(match_id, metric, period, team_id, limit)}
