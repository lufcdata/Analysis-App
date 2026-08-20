"""Canonical season -> matchday -> match inventory for the Match Report UI."""
from __future__ import annotations

from pathlib import Path

from .database import DEFAULT_DB_PATH, connection
from .team_logos import logo_url


def _matchday_column_exists(conn) -> bool:
    columns = {row[1] for row in conn.execute("PRAGMA table_info('matches')").fetchall()}
    return 'matchday' in columns


def get_match_inventory(*, season_id: str | None = None, matchday: int | None = None, db_path: str | Path = DEFAULT_DB_PATH) -> dict:
    if matchday is not None and not 1 <= int(matchday) <= 38:
        raise ValueError('matchday must be between 1 and 38')

    with connection(db_path, read_only=True) as conn:
        has_matchday = _matchday_column_exists(conn)
        seasons = [
            {
                'season_id': row[0],
                'season_name': row[1],
                'start_date': str(row[2]) if row[2] is not None else None,
                'end_date': str(row[3]) if row[3] is not None else None,
                'status': row[4],
            }
            for row in conn.execute(
                "SELECT season_id, season_name, start_date, end_date, status FROM seasons ORDER BY start_date, season_name"
            ).fetchall()
        ]

        clauses: list[str] = []
        args: list[object] = []
        if season_id:
            clauses.append('m.season_id = ?')
            args.append(season_id)
        if matchday is not None:
            if not has_matchday:
                return {'seasons': seasons, 'matches': [], 'matchday_available': False}
            clauses.append('m.matchday = ?')
            args.append(int(matchday))
        where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
        matchday_select = 'm.matchday' if has_matchday else 'NULL AS matchday'
        rows = conn.execute(
            f"""
            SELECT m.match_id, m.season_id, s.season_name, {matchday_select}, m.match_date, m.kickoff_time,
                   m.home_team_id, ht.team_name, m.away_team_id, at.team_name,
                   m.home_score, m.away_score, m.status, m.whoscored_ingested, m.sofascore_ingested
            FROM matches m
            JOIN seasons s ON s.season_id = m.season_id
            JOIN teams ht ON ht.team_id = m.home_team_id
            JOIN teams at ON at.team_id = m.away_team_id
            {where}
            ORDER BY s.start_date, m.matchday NULLS LAST, m.match_date, m.kickoff_time, m.match_id
            """,
            args,
        ).fetchall()

    matches = [
        {
            'match_id': row[0], 'season_id': row[1], 'season_name': row[2], 'matchday': row[3],
            'date': str(row[4]), 'kickoff_time': row[5].isoformat() if row[5] is not None else None,
            'home_team_id': row[6], 'home_team': row[7], 'home_logo_url': logo_url(row[7]),
            'away_team_id': row[8], 'away_team': row[9], 'away_logo_url': logo_url(row[9]),
            'home_score': row[10], 'away_score': row[11], 'status': row[12],
            'whoscored_ingested': bool(row[13]), 'sofascore_ingested': bool(row[14]),
        }
        for row in rows
    ]
    return {'seasons': seasons, 'matches': matches, 'matchday_available': has_matchday}
