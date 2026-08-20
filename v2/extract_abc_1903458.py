from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import boto3
import duckdb
import pandas as pd

MATCH_ID = "1903458"
GOLDEN_SHA256 = "cb037d6c8c69b6d83a93fffbb404de92429c45268752d5f3d05d599edb145093"


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_columns(con, table: str) -> list[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info({qident(table)})").fetchall()]


def find_matching_rows(con, table: str, needle: str):
    cols = table_columns(con, table)
    matches = []
    for col in cols:
        try:
            n = con.execute(
                f"SELECT COUNT(*) FROM {qident(table)} WHERE CAST({qident(col)} AS VARCHAR) = ?",
                [needle],
            ).fetchone()[0]
            if n:
                matches.append((col, int(n)))
        except Exception:
            pass
    return matches


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--r2-key", default="football/staging/2025-26-whoscored-cards.duckdb")
    ap.add_argument("--golden")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    a_summary = None
    if args.golden:
        golden = Path(args.golden)
        digest = hashlib.sha256(golden.read_bytes()).hexdigest()
        if digest != GOLDEN_SHA256:
            raise SystemExit(f"Golden fixture SHA mismatch: {digest}")
        payload = json.loads(golden.read_text(encoding="utf-8"))
        events = payload.get("events") or []
        a_summary = {
            "match_id": payload.get("matchId"),
            "events": len(events),
            "qualifier_instances": sum(len(e.get("qualifiers") or []) for e in events),
            "sha256": digest,
        }
        (out / "A_summary.json").write_text(json.dumps(a_summary, indent=2), encoding="utf-8")
    else:
        # A is a known locked reference but must not block inspection of C.
        a_summary = {
            "status": "not_materialized_in_this_run",
            "match_id": int(MATCH_ID),
            "known_events": 1472,
            "known_sha256": GOLDEN_SHA256,
            "note": "Locked A remains the historical golden reference; this run extracts C independently.",
        }
        (out / "A_reference.json").write_text(json.dumps(a_summary, indent=2), encoding="utf-8")

    endpoint = f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    db_path = out / "source.duckdb"
    s3.download_file(os.environ["R2_BUCKET"], args.r2_key, str(db_path))

    con = duckdb.connect(str(db_path), read_only=True)
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    report = {"r2_key": args.r2_key, "tables": tables, "match_id_search": {}}

    internal_ids = set()
    for table in [t for t in ["matches", "match_events"] if t in tables]:
        found = find_matching_rows(con, table, MATCH_ID)
        report["match_id_search"][table] = found
        if table == "matches" and found:
            predicates = [f"CAST({qident(c)} AS VARCHAR) = ?" for c, _ in found]
            params = [MATCH_ID] * len(predicates)
            dfm = con.execute(f"SELECT * FROM {qident(table)} WHERE " + " OR ".join(predicates), params).df()
            dfm.to_csv(out / "C_matches.csv", index=False)
            dfm.to_json(out / "C_matches.json", orient="records", indent=2, force_ascii=False)
            for candidate in ["match_id", "id"]:
                if candidate in dfm.columns:
                    internal_ids.update(str(v) for v in dfm[candidate].dropna().tolist())

    if "match_events" not in tables:
        raise SystemExit("match_events table missing")
    me_cols = table_columns(con, "match_events")
    report["match_events_columns"] = me_cols

    predicates = []
    params = []
    if "match_id" in me_cols:
        predicates.append(f"CAST({qident('match_id')} AS VARCHAR) = ?")
        params.append(MATCH_ID)
        for iid in sorted(internal_ids):
            if iid != MATCH_ID:
                predicates.append(f"CAST({qident('match_id')} AS VARCHAR) = ?")
                params.append(iid)
    for c in ["provider_match_id", "whoscored_match_id", "source_match_id"]:
        if c in me_cols:
            predicates.append(f"CAST({qident(c)} AS VARCHAR) = ?")
            params.append(MATCH_ID)
    if not predicates:
        raise SystemExit("No usable match identity column in match_events")

    df = con.execute(
        "SELECT * FROM match_events WHERE " + " OR ".join(predicates), params
    ).df()
    if df.empty:
        found = find_matching_rows(con, "match_events", MATCH_ID)
        report["match_id_search"]["match_events_fallback"] = found
        if found:
            preds = [f"CAST({qident(c)} AS VARCHAR) = ?" for c, _ in found]
            df = con.execute("SELECT * FROM match_events WHERE " + " OR ".join(preds), [MATCH_ID] * len(preds)).df()
    if df.empty:
        raise SystemExit("Could not locate match 1903458 rows in match_events")

    df.to_csv(out / "C_match_events.csv", index=False)
    df.to_json(out / "C_match_events.json", orient="records", indent=2, force_ascii=False)

    c_summary = {
        "rows": int(len(df)),
        "columns": [str(c) for c in df.columns],
    }
    for c in ["source", "event_type", "event_outcome"]:
        if c in df.columns:
            c_summary[f"{c}_counts"] = {str(k): int(v) for k, v in df[c].value_counts(dropna=False).items()}
    for c in ["x", "y", "end_x", "end_y", "metadata_json", "source_event_id"]:
        if c in df.columns:
            c_summary[f"non_null_{c}"] = int(df[c].notna().sum())
    report["C_summary"] = c_summary

    for table in ["player_match_stats", "team_match_stats"]:
        if table not in tables:
            continue
        cols = table_columns(con, table)
        if "match_id" not in cols:
            continue
        ids = [MATCH_ID] + sorted(i for i in internal_ids if i != MATCH_ID)
        qs = ",".join(["?"] * len(ids))
        statdf = con.execute(
            f"SELECT * FROM {qident(table)} WHERE CAST(match_id AS VARCHAR) IN ({qs})", ids
        ).df()
        statdf.to_csv(out / f"C_{table}.csv", index=False)
        statdf.to_json(out / f"C_{table}.json", orient="records", indent=2, force_ascii=False)
        report[f"{table}_rows"] = int(len(statdf))

    (out / "C_summary.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    con.close()
    db_path.unlink(missing_ok=True)
    print(json.dumps({"A_reference": a_summary, "C": c_summary, "identity": report["match_id_search"]}, indent=2, default=str))


if __name__ == "__main__":
    main()
