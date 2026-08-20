from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import boto3
import duckdb
from botocore.client import Config

KEYWORDS = [
    "qualifiers", "relatedEventId", "relatedPlayerId", "CornerTaken", "Cross",
    "Longball", "Throughball", "ThrowIn", "KeeperThrow", "FreekickTaken",
    "IndirectFreekickTaken", "DirectFreekick", "SetPiece", "FromCorner",
    "ThrowinSetPiece", "RegularPlay", "FastBreak", "Penalty", "OwnGoal",
    "RightFoot", "LeftFoot", "Head", "OtherBodyPart", "BigChance",
    "BigChanceCreated", "IntentionalAssist", "KeyPass", "Blocked",
    "PassEndX", "PassEndY", "GoalMouthY", "BlockedX", "BlockedY",
]

FOCUS_TYPES = [
    "accurate_pass", "unsuccessful_pass", "accurate_cross", "inaccurate_cross",
    "accurate_corner", "inaccurate_corner", "accurate_long_ball", "inaccurate_long_ball",
    "accurate_throw", "inaccurate_throw", "free_kick", "shot", "goal", "touch",
    "red_card", "yellow_card", "progressive_pass", "successful_final_third_pass",
]


def _client():
    account = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def _parse_metadata(raw):
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        val = json.loads(str(raw))
        return val if isinstance(val, dict) else None
    except Exception:
        return None


def _walk_keys(value, prefix=""):
    out = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            out.append(path)
            out.extend(_walk_keys(child, path))
    elif isinstance(value, list):
        for child in value[:20]:
            out.extend(_walk_keys(child, prefix + "[]"))
    return out


def inspect(db_path: str) -> dict:
    con = duckdb.connect(db_path, read_only=True)
    try:
        total = con.execute("SELECT COUNT(*) FROM match_events").fetchone()[0]
        ws_total = con.execute("SELECT COUNT(*) FROM match_events WHERE lower(source)='whoscored'").fetchone()[0]
        patterns = {}
        for kw in KEYWORDS:
            patterns[kw] = int(con.execute(
                "SELECT COUNT(*) FROM match_events WHERE lower(source)='whoscored' AND metadata_json IS NOT NULL AND CAST(metadata_json AS VARCHAR) ILIKE ?",
                [f"%{kw}%"],
            ).fetchone()[0])

        samples = defaultdict(list)
        key_counts = Counter()
        type_counts = Counter()
        qualifier_values = Counter()
        rows = con.execute(
            """SELECT event_type, metadata_json FROM match_events
               WHERE lower(source)='whoscored' AND metadata_json IS NOT NULL
               AND event_type IN (SELECT * FROM UNNEST(?))
               ORDER BY match_id, time_seconds, event_id""",
            [FOCUS_TYPES],
        ).fetchall()
        seen_per_type = Counter()
        for event_type, raw in rows:
            et = str(event_type)
            if seen_per_type[et] >= 50:
                continue
            meta = _parse_metadata(raw)
            if not meta:
                continue
            seen_per_type[et] += 1
            type_counts[et] += 1
            for k in _walk_keys(meta):
                key_counts[k] += 1
            q = meta.get("qualifiers")
            if isinstance(q, list):
                for item in q:
                    if not isinstance(item, dict):
                        continue
                    qt = item.get("type")
                    if isinstance(qt, dict):
                        name = qt.get("displayName") or qt.get("value") or qt.get("id")
                    else:
                        name = qt
                    if name is not None:
                        qualifier_values[str(name)] += 1
            if len(samples[et]) < 3:
                samples[et].append(meta)

        return {
            "match_events_rows": int(total),
            "whoscored_rows": int(ws_total),
            "keyword_presence_counts": patterns,
            "sampled_event_types": dict(type_counts),
            "top_metadata_paths": key_counts.most_common(100),
            "top_qualifier_values": qualifier_values.most_common(100),
            "samples": dict(samples),
        }
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default="football/staging/2025-26-whoscored-cards.duckdb")
    ap.add_argument("--report", default="/tmp/r2-metadata-forensics.json")
    args = ap.parse_args()
    bucket = os.environ["R2_BUCKET"]
    client = _client()
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp:
        path = tmp.name
    try:
        client.download_file(bucket, args.key, path)
        result = {"r2_key": args.key, "inspection": inspect(path)}
        Path(args.report).write_text(json.dumps(result, indent=2, default=str))
        print(json.dumps({
            "r2_key": args.key,
            "match_events_rows": result["inspection"]["match_events_rows"],
            "whoscored_rows": result["inspection"]["whoscored_rows"],
            "keyword_presence_counts": result["inspection"]["keyword_presence_counts"],
            "top_qualifier_values": result["inspection"]["top_qualifier_values"][:30],
        }, indent=2))
        print(f"wrote_report={args.report}")
    finally:
        try: os.unlink(path)
        except OSError: pass


if __name__ == "__main__":
    main()
