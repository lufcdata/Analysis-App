"""Read-only evidence audit for using the 2025/26 staging DuckDB as a Metrics Bible source.

This module does NOT materialise canonical values and does NOT mutate R2. It only
classifies each Aug-18 registry metric by evidence available in the staging
schema. Candidate classifications are deliberately conservative and still need
regression proof before a bridge is enabled.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

import boto3
import duckdb
from botocore.client import Config

from .metric_registry import METRICS, MetricStatus, METRIC_SET_VERSION

SEASON_ID = "eng-premier-league-2025-26"

# Direct event-family evidence already persisted by the audited pitch-plot V2 ingest.
EVENT_EVIDENCE = {
    "touches": ["touch"],
    "final_third_touches": ["touch"],
    "progressive_passes": ["progressive_pass"],
    "successful_take_ons": ["take_on_won"],
    "unsuccessful_take_ons": ["take_on_lost"],
    "take_on_attempts_total_take_ons": ["take_on_won", "take_on_lost"],
    "tackles_won": ["tackle_won"],
    "tackles_lost": ["tackle_lost"],
    "interceptions": ["interception"],
    "ball_recoveries": ["ball_recovery"],
    "big_chances_created": ["big_chance_created"],
    "key_passes": ["key_pass"],
    "assists": ["assist"],
    "chances_created": ["key_pass"],
    "saves": ["keeper_save_total"],
    "successful_throw_ins": ["accurate_throw"],
    "unsuccessful_throw_ins": ["inaccurate_throw"],
    "throw_ins_total_throws": ["accurate_throw", "inaccurate_throw"],
    "aerial_duels_won": ["aerial_won"],
    "aerial_duels_lost": ["aerial_lost"],
    "ground_duels_won": ["ground_duel_won"],
    "ground_duels_lost": ["ground_duel_lost"],
    "duels_won": ["duel_won"],
    "duels_lost": ["duel_lost"],
    "penalty_box_touches": ["penalty_box_touch"],
    "forward_passes": ["forward_pass"],
    "backward_passes": ["backward_pass"],
    "successful_final_third_passes": ["successful_final_third_pass"],
    "clearances": ["clearance"],
    "headed_clearances": ["head_clearance"],
    "goals": ["goal"],
    "goals_free_kicks": ["direct_freekick_goal"],
    "goals_set_pieces": ["goal_set_piece"],
    "goals_right_foot": ["goal_right_foot"],
    "goals_left_foot": ["goal_left_foot"],
    "goals_head": ["goal_head"],
    "shots": ["shot"],
    "shots_on_target": ["shot_on_target"],
    "shots_off_target": ["shot_off_target"],
    "blocked_shots": ["blocked_shot"],
    "shots_direct_free_kick": ["shot_direct_freekick"],
    "shots_from_set_pieces": ["shot_set_piece"],
    "shots_right_foot": ["shot_right_foot"],
    "shots_left_foot": ["shot_left_foot"],
    "shots_head": ["shot_head"],
    "successful_corners": ["accurate_corner"],
    "unsuccessful_corners": ["inaccurate_corner"],
    "fouls_won": ["fouled"],
    "fouls_committed": ["foul"],
    "big_chances": ["big_chance"],
    "big_chances_missed": ["big_chance_missed"],
    "accurate_crosses": ["accurate_cross"],
    "accurate_long_passes": ["accurate_long_ball"],
}

# Existing audited match-stat columns. Presence is evidence only, never permission
# to bypass the Metrics Bible. Each candidate must be definition-regression tested.
STAT_COLUMN_EVIDENCE = {
    "successful_final_third_passes": "successful_final_third_pass",
    "progressive_passes": "progressive_passes",
    "forward_passes": "forward_passes",
    "backward_passes": "backward_passes",
    "ball_recoveries": "ball_recovery",
    "tackles_won": "tackle_won",
    "tackles_lost": "tackle_lost",
    "interceptions": "interception",
    "ground_duels_won": "ground_duel_won",
    "ground_duels_lost": "ground_duel_lost",
    "aerial_duels_won": "aerial_duel_won",
    "aerial_duels_lost": "aerial_duel_lost",
    "penalty_box_touches": "penalty_box_touches",
    "clearances": "clearance",
    "goals": "goals",
    "chances_created": "chances_created",
    "shots_on_target": "shots_on_target",
    "successful_take_ons": "successful_take_ons",
    "saves": "saves",
}

# These can potentially be reconstructed from normalized primitive columns/event
# families, but must pass canonical-vs-bridge regression before activation.
DERIVABLE = {
    "successful_passes": "successful pass events / pass outcome evidence",
    "unsuccessful_passes": "unsuccessful_pass event family",
    "total_passes": "successful + unsuccessful pass populations",
    "pass_accuracy_percent": "successful / total passes",
    "side_passes": "pass start/end x using the Bible 2.0 directional boundary",
    "successful_passes_into_penalty_box": "pass start/end coordinates + outcome",
    "final_third_touches": "touch x >= Bible final-third boundary",
    "shots_outside_box": "shot coordinates",
    "shots_6_yard_box": "shot coordinates",
    "shots_penalty_area": "shot coordinates",
    "goals_outside_box": "goal coordinates",
    "goals_6_yard_box": "goal coordinates",
    "goals_penalty_area": "goal coordinates",
    "save_percentage_percent": "saves / shots on-target faced",
    "goals_conceded": "opponent goal population while goalkeeper active",
    "clean_sheets": "goals conceded == 0 while goalkeeper active",
    "shots_on_target_faced": "opponent shot-on-target population while goalkeeper active",
    "possession": "touch/timeline event sequence; requires dedicated regression proof",
}


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


def download(key: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _client().download_file(os.environ["R2_BUCKET"], key, str(destination))


def columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall()}


def audit(path: Path, r2_key: str) -> dict:
    conn = duckdb.connect(str(path), read_only=True)
    try:
        event_counts = {
            str(event_type): int(rows)
            for event_type, rows in conn.execute(
                """SELECT event_type, COUNT(*) FROM match_events
                   WHERE source='whoscored' GROUP BY event_type"""
            ).fetchall()
        }
        pcols = columns(conn, "player_match_stats")
        tcols = columns(conn, "team_match_stats")
        matches = conn.execute(
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE whoscored_ingested) FROM matches WHERE season_id=?",
            [SEASON_ID],
        ).fetchone()

        rows = []
        status_counts = Counter()
        for spec in METRICS:
            if spec.status is MetricStatus.UNAVAILABLE:
                classification = "UNAVAILABLE_BY_REGISTRY"
                evidence = spec.reason
            else:
                required_events = EVENT_EVIDENCE.get(spec.key, [])
                present_events = {name: event_counts.get(name, 0) for name in required_events}
                if required_events and all(present_events.values()):
                    classification = "EVENT_EVIDENCE_CANDIDATE"
                    evidence = present_events
                elif spec.key in STAT_COLUMN_EVIDENCE and STAT_COLUMN_EVIDENCE[spec.key] in pcols:
                    classification = "STAT_COLUMN_TRACE_CANDIDATE"
                    evidence = {"player_match_stats": STAT_COLUMN_EVIDENCE[spec.key]}
                elif spec.key in DERIVABLE:
                    classification = "DERIVABLE_CANDIDATE"
                    evidence = DERIVABLE[spec.key]
                else:
                    classification = "RAW_REQUIRED_OR_REVIEW"
                    evidence = None
            status_counts[classification] += 1
            rows.append({
                "key": spec.key,
                "label": spec.label,
                "bible_name": spec.bible_name,
                "surfaces": sorted(spec.surfaces),
                "classification": classification,
                "evidence": evidence,
            })

        return {
            "metric_set_version": METRIC_SET_VERSION,
            "r2_key": r2_key,
            "season_id": SEASON_ID,
            "matches": int(matches[0]),
            "whoscored_ingested_matches": int(matches[1]),
            "whoscored_event_rows": int(sum(event_counts.values())),
            "event_type_count": len(event_counts),
            "player_match_stat_columns": sorted(pcols),
            "team_match_stat_columns": sorted(tcols),
            "classification_counts": dict(sorted(status_counts.items())),
            "metrics": rows,
            "contract": {
                "audit_only": True,
                "candidate_does_not_mean_approved_bridge": True,
                "next_gate": "Regression-test each candidate against Metrics Bible canonical calculations/golden fixtures before any production materialisation.",
            },
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", default="football/staging/2025-26.duckdb")
    parser.add_argument("--db", default="/tmp/metrics-bible-staging-audit.duckdb")
    parser.add_argument("--report", default="/tmp/metrics-bible-staging-audit.json")
    args = parser.parse_args()
    db = Path(args.db)
    report_path = Path(args.report)
    download(args.key, db)
    report = audit(db, args.key)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "metric_set_version": report["metric_set_version"],
        "matches": report["matches"],
        "whoscored_ingested_matches": report["whoscored_ingested_matches"],
        "whoscored_event_rows": report["whoscored_event_rows"],
        "classification_counts": report["classification_counts"],
    }, indent=2))
    print(f"wrote_report={report_path}")


if __name__ == "__main__":
    main()
