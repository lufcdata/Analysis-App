from __future__ import annotations

import json
from dataclasses import dataclass

from .canonical_touch_metrics import canonical_touch_events
from .database import DEFAULT_DB_PATH, connection
from .match_timing import get_match_timing
from .team_logos import logo_url


@dataclass(frozen=True)
class SpatialFilter:
    team_id: str | None = None
    player_ids: tuple[str, ...] = ()
    periods: tuple[str, ...] = ()
    start_seconds: int | None = None
    end_seconds: int | None = None


def _clamp100(value):
    return None if value is None else max(0.0, min(100.0, float(value)))


def canonical_to_portrait(x, y):
    cx, cy = _clamp100(x), _clamp100(y)
    return (None, None) if cx is None or cy is None else (cy, 100.0 - cx)


def _table_columns(conn, table: str) -> set[str]:
    try:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall()}
    except Exception:
        return set()


def _where(f, alias=""):
    p = f"{alias}." if alias else ""; c = []; a = []
    if f.team_id: c.append(f"{p}team_id=?"); a.append(f.team_id)
    if f.player_ids:
        m = ','.join('?' for _ in f.player_ids); c.append(f"{p}player_id IN ({m})"); a.extend(f.player_ids)
    if f.periods:
        m = ','.join('?' for _ in f.periods); c.append(f"{p}period IN ({m})"); a.extend(f.periods)
    if f.start_seconds is not None: c.append(f"COALESCE({p}time_seconds,0)>=?"); a.append(int(f.start_seconds))
    if f.end_seconds is not None: c.append(f"COALESCE({p}time_seconds,0)<=?"); a.append(int(f.end_seconds))
    return (' AND ' + ' AND '.join(c)) if c else '', a


def _event_row(r):
    event_id, team_id, player_id, event_type, period, minute, second, time_seconds, x, y, end_x, end_y, outcome, source = r
    sx, sy = canonical_to_portrait(x, y); ex, ey = canonical_to_portrait(end_x, end_y)
    return {'event_id': event_id, 'team_id': team_id, 'player_id': player_id, 'event_type': event_type, 'period': period,
            'minute': minute, 'second': second, 'time_seconds': time_seconds, 'x': x, 'y': y, 'end_x': end_x, 'end_y': end_y,
            'portrait_x': sx, 'portrait_y': sy, 'portrait_end_x': ex, 'portrait_end_y': ey, 'outcome': outcome, 'source': source}


def _metadata(value):
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value))
        return dict(parsed) if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def get_passes(conn, match_id, f):
    if not _table_columns(conn, 'match_passes'):
        return []
    w, a = _where(f); w = w.replace('player_id IN', 'passer_id IN')
    rows = conn.execute("SELECT source_pass_id,team_id,passer_id,receiver_id,successful,receiver_method,receiver_confidence,period,minute,second,time_seconds,x,y,end_x,end_y,source FROM match_passes WHERE match_id=?" + w + " ORDER BY time_seconds,source_pass_id", [match_id] + a).fetchall()
    out = []
    for r in rows:
        sid, tid, pid, rid, ok, method, conf, period, minute, second, ts, x, y, ex, ey, source = r
        sx, sy = canonical_to_portrait(x, y); px, py = canonical_to_portrait(ex, ey)
        out.append({'pass_id': sid, 'team_id': tid, 'passer_id': pid, 'receiver_id': rid, 'successful': bool(ok), 'receiver_method': method,
                    'receiver_confidence': conf, 'period': period, 'minute': minute, 'second': second, 'time_seconds': ts,
                    'x': x, 'y': y, 'end_x': ex, 'end_y': ey, 'portrait_x': sx, 'portrait_y': sy, 'portrait_end_x': px, 'portrait_end_y': py, 'source': source})
    return out


def get_headline_passes(conn, match_id, f):
    w, a = _where(f)
    rows = conn.execute("SELECT event_id,team_id,player_id,event_type,period,minute,second,time_seconds,x,y,end_x,end_y,outcome,source FROM match_events WHERE match_id=? AND source='whoscored' AND event_type IN ('accurate_pass','unsuccessful_pass')" + w + " ORDER BY time_seconds,event_id", [match_id] + a).fetchall()
    out = []
    for r in rows:
        event = _event_row(r)
        out.append({'pass_id': event['event_id'], 'team_id': event['team_id'], 'passer_id': event['player_id'], 'receiver_id': None,
                    'successful': event['event_type'] == 'accurate_pass', 'period': event['period'], 'minute': event['minute'], 'second': event['second'],
                    'time_seconds': event['time_seconds'], 'x': event['x'], 'y': event['y'], 'end_x': event['end_x'], 'end_y': event['end_y'],
                    'portrait_x': event['portrait_x'], 'portrait_y': event['portrait_y'], 'portrait_end_x': event['portrait_end_x'],
                    'portrait_end_y': event['portrait_end_y'], 'source': event['source'], 'headline_event_type': event['event_type']})
    return out


def get_event_layer(conn, match_id, event_types, f):
    types = tuple(event_types)
    if not types: return []
    w, a = _where(f); m = ','.join('?' for _ in types)
    rows = conn.execute("SELECT event_id,team_id,player_id,event_type,period,minute,second,time_seconds,x,y,end_x,end_y,outcome,source FROM match_events WHERE match_id=? AND event_type IN (" + m + ")" + w + " ORDER BY time_seconds,event_id", [match_id] + list(types) + a).fetchall()
    return [_event_row(r) for r in rows]


def _raw_touch_source_events(conn, match_id):
    rows = conn.execute(
        """SELECT event_id,team_id,player_id,period,minute,expanded_minute,second,time_seconds,
                  x,y,end_x,end_y,outcome,source,metadata_json
           FROM match_events
           WHERE match_id=? AND lower(source)='whoscored' AND event_type='raw_whoscored'
           ORDER BY time_seconds,event_id""",
        [match_id],
    ).fetchall()
    events = []
    for event_id, team_id, player_id, period, minute, expanded_minute, second, time_seconds, x, y, end_x, end_y, outcome, source, metadata_json in rows:
        event = _metadata(metadata_json)
        event.update({
            'eventId': event.get('eventId', event.get('id', event_id)),
            'teamId': None if team_id is None else str(team_id),
            'playerId': None if player_id is None else str(player_id),
            'period': {'displayName': period},
            'minute': minute,
            'expandedMinute': expanded_minute if expanded_minute is not None else minute,
            'second': second,
            'time_seconds': time_seconds,
            'x': x,
            'y': y,
            'endX': end_x,
            'endY': end_y,
            '_outcome': outcome,
            '_source': source,
        })
        events.append(event)
    return events


def get_touches(conn, match_id, f):
    """Return Bible-defined touches from full-fidelity raw WhoScored events."""
    raw = _raw_touch_source_events(conn, match_id)
    out = []
    player_ids = set(f.player_ids)
    periods = set(f.periods)
    for event in canonical_touch_events(raw):
        team_id = event.get('teamId'); player_id = event.get('playerId')
        time_seconds = event.get('time_seconds')
        period = event.get('period'); period = period.get('displayName') if isinstance(period, dict) else period
        if f.team_id and team_id != f.team_id: continue
        if player_ids and player_id not in player_ids: continue
        if periods and period not in periods: continue
        if f.start_seconds is not None and (time_seconds or 0) < f.start_seconds: continue
        if f.end_seconds is not None and (time_seconds or 0) > f.end_seconds: continue
        x, y = event.get('x'), event.get('y')
        if x is None or y is None: continue
        end_x, end_y = event.get('endX'), event.get('endY')
        sx, sy = canonical_to_portrait(x, y); ex, ey = canonical_to_portrait(end_x, end_y)
        etype = event.get('type'); etype = etype.get('displayName') if isinstance(etype, dict) else etype
        out.append({
            'event_id': str(event.get('eventId', event.get('id'))), 'team_id': team_id, 'player_id': player_id,
            'event_type': etype or 'touch', 'period': period, 'minute': event.get('minute'), 'second': event.get('second'),
            'time_seconds': time_seconds, 'x': x, 'y': y, 'end_x': end_x, 'end_y': end_y,
            'portrait_x': sx, 'portrait_y': sy, 'portrait_end_x': ex, 'portrait_end_y': ey,
            'outcome': event.get('_outcome'), 'source': event.get('_source') or 'whoscored',
        })
    return out


def get_average_positions(conn, match_id, f):
    touches = get_touches(conn, match_id, f); groups = {}
    for t in touches:
        if not t['player_id']: continue
        g = groups.setdefault((t['player_id'], t['team_id']), [0., 0., 0]); g[0] += float(t['x']); g[1] += float(t['y']); g[2] += 1
    names = {str(r[0]): r[1] for r in conn.execute("SELECT player_id,player_name FROM players").fetchall()}; out = []
    for (pid, tid), (sx, sy, n) in groups.items():
        ax, ay = sx/n, sy/n; px, py = canonical_to_portrait(ax, ay)
        out.append({'player_id': pid, 'player_name': names.get(str(pid)), 'team_id': tid, 'avg_x': ax, 'avg_y': ay, 'portrait_x': px, 'portrait_y': py, 'touch_count': n})
    return sorted(out, key=lambda r: (-r['touch_count'], r['player_name'] or ''))


def get_carry_readiness(conn, match_id, f):
    columns = _table_columns(conn, 'player_match_stats')
    required = {'ball_carries','progressive_carries','carry_distance_m','progressive_carry_distance_m','sofascore_carries_complete'}
    if not required.issubset(columns):
        return {'event_coordinates_available': False, 'reason': 'Carry enrichment is not present in this snapshot.',
                'ball_carries': 0, 'progressive_carries': 0, 'carry_distance_m': 0.0,
                'progressive_carry_distance_m': 0.0, 'sofascore_complete': False}
    c = ['pms.match_id=?']; a = [match_id]
    if f.team_id: c.append('pms.team_id=?'); a.append(f.team_id)
    if f.player_ids:
        m = ','.join('?' for _ in f.player_ids); c.append(f'pms.player_id IN ({m})'); a.extend(f.player_ids)
    total, prog, dist, pdist, complete = conn.execute("SELECT COALESCE(SUM(ball_carries),0),COALESCE(SUM(progressive_carries),0),COALESCE(SUM(carry_distance_m),0),COALESCE(SUM(progressive_carry_distance_m),0),BOOL_OR(sofascore_carries_complete) FROM player_match_stats pms WHERE " + ' AND '.join(c), a).fetchone()
    return {'event_coordinates_available': False, 'reason': 'Validated SofaScore carry totals/distances exist; event-level coordinates are not yet exposed in V2.',
            'ball_carries': int(total or 0), 'progressive_carries': int(prog or 0), 'carry_distance_m': float(dist or 0),
            'progressive_carry_distance_m': float(pdist or 0), 'sofascore_complete': bool(complete)}


def build_match_spatial_payload(match_id, *, team_id=None, player_ids=None, periods=None, start_seconds=None, end_seconds=None, db_path=DEFAULT_DB_PATH):
    f = SpatialFilter(team_id, tuple(player_ids or ()), tuple(periods or ()), start_seconds, end_seconds)
    with connection(db_path, read_only=True) as conn:
        columns = _table_columns(conn, 'matches')
        optional = lambda name, fallback='NULL': f"m.{name}" if name in columns else fallback
        m = conn.execute(
            f"""SELECT m.match_id,m.match_date,m.home_team_id,ht.team_name,m.away_team_id,awt.team_name,
                       {optional('home_score')},{optional('away_score')},
                       {optional('whoscored_ingested','FALSE')},{optional('sofascore_ingested','FALSE')}
                FROM matches m
                JOIN teams ht ON ht.team_id=m.home_team_id
                JOIN teams awt ON awt.team_id=m.away_team_id
                WHERE m.match_id=?""",
            [match_id],
        ).fetchone()
        if not m: raise ValueError(f'Unknown V2 match_id: {match_id}')
        timing = get_match_timing(conn, match_id)
        slider = {'min_seconds': 0, 'max_seconds': timing['full_time_seconds'] if timing['timing_complete'] else None,
                  'max_display': timing['full_time_display'] if timing['timing_complete'] else None, 'step_seconds': 1, 'authoritative': timing['timing_complete']}
        touches = get_touches(conn, match_id, f)
        average_positions = get_average_positions(conn, match_id, f)
        return {'coordinate_system': {'canonical': 'WhoScored native 0-100 x 0-100; consumer may plot x/y directly without mutation',
                                      'portrait': 'legacy compatibility only: screen_x=y; screen_y=100-x', 'physical_pitch_m': {'length': 105., 'width': 68.}},
                'match': {'match_id': m[0], 'date': str(m[1]), 'home_team_id': m[2], 'home_team': m[3], 'home_logo_url': logo_url(m[3]),
                          'away_team_id': m[4], 'away_team': m[5], 'away_logo_url': logo_url(m[5]), 'home_score': m[6], 'away_score': m[7],
                          'whoscored_ingested': bool(m[8]), 'sofascore_ingested': bool(m[9])},
                'timing': timing, 'time_slider': slider,
                'filters': {'team_id': team_id, 'player_ids': list(player_ids or ()), 'periods': list(periods or ()), 'start_seconds': start_seconds, 'end_seconds': end_seconds},
                'passes': get_passes(conn, match_id, f), 'headline_passes': get_headline_passes(conn, match_id, f),
                'shots': get_event_layer(conn, match_id, ('shot','shot_xg'), f), 'goals': get_event_layer(conn, match_id, ('goal',), f),
                'touches': touches, 'average_positions': average_positions,
                'carries': [], 'carry_readiness': get_carry_readiness(conn, match_id, f)}
