from __future__ import annotations

import csv
import json
import os
from collections import Counter
from pathlib import Path

import boto3
import duckdb

SEASON_ID = "eng-premier-league-2025-26"
R2_KEY = "football/staging/2025-26-whoscored-cards.duckdb"

# Stored Opta Analyst 2025/26 Arsenal team snapshot (source last updated 2026-07-23).
# Only direct, like-for-like counting metrics are used for verdicts here.
OPTA = {
    "matches": 38,
    "goals": 71,
    "shots": 553,
    "shots_on_target": 187,
    "penalty_box_touches": 1255,
    "passes": 17897,
    "successful_passes": 15076,
    "final_third_passes": 5787,
    "successful_final_third_passes": 4295,
    "open_play_crosses": 437,
    "successful_open_play_crosses": 96,
    "through_balls": 127,
    "tackles": 602,
    "interceptions": 269,
    "recoveries": 1711,
    "blocks": 130,
    "clearances": 903,
}


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def columns(con, table: str) -> list[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info({q(table)})").fetchall()]


def resolve_arsenal_team_id(con, tables: list[str]) -> str:
    if "teams" in tables:
        cols = columns(con, "teams")
        text_cols = [c for c in cols if any(k in c.lower() for k in ["name", "team", "club", "short"])]
        id_cols = [c for c in cols if c in ["team_id", "id"] or c.endswith("team_id")]
        for tc in text_cols:
            try:
                rows = con.execute(
                    f"SELECT * FROM teams WHERE lower(CAST({q(tc)} AS VARCHAR)) LIKE '%arsenal%'"
                ).fetchall()
            except Exception:
                continue
            if rows:
                desc = [d[0] for d in con.description]
                for row in rows:
                    rec = dict(zip(desc, row))
                    for ic in id_cols:
                        if rec.get(ic) is not None:
                            return str(rec[ic])
    # WhoScored Arsenal's provider team id is 13 in this dataset convention.
    candidate = "ws-team-13"
    if "matches" in tables:
        n = con.execute(
            "SELECT COUNT(*) FROM matches WHERE season_id=? AND (CAST(home_team_id AS VARCHAR)=? OR CAST(away_team_id AS VARCHAR)=?)",
            [SEASON_ID, candidate, candidate],
        ).fetchone()[0]
        if n:
            return candidate
    raise SystemExit("Could not resolve Arsenal team_id")


def classify(opta: float, ours: float) -> tuple[float, str]:
    if opta == 0:
        return (0.0 if ours == 0 else 999.0, "EXACT" if ours == 0 else "FAILED")
    diff = abs(ours - opta) / abs(opta) * 100.0
    if diff <= 1:
        band = "EXACT_NEAR"
    elif diff <= 3:
        band = "CLOSE"
    elif diff <= 10:
        band = "QUESTIONABLE"
    else:
        band = "FAILED"
    return diff, band


def main():
    out = Path("arsenal-audit")
    out.mkdir(exist_ok=True)

    endpoint = f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
    s3 = boto3.client(
        "s3", endpoint_url=endpoint,
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    db = out / "source.duckdb"
    s3.download_file(os.environ["R2_BUCKET"], R2_KEY, str(db))
    con = duckdb.connect(str(db), read_only=True)
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    team_id = resolve_arsenal_team_id(con, tables)

    match_ids = [r[0] for r in con.execute(
        "SELECT match_id FROM matches WHERE season_id=? AND (CAST(home_team_id AS VARCHAR)=? OR CAST(away_team_id AS VARCHAR)=?) ORDER BY match_date",
        [SEASON_ID, team_id, team_id],
    ).fetchall()]
    if not match_ids:
        raise SystemExit(f"No Arsenal matches found for {team_id}")

    qs = ",".join(["?"] * len(match_ids))
    ev = con.execute(
        f"SELECT event_type, source, source_event_id, match_id, minute, second, x, y, end_x, end_y, outcome, metadata_json "
        f"FROM match_events WHERE CAST(team_id AS VARCHAR)=? AND match_id IN ({qs})",
        [team_id] + match_ids,
    ).df()
    ev.to_csv(out / "arsenal_match_events.csv", index=False)

    counts = Counter(ev["event_type"].dropna().astype(str).tolist())
    def c(*names):
        return sum(counts.get(n, 0) for n in names)

    # Core event-derived measures. We deliberately reconstruct from events rather than trust zero-filled aggregates.
    ours = {
        "matches": len(match_ids),
        "goals": c("goal"),
        "shots": c("shot"),
        "shots_on_target": c("shot_on_target"),
        "penalty_box_touches": c("penalty_box_touch"),
        "passes": c("accurate_pass", "unsuccessful_pass"),
        "successful_passes": c("accurate_pass"),
        "successful_final_third_passes": c("successful_final_third_pass"),
        "open_play_crosses": c("accurate_cross", "inaccurate_cross"),
        "successful_open_play_crosses": c("accurate_cross"),
        "through_balls": sum(v for k, v in counts.items() if "through_ball" in k.lower()),
        "tackles": c("tackle_won", "tackle_lost"),
        "interceptions": c("interception"),
        "recoveries": c("ball_recovery"),
        "blocks": c("block"),
        "clearances": c("clearance"),
    }

    # Reconstruct total final-third passes geometrically from canonical pass events.
    pass_mask = ev["event_type"].isin(["accurate_pass", "unsuccessful_pass"])
    pass_ev = ev.loc[pass_mask].copy()
    # WhoScored coordinates are normalized so the acting team attacks toward x=100.
    ours["final_third_passes"] = int((pass_ev["end_x"].notna() & (pass_ev["end_x"] >= (100.0 * 2.0 / 3.0))).sum())

    # Diagnostic metrics not present in the Opta team table but important to this project.
    diagnostics = {
        "ball_carries": c("Carry"),
        "progressive_passes": c("progressive_pass"),
        "forward_passes": c("forward_pass"),
        "backward_passes": c("backward_pass"),
        "final_third_entries": c("final_third_entry"),
        "ground_duel_won": c("ground_duel_won", "ground_duels_won"),
        "ground_duel_lost": c("ground_duel_lost"),
        "aerial_won": c("aerial_won"),
        "aerial_lost": c("aerial_lost"),
        "key_passes": c("key_pass"),
        "big_chances": c("big_chance"),
        "big_chances_created": c("big_chance_created"),
        "assists": c("assist"),
    }

    # Aggregate existing team_match_stats as a storage-quality diagnostic.
    agg = {}
    if "team_match_stats" in tables:
        tcols = columns(con, "team_match_stats")
        numeric_targets = [
            "goals", "shots_on_target", "penalty_box_touches", "successful_final_third_pass",
            "accurate_cross", "inaccurate_cross", "tackle_won", "tackle_lost", "interception",
            "block", "clearance", "ball_recovery", "ball_carries", "progressive_carries",
            "carry_distance_m", "carries_into_final_third", "final_third_passes",
            "unsuccessful_final_third_passes", "progressive_passes", "forward_passes",
            "successful_forward_passes", "backward_passes", "successful_backward_passes",
            "final_third_entries",
        ]
        for col in numeric_targets:
            if col in tcols:
                val = con.execute(
                    f"SELECT COALESCE(SUM({q(col)}),0) FROM team_match_stats WHERE CAST(team_id AS VARCHAR)=? AND match_id IN ({qs})",
                    [team_id] + match_ids,
                ).fetchone()[0]
                agg[col] = float(val) if isinstance(val, float) else int(val)

    rows = []
    for metric, opta in OPTA.items():
        ours_val = ours.get(metric)
        if ours_val is None:
            rows.append({"metric": metric, "opta": opta, "ours": None, "difference": None, "difference_pct": None, "verdict": "NOT_COMPARABLE"})
            continue
        pct, band = classify(float(opta), float(ours_val))
        rows.append({
            "metric": metric,
            "opta": opta,
            "ours": ours_val,
            "difference": ours_val - opta,
            "difference_pct": round(pct, 3),
            "verdict": band,
        })

    with (out / "comparison.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["metric", "opta", "ours", "difference", "difference_pct", "verdict"])
        w.writeheader(); w.writerows(rows)

    verdict_counts = Counter(r["verdict"] for r in rows)
    report = {
        "team": "Arsenal",
        "team_id": team_id,
        "season": "2025/26",
        "r2_key": R2_KEY,
        "match_count": len(match_ids),
        "event_rows": int(len(ev)),
        "opta_source": "Stored The Analyst / Opta 2025/26 snapshot, last updated 2026-07-23",
        "comparison": rows,
        "verdict_counts": dict(verdict_counts),
        "ours_event_derived": ours,
        "our_diagnostics": diagnostics,
        "stored_team_match_stats_sums": agg,
        "event_type_counts": dict(counts.most_common()),
        "notes": [
            "Comparison uses event-derived values wherever possible to distinguish definition quality from broken aggregate columns.",
            "Final-third pass total is reconstructed from canonical pass end_x >= 66.6667; successful final-third passes use the stored derived category.",
            "Open-play crosses are compared against our accurate_cross + inaccurate_cross categories; if our categories include set-play crosses this will surface as a definition mismatch.",
            "Carries/progressive passes/forward/backward passes are exported as diagnostics because the stored Opta team table does not expose like-for-like totals for all of them.",
        ],
    }
    (out / "audit.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (out / "event_type_counts.json").write_text(json.dumps(dict(counts.most_common()), indent=2), encoding="utf-8")
    con.close(); db.unlink(missing_ok=True)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
