from __future__ import annotations

import gzip
import hashlib
import json
import os
import random
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import pandas as pd
import soccerdata as sd

LEAGUE = "ENG-Premier League"
SEASON = "2025"
EXPECTED_MATCHES = 380
PREFIX = "football/raw/whoscored/2025-26-v3"
LOCAL = Path("raw-season-2025-26")
CACHE_ROOT = Path.home() / "soccerdata" / "data" / "WhoScored"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_default(value: Any):
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def json_bytes(obj: Any, *, gzip_it: bool = False) -> bytes:
    raw = json.dumps(obj, ensure_ascii=False, indent=2, default=json_default).encode("utf-8")
    return gzip.compress(raw, compresslevel=6) if gzip_it else raw


def df_json_gz(df: pd.DataFrame) -> bytes:
    records = json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))
    return json_bytes(records, gzip_it=True)


def df_csv_gz(df: pd.DataFrame) -> bytes:
    return gzip.compress(df.to_csv(index=False).encode("utf-8"), compresslevel=6)


def s3_client():
    endpoint = f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def exists(s3, bucket: str, key: str) -> dict | None:
    try:
        return s3.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if str(code) in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def put_immutable(s3, bucket: str, key: str, data: bytes, content_type: str, *, content_encoding: str | None = None):
    digest = sha256_bytes(data)
    prior = exists(s3, bucket, key)
    if prior is not None:
        old = (prior.get("Metadata") or {}).get("sha256")
        if old == digest:
            print(f"  exists/verified {key}")
            return {"key": key, "sha256": digest, "bytes": len(data), "status": "already-present"}
        raise RuntimeError(f"Immutable object already exists with different checksum: {key}")

    kwargs = {
        "Bucket": bucket,
        "Key": key,
        "Body": data,
        "ContentType": content_type,
        "Metadata": {"sha256": digest},
    }
    if content_encoding:
        kwargs["ContentEncoding"] = content_encoding
    s3.put_object(**kwargs)
    print(f"  uploaded {key} ({len(data):,} bytes)")
    return {"key": key, "sha256": digest, "bytes": len(data), "status": "uploaded"}


def resolve_match_ids(schedule: pd.DataFrame) -> list[int]:
    flat = schedule.reset_index()
    candidates = [c for c in flat.columns if str(c).lower() in {"game_id", "match_id", "id"}]
    for col in candidates:
        nums = pd.to_numeric(flat[col], errors="coerce").dropna().astype(int)
        ids = sorted(set(nums.tolist()))
        ids = [x for x in ids if x > 100000]
        if len(ids) >= EXPECTED_MATCHES:
            return ids
    # Fallback: inspect every column for WhoScored-like seven-digit IDs.
    for col in flat.columns:
        nums = pd.to_numeric(flat[col], errors="coerce").dropna().astype(int)
        ids = sorted(set(x for x in nums.tolist() if 1_000_000 <= x <= 9_999_999))
        if len(ids) >= EXPECTED_MATCHES:
            return ids
    raise RuntimeError(f"Could not identify match IDs from schedule columns: {list(flat.columns)}")


def qualifier_count(df: pd.DataFrame) -> tuple[int, int]:
    if "qualifiers" not in df.columns:
        return 0, 0
    events_with = 0
    total = 0
    for value in df["qualifiers"].tolist():
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        if isinstance(value, (list, tuple)):
            if len(value):
                events_with += 1
                total += len(value)
        else:
            events_with += 1
            try:
                parsed = json.loads(value) if isinstance(value, str) else value
                total += len(parsed) if isinstance(parsed, (list, tuple)) else 1
            except Exception:
                total += 1
    return events_with, total


def cache_files_for_match(mid: int) -> list[Path]:
    if not CACHE_ROOT.exists():
        return []
    # SoccerData normally includes the game ID in match cache filenames.
    found = [p for p in CACHE_ROOT.rglob(f"*{mid}*") if p.is_file()]
    return sorted(found)


def acquire_match(ws, s3, bucket: str, mid: int) -> dict:
    base = f"{PREFIX}/matches/{mid}"
    marker_key = f"{base}/complete.json"
    if exists(s3, bucket, marker_key):
        print(f"[{mid}] COMPLETE marker exists; skipping")
        return {"match_id": mid, "status": "skipped-complete"}

    print(f"[{mid}] scraping standard event frame")
    standard = ws.read_events(match_id=mid).reset_index()
    print(f"[{mid}] standard rows={len(standard):,}")

    print(f"[{mid}] retrieving raw event frame")
    raw = ws.read_events(match_id=mid, output_fmt="raw")
    if isinstance(raw, pd.DataFrame):
        raw_df = raw.reset_index()
        raw_obj: Any = json.loads(raw_df.to_json(orient="records", date_format="iso", force_ascii=False))
        raw_rows = len(raw_df)
        raw_columns = [str(c) for c in raw_df.columns]
    else:
        raw_df = None
        raw_obj = raw
        raw_rows = len(raw) if hasattr(raw, "__len__") else None
        raw_columns = None

    events_with_qualifiers, qualifier_instances = qualifier_count(standard)
    outputs: list[dict] = []
    outputs.append(put_immutable(s3, bucket, f"{base}/events.json.gz", df_json_gz(standard), "application/json", content_encoding="gzip"))
    outputs.append(put_immutable(s3, bucket, f"{base}/events.csv.gz", df_csv_gz(standard), "text/csv", content_encoding="gzip"))
    outputs.append(put_immutable(s3, bucket, f"{base}/raw.json.gz", json_bytes(raw_obj, gzip_it=True), "application/json", content_encoding="gzip"))
    if raw_df is not None:
        outputs.append(put_immutable(s3, bucket, f"{base}/raw.csv.gz", df_csv_gz(raw_df), "text/csv", content_encoding="gzip"))

    # Preserve SoccerData's own downloaded/cache representation too, whenever the match-id file is discoverable.
    cache_outputs = []
    for path in cache_files_for_match(mid):
        rel = path.relative_to(CACHE_ROOT)
        data = path.read_bytes()
        cache_outputs.append(put_immutable(s3, bucket, f"{base}/soccerdata_cache/{rel.as_posix()}", data, "application/octet-stream"))

    summary = {
        "schema": "lufcdata.whoscored.raw-match.v1",
        "match_id": mid,
        "league": LEAGUE,
        "season": "2025/26",
        "acquired_at_utc": utcnow(),
        "soccerdata_version": getattr(sd, "__version__", "unknown"),
        "python_version": sys.version,
        "standard_rows": int(len(standard)),
        "standard_columns": [str(c) for c in standard.columns],
        "raw_rows": raw_rows,
        "raw_columns": raw_columns,
        "events_with_qualifiers": events_with_qualifiers,
        "qualifier_instances": qualifier_instances,
        "event_type_counts": {str(k): int(v) for k, v in standard["type"].value_counts(dropna=False).items()} if "type" in standard.columns else {},
        "files": outputs + cache_outputs,
    }
    summary_data = json_bytes(summary)
    outputs.append(put_immutable(s3, bucket, f"{base}/summary.json", summary_data, "application/json"))

    # Completion marker is deliberately LAST. Its existence means all expected representations above are durable in R2.
    complete = {
        "schema": "lufcdata.whoscored.raw-match-complete.v1",
        "match_id": mid,
        "completed_at_utc": utcnow(),
        "standard_rows": int(len(standard)),
        "raw_rows": raw_rows,
        "events_with_qualifiers": events_with_qualifiers,
        "qualifier_instances": qualifier_instances,
        "required_objects": [x["key"] for x in outputs],
    }
    put_immutable(s3, bucket, marker_key, json_bytes(complete), "application/json")
    return {"match_id": mid, "status": "completed", "rows": int(len(standard)), "qualifiers": qualifier_instances}


def main():
    LOCAL.mkdir(exist_ok=True)
    bucket = os.environ["R2_BUCKET"]
    s3 = s3_client()

    print("Initializing visible-browser WhoScored scraper")
    ws = sd.WhoScored(leagues=LEAGUE, seasons=SEASON, headless=False)

    print("Retrieving/caching complete 2025/26 Premier League schedule")
    schedule = ws.read_schedule()
    flat_schedule = schedule.reset_index()
    ids = resolve_match_ids(schedule)
    if len(ids) != EXPECTED_MATCHES:
        raise RuntimeError(f"Safety stop: expected exactly {EXPECTED_MATCHES} matches, found {len(ids)}")
    print(f"Season inventory verified: {len(ids)} matches; range {min(ids)}..{max(ids)}")

    run_id = os.getenv("GITHUB_RUN_ID", f"local-{int(time.time())}")
    schedule_csv = flat_schedule.to_csv(index=False).encode("utf-8")
    schedule_json = json_bytes(json.loads(flat_schedule.to_json(orient="records", date_format="iso", force_ascii=False)))
    put_immutable(s3, bucket, f"{PREFIX}/inventory/schedule.csv", schedule_csv, "text/csv")
    put_immutable(s3, bucket, f"{PREFIX}/inventory/schedule.json", schedule_json, "application/json")
    put_immutable(s3, bucket, f"{PREFIX}/inventory/match_ids.json", json_bytes(ids), "application/json")

    results = []
    failures = []
    consecutive_failures = 0
    for i, mid in enumerate(ids, 1):
        print(f"\n=== {i}/{len(ids)} match {mid} ===")
        try:
            result = acquire_match(ws, s3, bucket, mid)
            results.append(result)
            consecutive_failures = 0
        except Exception as exc:
            failure = {"match_id": mid, "error": repr(exc), "at_utc": utcnow()}
            failures.append(failure)
            results.append({"match_id": mid, "status": "failed", "error": repr(exc)})
            consecutive_failures += 1
            print(f"ERROR match {mid}: {exc!r}")
            if consecutive_failures >= 5:
                print("Stopping after 5 consecutive failures; rerun will resume from durable completion markers.")
                break
        time.sleep(random.uniform(1.0, 2.5))

    completed_markers = 0
    for mid in ids:
        if exists(s3, bucket, f"{PREFIX}/matches/{mid}/complete.json"):
            completed_markers += 1

    run_summary = {
        "schema": "lufcdata.whoscored.raw-season-run.v1",
        "run_id": run_id,
        "finished_at_utc": utcnow(),
        "expected_matches": EXPECTED_MATCHES,
        "durable_completed_matches": completed_markers,
        "this_run_results": results,
        "this_run_failures": failures,
        "prefix": PREFIX,
    }
    local_summary = LOCAL / "run_summary.json"
    local_summary.write_text(json.dumps(run_summary, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")
    put_immutable(s3, bucket, f"{PREFIX}/runs/{run_id}/summary.json", json_bytes(run_summary), "application/json")

    if completed_markers == EXPECTED_MATCHES:
        season_complete = {
            "schema": "lufcdata.whoscored.raw-season-complete.v1",
            "league": LEAGUE,
            "season": "2025/26",
            "matches": EXPECTED_MATCHES,
            "completed_at_utc": utcnow(),
            "prefix": PREFIX,
            "meaning": "All 380 match completion markers verified. Raw and standard SoccerData event representations preserved per match.",
        }
        put_immutable(s3, bucket, f"{PREFIX}/SEASON_COMPLETE.json", json_bytes(season_complete), "application/json")
        print("FULL SEASON COMPLETE: 380/380 durable match markers verified")
    else:
        print(f"PARTIAL/RESUMABLE: {completed_markers}/{EXPECTED_MATCHES} durable match markers currently verified")
        if failures:
            print(f"Failures this run: {len(failures)}")
        # Deliberately return success for partial progress unless nothing was completed; rerun is the normal recovery path.


if __name__ == "__main__":
    main()
