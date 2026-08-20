from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import boto3
import duckdb
from botocore.client import Config


def client_from_env():
    account = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def table_columns(conn, table: str) -> set[str]:
    try:
        return {str(r[1]) for r in conn.execute(f"PRAGMA table_info('{table}')").fetchall()}
    except Exception:
        return set()


def scalar(conn, sql: str):
    try:
        return conn.execute(sql).fetchone()[0]
    except Exception:
        return None


def inspect_db(path: Path) -> dict:
    conn = duckdb.connect(str(path), read_only=True)
    try:
        tables = sorted(r[0] for r in conn.execute("SHOW TABLES").fetchall())
        out = {"tables": tables}
        for table in ("matches", "teams", "players", "match_events", "player_match_stats", "team_match_stats", "canonical_metric_values", "canonical_player_exposure"):
            if table in tables:
                out[f"{table}_rows"] = scalar(conn, f"SELECT COUNT(*) FROM {table}")

        if "matches" in tables:
            mcols = table_columns(conn, "matches")
            if "whoscored_match_id" in mcols:
                out["distinct_whoscored_matches"] = scalar(conn, "SELECT COUNT(DISTINCT whoscored_match_id) FROM matches WHERE whoscored_match_id IS NOT NULL")

        if "match_events" in tables:
            cols = table_columns(conn, "match_events")
            out["match_events_columns"] = sorted(cols)
            if "source" in cols:
                out["whoscored_event_rows"] = scalar(conn, "SELECT COUNT(*) FROM match_events WHERE lower(source)='whoscored'")
            if {"source", "event_type"}.issubset(cols):
                out["raw_whoscored_rows"] = scalar(conn, "SELECT COUNT(*) FROM match_events WHERE lower(source)='whoscored' AND event_type='raw_whoscored'")
                out["raw_whoscored_matches"] = scalar(conn, "SELECT COUNT(DISTINCT match_id) FROM match_events WHERE lower(source)='whoscored' AND event_type='raw_whoscored'")
                out["top_whoscored_event_types"] = conn.execute(
                    "SELECT event_type, COUNT(*) n FROM match_events WHERE lower(source)='whoscored' GROUP BY event_type ORDER BY n DESC LIMIT 40"
                ).fetchall()
            if "metadata_json" in cols:
                out["metadata_nonempty_rows"] = scalar(conn, "SELECT COUNT(*) FROM match_events WHERE metadata_json IS NOT NULL AND length(CAST(metadata_json AS VARCHAR)) > 2")
        return out
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="football/")
    ap.add_argument("--report", default="/tmp/r2-duckdb-inventory.json")
    args = ap.parse_args()

    bucket = os.environ["R2_BUCKET"]
    s3 = client_from_env()
    paginator = s3.get_paginator("list_objects_v2")
    objects = []
    for page in paginator.paginate(Bucket=bucket, Prefix=args.prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(".duckdb"):
                objects.append({"key": key, "size": int(obj["Size"]), "last_modified": obj["LastModified"].isoformat()})

    report = {"bucket": bucket, "prefix": args.prefix, "duckdb_object_count": len(objects), "objects": []}
    for i, obj in enumerate(sorted(objects, key=lambda x: x["key"]), 1):
        print(f"[{i}/{len(objects)}] {obj['key']} ({obj['size']/1024/1024:.2f} MiB)", flush=True)
        with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        row = dict(obj)
        try:
            s3.download_file(bucket, obj["key"], str(tmp_path))
            row["inspection"] = inspect_db(tmp_path)
            print(json.dumps({"key": obj["key"], "inspection": row["inspection"]}, default=str), flush=True)
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            print(f"ERROR {obj['key']}: {row['error']}", flush=True)
        finally:
            tmp_path.unlink(missing_ok=True)
        report["objects"].append(row)

    Path(args.report).write_text(json.dumps(report, indent=2, default=str))
    print(f"wrote_report={args.report}")


if __name__ == "__main__":
    main()
