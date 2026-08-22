"""Matchday Studio product contract for the current 33-row Match Stats surface.

This is the single backend source of truth for WHAT the Matchday Studio exposes.
Metric calculations remain owned by the canonical V2 / Metrics Bible engine.
Provider labels below are ingestion identifiers only and never define a fallback
calculation or image source.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MatchStatSpec:
    key: str
    label: str
    canonical_key: str | None = None
    percent: bool = False


MATCH_STATS: tuple[MatchStatSpec, ...] = (
    MatchStatSpec("goals", "Goals", "goals"),
    MatchStatSpec("xg", "xG"),
    MatchStatSpec("possession", "Possession", "possession", True),
    MatchStatSpec("touches", "Touches", "touches"),
    MatchStatSpec("opposition_box_touches", "Opposition Box Touches", "penalty_box_touches"),
    MatchStatSpec("shots", "Shots", "shots"),
    MatchStatSpec("shots_on_target", "Shots On-Target", "shots_on_target"),
    MatchStatSpec("shots_outside_box", "Shots Outside Box"),
    MatchStatSpec("big_chances", "Big Chances", "big_chances"),
    MatchStatSpec("chances_created", "Chances Created", "chances_created"),
    MatchStatSpec("successful_passes", "Successful Passes", "successful_passes"),
    MatchStatSpec("total_passes", "Total Passes"),
    MatchStatSpec("successful_final_third_passes", "Successful Final Third Passes", "successful_final_third_passes"),
    MatchStatSpec("pass_accuracy", "Pass Accuracy", "pass_accuracy", True),
    MatchStatSpec("ball_carries", "Ball Carries"),
    MatchStatSpec("progressive_carries", "Progressive Carries"),
    MatchStatSpec("progressive_carrying_distance_m", "Progressive Carrying Distance (m)"),
    MatchStatSpec("accurate_long_passes", "Accurate Long Passes", "accurate_long_passes"),
    MatchStatSpec("final_third_entries", "Final Third Entries"),
    MatchStatSpec("accurate_crosses", "Accurate Crosses", "accurate_crosses"),
    MatchStatSpec("ground_duels_won", "Ground Duels Won", "ground_duels_won"),
    MatchStatSpec("aerial_duels_won", "Aerial Duels Won", "aerial_duels_won"),
    MatchStatSpec("duels_won", "Duels Won", "duels_won"),
    MatchStatSpec("ball_recoveries", "Ball Recoveries", "ball_recoveries"),
    MatchStatSpec("successful_take_ons", "Successful Take-Ons", "successful_take_ons"),
    MatchStatSpec("tackles_won", "Tackles Won", "tackles_won"),
    MatchStatSpec("interceptions", "Interceptions", "interceptions"),
    MatchStatSpec("clearances", "Clearances", "clearances"),
    MatchStatSpec("fouls", "Fouls"),
    MatchStatSpec("fouled", "Fouled"),
    MatchStatSpec("possession_lost", "Possession Lost"),
    MatchStatSpec("corners", "Corners", "corners"),
    MatchStatSpec("saves", "Saves", "saves"),
)

if len(MATCH_STATS) != 33:
    raise RuntimeError("Matchday Studio Match Stats contract must contain exactly 33 metrics")
if len({spec.key for spec in MATCH_STATS}) != len(MATCH_STATS):
    raise RuntimeError("Duplicate Matchday Studio metric key")

MATCH_STATS_BY_LABEL = {spec.label: spec for spec in MATCH_STATS}
MATCH_STATS_BY_KEY = {spec.key: spec for spec in MATCH_STATS}
MATCH_STATS_CONTRACT_VERSION = "matchlab-stats-33-2026-08-21"
