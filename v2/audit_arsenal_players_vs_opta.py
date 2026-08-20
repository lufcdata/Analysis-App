from __future__ import annotations

import csv
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import boto3
import duckdb

SEASON_ID = "eng-premier-league-2025-26"
R2_KEY = "football/staging/2025-26-whoscored-cards.duckdb"
TEAM_ID = "ws-team-13"

# Stored The Analyst / Opta Arsenal 2025/26 player snapshot.
# Source last updated 2026-07-23. These are the counting metrics most useful
# for testing our interpretation layer. Goalkeepers / zero-minute rows are
# excluded from the outfield metric verdicts.
# Format per player:
# passes, successful_passes, final_third_passes, successful_final_third_passes,
# open_play_crosses, successful_open_play_crosses, through_balls,
# carries, carry_distance, progressive_carries,
# tackles, interceptions, recoveries, blocks, clearances,
# ground_duels, ground_duels_won, aerial_duels, aerial_duels_won
OPTA = {
    "Leandro Trossard": [757,583,410,281,54,12,13,298,3487.810,145,27,9,80,3,14,190,90,19,6],
    "Christian Nørgaard": [61,51,17,9,1,0,0,8,54.388,4,3,0,4,1,8,11,3,5,2],
    "Martin Ødegaard": [828,701,398,305,12,3,20,325,3771.854,142,19,7,70,0,6,89,37,8,3],
    "Mikel Merino": [370,281,150,97,4,0,12,66,653.059,28,26,10,57,2,19,101,51,71,28],
    "Ben White": [354,289,148,116,16,3,3,54,605.785,31,15,9,28,4,25,40,24,27,12],
    "Bukayo Saka": [773,593,453,341,67,21,3,400,4763.208,207,41,16,117,1,11,275,145,52,22],
    "Viktor Gyökeres": [319,199,198,119,8,3,4,118,1373.592,63,7,1,55,3,19,137,44,97,30],
    "Gabriel Magalhães": [1733,1528,299,205,5,1,4,315,2991.340,192,38,23,64,33,182,103,72,159,99],
    "Eberechi Eze": [666,565,291,228,7,2,18,238,2536.834,100,19,11,79,1,10,153,88,35,10],
    "Noni Madueke": [411,313,238,171,47,7,2,201,2534.568,119,21,5,35,1,8,149,65,22,10],
    "Gabriel Martinelli": [261,189,133,86,33,7,2,135,1733.417,83,12,1,52,1,10,104,47,26,8],
    "Jurriën Timber": [1085,925,434,344,46,6,9,242,2609.645,150,66,24,97,6,53,197,107,60,40],
    "Piero Hincapié": [837,744,205,169,33,4,2,193,2002.534,106,48,26,63,9,88,109,68,63,32],
    "William Saliba": [2104,1954,311,258,9,4,7,393,3806.157,225,35,17,113,7,133,99,58,132,73],
    "Declan Rice": [2136,1865,671,534,47,15,12,624,7460.810,328,70,37,180,12,78,167,95,74,50],
    "Kai Havertz": [166,123,89,63,6,0,1,44,512.914,25,8,1,14,0,8,42,19,42,17],
    "Gabriel Jesus": [108,83,52,40,0,0,1,36,405.512,23,4,3,19,0,5,42,13,29,10],
    "Riccardo Calafiori": [756,647,221,194,21,3,1,187,2066.866,100,32,15,73,5,50,107,56,77,48],
    "Myles Lewis-Skelly": [382,350,91,80,0,0,0,80,827.586,47,8,5,30,1,11,55,32,17,6],
    "Ethan Nwaneri": [87,79,30,26,1,0,1,38,518.012,20,1,0,10,0,1,15,4,4,1],
    "Cristhian Mosquera": [633,578,120,106,3,1,1,151,1579.871,96,32,8,34,6,47,72,40,48,20],
    "Max Dowman": [52,46,30,26,5,1,1,37,513.524,23,2,1,13,0,0,38,15,2,0],
}

FIELDS = [
    "passes","successful_passes","final_third_passes","successful_final_third_passes",
    "open_play_crosses","successful_open_play_crosses","through_balls",
    "carries","carry_distance","progressive_carries",
    "tackles","interceptions","recoveries","blocks","clearances",
    "ground_duels","ground_duels_won","aerial_duels","aerial_duels_won",
]


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def cols(con, table: str) -> list[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info({q(table)})").fetchall()]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    s = s.lower().replace("ø", "o")
    return re.sub(r"[^a-z0-9]+", "", s)


def verdict(opta: float, ours: float):
    if opta == 0:
        if ours == 0:
            return 0.0, "EXACT"
        return None, "FAILED_ZERO_BASE"
    pct = abs(ours - opta) / abs(opta) * 100.0
    if ours == opta:
        band = "EXACT"
    elif pct <= 1:
        band = "NEAR_EXACT"
    elif pct <= 3:
        band = "CLOSE"
    elif pct <= 10:
        band = "QUESTIONABLE"
    else:
        band = "FAILED"
    return pct, band


def player_name_map(con, player_ids: list[str]) -> dict[str, str]:
    if "players" not in [r[0] for r in con.execute("SHOW TABLES").fetchall()]:
        return {}
    pc = cols(con, "players")
    id_col = next((c for c in ["player_id", "id"] if c in pc), None)
    name_col = next((c for c in ["player_name", "name", "display_name", "full_name"] if c in pc), None)
    if not id_col or not name_col:
        return {}
    qs = ",".join(["?"] * len(player_ids))
    rows = con.execute(
        f"SELECT CAST({q(id_col)} AS VARCHAR), CAST({q(name_col)} AS VARCHAR) FROM players WHERE CAST({q(id_col)} AS VARCHAR) IN ({qs})",
        player_ids,
    ).fetchall()
    return {str(a): str(b) for a, b in rows if a is not None and b is not None}


def parse_meta(v):
    if not isinstance(v, str) or not v:
        return {}
    try:
        return json.loads(v)
    except Exception:
        return {}


def main():
    out = Path("arsenal-player-audit")
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

    match_ids = [r[0] for r in con.execute(
        "SELECT match_id FROM matches WHERE season_id=? AND (CAST(home_team_id AS VARCHAR)=? OR CAST(away_team_id AS VARCHAR)=?) ORDER BY match_date",
        [SEASON_ID, TEAM_ID, TEAM_ID],
    ).fetchall()]
    if len(match_ids) != 38:
        raise SystemExit(f"Expected 38 Arsenal matches, found {len(match_ids)}")

    qs = ",".join(["?"] * len(match_ids))
    ev = con.execute(
        f"SELECT player_id,event_type,match_id,x,y,end_x,end_y,metadata_json FROM match_events "
        f"WHERE CAST(team_id AS VARCHAR)=? AND match_id IN ({qs}) AND player_id IS NOT NULL",
        [TEAM_ID] + match_ids,
    ).df()
    ids = sorted(set(ev["player_id"].dropna().astype(str)))
    names = player_name_map(con, ids)

    # If the players table naming schema changes, export IDs visibly rather than guessing.
    ev["player_name"] = ev["player_id"].astype(str).map(names)
    ev.to_csv(out / "arsenal_player_events.csv", index=False)
    (out / "player_id_name_map.json").write_text(json.dumps(names, indent=2, ensure_ascii=False), encoding="utf-8")

    opta_norm = {norm(k): k for k in OPTA}
    aliases = {
        "gabriel": "Gabriel Magalhães",
        "gabrielmagalhaes": "Gabriel Magalhães",
        "martinodegaard": "Martin Ødegaard",
        "viktorgyokeres": "Viktor Gyökeres",
        "jurrientimber": "Jurriën Timber",
        "piero hincapie": "Piero Hincapié",
    }
    aliases = {norm(k): v for k, v in aliases.items()}

    matched_ids = {}
    for pid, pname in names.items():
        n = norm(pname)
        target = opta_norm.get(n) or aliases.get(n)
        if target:
            matched_ids[pid] = target

    # Detect unmatched Opta benchmark players explicitly.
    matched_targets = set(matched_ids.values())
    unmatched_opta = sorted(set(OPTA) - matched_targets)

    by_player = defaultdict(Counter)
    carry_distance = defaultdict(float)
    progressive_carries = defaultdict(int)
    final_third = defaultdict(int)

    for row in ev.itertuples(index=False):
        pid = str(row.player_id)
        if pid not in matched_ids:
            continue
        p = matched_ids[pid]
        et = str(row.event_type)
        by_player[p][et] += 1
        if et in ("accurate_pass", "unsuccessful_pass") and row.end_x is not None:
            try:
                if float(row.end_x) >= 100.0 * 2.0 / 3.0:
                    final_third[p] += 1
            except Exception:
                pass
        if et == "Carry":
            meta = parse_meta(row.metadata_json)
            try:
                carry_distance[p] += float(meta.get("carry_distance_m") or 0.0)
            except Exception:
                pass
            if meta.get("is_progressive_carry") is True:
                progressive_carries[p] += 1

    def derive(p: str) -> dict[str, float]:
        c = by_player[p]
        def n(*keys): return sum(c.get(k, 0) for k in keys)
        return {
            "passes": n("accurate_pass", "unsuccessful_pass"),
            "successful_passes": n("accurate_pass"),
            "final_third_passes": final_third[p],
            "successful_final_third_passes": n("successful_final_third_pass"),
            "open_play_crosses": n("accurate_cross", "inaccurate_cross"),
            "successful_open_play_crosses": n("accurate_cross"),
            "through_balls": sum(v for k, v in c.items() if "through_ball" in k.lower()),
            "carries": n("Carry"),
            "carry_distance": round(carry_distance[p], 3),
            "progressive_carries": progressive_carries[p],
            "tackles": n("tackle_won", "tackle_lost"),
            "interceptions": n("interception"),
            "recoveries": n("ball_recovery"),
            "blocks": n("block"),
            "clearances": n("clearance"),
            "ground_duels": n("ground_duel_won", "ground_duel_lost", "ground_duels_won", "ground_duels_lost"),
            "ground_duels_won": n("ground_duel_won", "ground_duels_won"),
            "aerial_duels": n("aerial_won", "aerial_lost"),
            "aerial_duels_won": n("aerial_won"),
        }

    comparison = []
    metric_bands = defaultdict(Counter)
    metric_abs_pct = defaultdict(list)
    metric_totals = defaultdict(lambda: [0.0, 0.0])

    for player in sorted(matched_targets):
        ours = derive(player)
        opta = dict(zip(FIELDS, OPTA[player]))
        for metric in FIELDS:
            ov = float(opta[metric]); rv = float(ours[metric])
            pct, band = verdict(ov, rv)
            comparison.append({
                "player": player, "metric": metric, "opta": ov, "ours": rv,
                "difference": rv - ov,
                "difference_pct": "" if pct is None else round(pct, 3),
                "verdict": band,
            })
            metric_bands[metric][band] += 1
            if pct is not None:
                metric_abs_pct[metric].append(pct)
            metric_totals[metric][0] += ov
            metric_totals[metric][1] += rv

    with (out / "player_metric_comparison.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["player","metric","opta","ours","difference","difference_pct","verdict"])
        w.writeheader(); w.writerows(comparison)

    metric_summary = []
    for metric in FIELDS:
        o, r = metric_totals[metric]
        total_pct, total_band = verdict(o, r)
        vals = sorted(metric_abs_pct.get(metric, []))
        med = vals[len(vals)//2] if vals else None
        metric_summary.append({
            "metric": metric,
            "players_compared": len(matched_targets),
            "opta_total": round(o, 3),
            "ours_total": round(r, 3),
            "total_difference_pct": "" if total_pct is None else round(total_pct, 3),
            "total_verdict": total_band,
            "median_player_abs_difference_pct": "" if med is None else round(med, 3),
            "exact": metric_bands[metric].get("EXACT", 0),
            "near_exact": metric_bands[metric].get("NEAR_EXACT", 0),
            "close": metric_bands[metric].get("CLOSE", 0),
            "questionable": metric_bands[metric].get("QUESTIONABLE", 0),
            "failed": metric_bands[metric].get("FAILED", 0) + metric_bands[metric].get("FAILED_ZERO_BASE", 0),
        })

    with (out / "metric_summary.csv").open("w", newline="", encoding="utf-8") as f:
        fields = list(metric_summary[0].keys())
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(metric_summary)

    report = {
        "team": "Arsenal",
        "season": "2025/26",
        "r2_key": R2_KEY,
        "matches": len(match_ids),
        "benchmark_players": len(OPTA),
        "matched_players": len(matched_targets),
        "matched_player_names": sorted(matched_targets),
        "unmatched_opta_players": unmatched_opta,
        "metric_summary": metric_summary,
        "notes": [
            "EXACT means numerically identical. NEAR_EXACT means non-identical but within 1%.",
            "The benchmark is the stored The Analyst / Opta 2025/26 player snapshot last updated 2026-07-23.",
            "R2 values are reconstructed from underlying match_events, not zero-filled aggregate columns.",
            "Cross benchmark is Opta open-play crosses; our cross categories may include set plays, which is intentionally exposed as a definition test.",
            "Carry distance and progressive-carry flags come from the stored derived Carry metadata and therefore directly test our custom carry interpretation.",
        ],
    }
    (out / "audit_summary.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    con.close(); db.unlink(missing_ok=True)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("\n=== METRIC SUMMARY ===")
    for r in metric_summary:
        print(r)


if __name__ == "__main__":
    main()
