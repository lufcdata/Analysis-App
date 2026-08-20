"""Canonical season -> matchday -> match inventory for the Match Report UI."""
from __future__ import annotations

from pathlib import Path

from .database import DEFAULT_DB_PATH, connection
from .team_logos import logo_url


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall()}


def _optional(alias: str, column: str, columns: set[str], *, default: str = "NULL") -> str:
    return f"{alias}.{column}" if column in columns else f"{default} AS {column}"


def get_match_inventory(*, season_id: str | None = None, matchday: int | None = None, db_path: str | Path = DEFAULT_DB_PATH) -> dict:
    if matchday is not None and not 1 <= int(matchday) <= 38:
        raise ValueError('matchday must be between 1 and 38')

    with connection(db_path, read_only=True) as conn:
        match_columns = _columns(conn, 'matches')
        season_columns = _columns(conn, 'seasons')
        has_matchday = 'matchday' in match_columns

        season_start = _optional('s', 'start_date', season_columns)
        season_end = _optional('s', 'end_date', season_columns)
        season_status = _optional('s', 'status', season_columns)
        season_order = 's.start_date, ' if 'start_date' in season_columns else ''
        seasons = [
            {
                'season_id': row[0],
                'season_name': row[1],
                'start_date': str(row[2]) if row[2] is not None else None,
                'end_date': str(row[3]) if row[3] is not None else None,
                'status': row[4],
            }
            for row in conn.execute(
                f"SELECT s.season_id, s.season_name, {season_start}, {season_end}, {season_status} "
                f"FROM seasons s ORDER BY {season_order}s.season_name"
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

        matchday_select = _optional('m', 'matchday', match_columns)
        kickoff_select = _optional('m', 'kickoff_time', match_columns)
        home_score_select = _optional('m', 'home_score', match_columns)
        away_score_select = _optional('m', 'away_score', match_columns)
        status_select = _optional('m', 'status', match_columns)
        whoscored_select = _optional('m', 'whoscored_ingested', match_columns, default='FALSE')
        sofascore_select = _optional('m', 'sofascore_ingested', match_columns, default='FALSE')

        order_parts: list[str] = []
        if 'start_date' in season_columns:
            order_parts.append('s.start_date')
        if has_matchday:
            order_parts.append('m.matchday NULLS LAST')
        order_parts.append('m.match_date')
        if 'kickoff_time' in match_columns:
            order_parts.append('m.kickoff_time')
        order_parts.append('m.match_id')
        order_by = ', '.join(order_parts)

        rows = conn.execute(
            f"""
            SELECT m.match_id, m.season_id, s.season_name, {matchday_select}, m.match_date, {kickoff_select},
                   m.home_team_id, ht.team_name, m.away_team_id, at.team_name,
                   {home_score_select}, {away_score_select}, {status_select}, {whoscored_select}, {sofascore_select}
            FROM matches m
            JOIN seasons s ON s.season_id = m.season_id
            JOIN teams ht ON ht.team_id = m.home_team_id
            JOIN teams at ON at.team_id = m.away_team_id
            {where}
            ORDER BY {order_by}
            """,
            args,
        ).fetchall()

    matches = [
        {
            'match_id': row[0], 'season_id': row[1], 'season_name': row[2], 'matchday': row[3],
            'date': str(row[4]), 'kickoff_time': row[5].isoformat() if hasattr(row[5], 'isoformat') else (str(row[5]) if row[5] is not None else None),
            'home_team_id': row[6], 'home_team': row[7], 'home_logo_url': logo_url(row[7]),
            'away_team_id': row[8], 'away_team': row[9], 'away_logo_url': logo_url(row[9]),
            'home_score': row[10], 'away_score': row[11], 'status': row[12],
            'whoscored_ingested': bool(row[13]), 'sofascore_ingested': bool(row[14]),
        }
        for row in rows
    ]
    return {'seasons': seasons, 'matches': matches, 'matchday_available': has_matchday}
