"""Read-only inventory for an R2 DuckDB snapshot.

Downloads an R2 object to a temporary/local path, opens it read-only with DuckDB,
and reports schema/data fidelity without modifying or publishing the snapshot.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import boto3
import duckdb
from botocore.client import Config


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def download_snapshot(key: str, destination: Path) -> None:
    account_id = _env("R2_ACCOUNT_ID")
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=_env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_env("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(_env("R2_BUCKET"), key, str(destination))


def _columns(conn: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    return [str(row[1]) for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall()]


def _count(conn: duckdb.DuckDBPyConnection, table: str) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def _scalar(conn: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None) -> Any:
    return conn.execute(sql, params or []).fetchone()[0]


def inspect_snapshot(path: Path, key: str) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        raise ValueError(f"Downloaded snapshot is missing or empty: {path}")

    conn = duckdb.connect(str(path), read_only=True)
    try:
        tables = sorted(str(row[0]) for row in conn.execute("SHOW TABLES").fetchall())
        schemas = {table: _columns(conn, table) for table in tables}
        row_counts = {table: _count(conn, table) for table in tables}

        report: dict[str, Any] = {
            "r2_key": key,
            "file_bytes": path.stat().st_size,
            "tables": tables,
            "row_counts": row_counts,
            "schemas": schemas,
        }

        # Match/season coverage.
        if "matches" in tables:
            mcols = set(schemas["matches"])
            matches: dict[str, Any] = {"rows": row_counts["matches"]}
            if "season_id" in mcols:
                matches["by_season"] = [
                    {"season_id": str(row[0]), "matches": int(row[1])}
                    for row in conn.execute(
                        "SELECT season_id, COUNT(*) FROM matches GROUP BY season_id ORDER BY COUNT(*) DESC"
                    ).fetchall()
                ]
            for provider_col in ("whoscored_ingested", "sofascore_ingested"):
                if provider_col in mcols:
                    matches[provider_col] = int(_scalar(conn, f"SELECT COUNT(*) FROM matches WHERE {provider_col}"))
            if "whoscored_match_id" in mcols:
                matches["distinct_whoscored_match_ids"] = int(
                    _scalar(conn, "SELECT COUNT(DISTINCT whoscored_match_id) FROM matches WHERE whoscored_match_id IS NOT NULL")
                )
            report["matches"] = matches

        # WhoScored event fidelity.
        if "match_events" in tables:
            ecols = set(schemas["match_events"])
            events: dict[str, Any] = {"rows": row_counts["match_events"]}
            if "source" in ecols:
                events["by_source"] = [
                    {"source": str(row[0]), "rows": int(row[1])}
                    for row in conn.execute(
                        "SELECT COALESCE(source, '<null>'), COUNT(*) FROM match_events GROUP BY 1 ORDER BY 2 DESC"
                    ).fetchall()
                ]
            if {"source", "event_type"}.issubset(ecols):
                events["whoscored_by_event_type"] = [
                    {"event_type": str(row[0]), "rows": int(row[1])}
                    for row in conn.execute(
                        """SELECT COALESCE(event_type, '<null>'), COUNT(*)
                           FROM match_events
                           WHERE lower(COALESCE(source, ''))='whoscored'
                           GROUP BY 1 ORDER BY 2 DESC, 1"""
                    ).fetchall()
                ]
                events["raw_whoscored_rows"] = int(
                    _scalar(
                        conn,
                        """SELECT COUNT(*) FROM match_events
                           WHERE lower(COALESCE(source, ''))='whoscored' AND event_type='raw_whoscored'""",
                    )
                )
            if "metadata_json" in ecols:
                events["metadata_json_nonempty_rows"] = int(
                    _scalar(conn, "SELECT COUNT(*) FROM match_events WHERE metadata_json IS NOT NULL AND length(CAST(metadata_json AS VARCHAR)) > 2")
                )
            for col in ("x", "y", "end_x", "end_y", "player_id", "team_id", "expanded_minute", "period"):
                if col in ecols:
                    events[f"{col}_non_null_rows"] = int(_scalar(conn, f"SELECT COUNT(*) FROM match_events WHERE {col} IS NOT NULL"))
            report["match_events"] = events

        # Core metric-store source tables.
        for table in ("player_match_stats", "team_match_stats"):
            if table not in tables:
                continue
            cols = set(schemas[table])
            data: dict[str, Any] = {"rows": row_counts[table]}
            if "season_id" in cols:
                data["by_season"] = [
                    {"season_id": str(row[0]), "rows": int(row[1])}
                    for row in conn.execute(
                        f"SELECT season_id, COUNT(*) FROM {table} GROUP BY season_id ORDER BY COUNT(*) DESC"
                    ).fetchall()
                ]
            report[table] = data

        # Player reference enrichment coverage.
        if "players" in tables:
            pcols = set(schemas["players"])
            players: dict[str, Any] = {"rows": row_counts["players"]}
            for col in ("nationality", "date_of_birth", "position", "fbref_player_id", "whoscored_player_id"):
                if col in pcols:
                    players[f"{col}_populated"] = int(
                        _scalar(conn, f"SELECT COUNT(*) FROM players WHERE {col} IS NOT NULL AND CAST({col} AS VARCHAR) <> ''")
                    )
            report["players"] = players

        # Explicit compatibility contract for the Analysis-App Metrics Bible source loader.
        required_raw_columns = {
            "match_id", "source", "event_type", "metadata_json", "event_id"
        }
        event_columns = set(schemas.get("match_events", []))
        report["analysis_app_raw_contract"] = {
            "required_columns": sorted(required_raw_columns),
            "missing_columns": sorted(required_raw_columns - event_columns),
            "raw_whoscored_rows": int(report.get("match_events", {}).get("raw_whoscored_rows", 0)),
            "compatible_now": not (required_raw_columns - event_columns)
            and int(report.get("match_events", {}).get("raw_whoscored_rows", 0)) > 0,
        }

        return report
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect an R2 DuckDB snapshot without writing to R2")
    parser.add_argument("--key", default="football/staging/2025-26.duckdb")
    parser.add_argument("--db", default="/tmp/r2-inspect.duckdb")
    parser.add_argument("--report", default="/tmp/r2-snapshot-inventory.json")
    args = parser.parse_args()

    db_path = Path(args.db)
    report_path = Path(args.report)
    db_path.unlink(missing_ok=True)
    download_snapshot(args.key, db_path)
    report = inspect_snapshot(db_path, args.key)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"wrote_report={report_path}")


if __name__ == "__main__":
    main()
