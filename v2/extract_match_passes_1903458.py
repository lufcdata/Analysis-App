from __future__ import annotations

import json
import os
from pathlib import Path

import boto3
import duckdb

R2_KEY = "football/staging/2025-26-whoscored-cards.duckdb"
MATCH_IDS = ["1903458", "ws-match-1903458"]


def main() -> None:
    out = Path("abc-1903458")
    out.mkdir(parents=True, exist_ok=True)
    db_path = out / "source_match_passes.duckdb"

    endpoint = f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    s3.download_file(os.environ["R2_BUCKET"], R2_KEY, str(db_path))

    con = duckdb.connect(str(db_path), read_only=True)
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    if "match_passes" not in tables:
        raise SystemExit("match_passes table missing")

    cols = [r[1] for r in con.execute('PRAGMA table_info("match_passes")').fetchall()]
    if "match_id" not in cols:
        raise SystemExit(f"match_passes has no match_id column: {cols}")

    qs = ",".join(["?"] * len(MATCH_IDS))
    df = con.execute(
        f'SELECT * FROM "match_passes" WHERE CAST(match_id AS VARCHAR) IN ({qs})',
        MATCH_IDS,
    ).df()

    df.to_csv(out / "C_match_passes.csv", index=False)
    df.to_json(out / "C_match_passes.json", orient="records", indent=2, force_ascii=False)
    summary = {
        "rows": int(len(df)),
        "columns": [str(c) for c in df.columns],
        "non_null": {str(c): int(df[c].notna().sum()) for c in df.columns},
    }
    (out / "C_match_passes_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, default=str))

    con.close()
    db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
