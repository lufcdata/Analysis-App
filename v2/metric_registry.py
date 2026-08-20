"""Canonical LUFCDATA metric registry for the 18 August 2026 hard cutover."""

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Optional, Tuple

METRIC_SET_VERSION = "2026-08-18.1"


class MetricStatus(str, Enum):
    IMPLEMENT = "IMPLEMENT"
    UNAVAILABLE = "UNAVAILABLE"


class MetricKind(str, Enum):
    SCALAR = "SCALAR"
    RELATIONSHIP = "RELATIONSHIP"


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    surfaces: FrozenSet[str]
    status: MetricStatus
    bible_name: Optional[str] = None
    reason: Optional[str] = None
    kind: MetricKind = MetricKind.SCALAR


def _key(label: str) -> str:
    import re
    value = label.lower().replace("%", " percent ")
    value = value.replace("/", " ").replace("-", " ")
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


LIVE_LABELS: Tuple[str, ...] = (
    "Touches", "Final Third Touches", "Successful Passes", "Unsuccessful Passes",
    "Total Passes", "Pass Accuracy %", "Progressive Passes", "Successful Take-Ons", "Unsuccessful Take-Ons",
    "Take-On Attempts / Total Take-Ons", "Tackles Won", "Tackles Lost", "Interceptions",
    "Ball Recoveries", "Big Chances Created", "Key Passes", "Assists", "Chances Created",
    "Clean Sheets", "Goals Conceded", "Saves", "Shots On-Target Faced", "Save Percentage %",
    "Throw-Ins / Total Throws", "Successful Throw-Ins", "Unsuccessful Throw-Ins",
    "Long Throws into Opposition Penalty Area", "Successful Long Throws into Opposition Penalty Area",
    "Unsuccessful Long Throws into Opposition Penalty Area", "Aerial Duels Won", "Aerial Duels Lost",
    "Ground Duels Won", "Ground Duels Lost", "Duels Won", "Duels Lost", "Penalty Box Touches",
    "Forward Passes", "Backward Passes", "Side Passes", "Successful Final Third Passes",
    "Successful Passes Into Penalty Box", "Clearances", "Headed Clearances", "Goals",
    "Goals - Open Play", "Goals - Penalties", "Goals - Own-Goals", "Goals - Free-kicks",
    "Goals - Set-Pieces", "Goals - Outside Box", "Goals - Right Foot", "Goals - Left Foot",
    "Goals - Head", "Goals - Other", "Goals - Fast Break", "Goals - 6 Yard Box",
    "Goals - Penalty Area", "Shots", "Shots On-Target", "Shots Off-Target", "Blocked Shots",
    "Shots - Open Play", "Shots - Direct Free-Kick", "Shots from Set-Pieces", "Shots - Outside Box",
    "Shots - Right Foot", "Shots - Left Foot", "Shots - Head", "Shots - Other", "Shots - Fast Break",
    "Shots - 6 Yard Box", "Shots - Penalty Area", "Shots - Woodwork", "Successful Corners",
    "Unsuccessful Corners", "Corner - Short", "Corner - Near Post", "Corner - Central",
    "Corner - Far Post", "Corner - Overhit", "Corner - Assists", "Corner - Chances Created",
    "Red Cards", "Fouls Won", "Fouls Committed", "Big Chances", "Big Chances Scored",
    "Big Chances Missed", "Possession", "Free-Kicks", "Free-Kicks Into the Penalty Box",
    "Direct Free-Kicks", "Passes Received", "Passes Made", "Pass Combination",
)

MATCH_LABELS: Tuple[str, ...] = (
    "Goals", "Possession", "Touches", "Penalty Box Touches", "Shots", "Shots On-Target",
    "Set-Piece Goals", "Big Chances", "Chances Created", "Progressive Passes", "Successful Final Third Passes",
    "Successful Passes", "Accurate Long Passes", "Pass Accuracy", "Accurate Crosses",
    "Successful Take-Ons", "Ball Recoveries", "Tackles Won", "Interceptions", "Ground Duels Won",
    "Aerial Duels Won", "Clearances", "Corners", "Saves", "Red Cards",
)

BIBLE_BINDINGS = {
    "Take-On Attempts / Total Take-Ons": "Total Take-Ons",
    "Throw-Ins / Total Throws": "Throw-Ins",
    "Successful Passes Into Penalty Box": "Successful Passes in Penalty Box",
    "Goals - Own-Goals": "Goals - Own Goals",
    "Goals - Set-Pieces": "Goals - Set pieces",
    "Goals - Other": "Goals - Other body part",
    "Goals - Fast Break": "Goals - Fastbreak",
    "Goals - 6 Yard Box": "Goals - 6-yard box",
    "Shots - 6 Yard Box": "Shots - 6 Yard Box",
    "Corner - Short": "Short Corners",
    "Corner - Near Post": "Near Post Corners",
    "Corner - Central": "Central Corners",
    "Corner - Far Post": "Far Post Corners",
    "Corner - Overhit": "Overhit Corners",
    "Fouls Won": "Times Fouled",
    "Possession": "Possession Share — V2",
    "Set-Piece Goals": "Goals - Set pieces",
    "Pass Accuracy": "Pass Accuracy %",
    "Pass Combination": "Pass Combinations / Passes From Player",
    "Progressive Passes": "Open-Play Progressive Passes",
}

RELATIONSHIP_LABELS = {"Pass Combination"}

UNAVAILABLE_REASONS = {
    "Free-Kicks Into the Penalty Box": "PARKED: approved Aug 18 metric; exact locked implementation evidence to be recovered before activation.",
    "Direct Free-Kicks": "PARKED: approved Aug 18 metric; exact locked implementation evidence to be recovered before activation.",
}


def _build_registry():
    surfaces = {}
    for label in LIVE_LABELS:
        surfaces.setdefault(label, set()).add("live")
    for label in MATCH_LABELS:
        surfaces.setdefault(label, set()).add("match_stats")

    specs = []
    for label, approved_surfaces in surfaces.items():
        reason = UNAVAILABLE_REASONS.get(label)
        specs.append(MetricSpec(
            key=_key(label),
            label=label,
            surfaces=frozenset(approved_surfaces),
            status=MetricStatus.UNAVAILABLE if reason else MetricStatus.IMPLEMENT,
            bible_name=BIBLE_BINDINGS.get(label, label) if not reason else None,
            reason=reason,
            kind=MetricKind.RELATIONSHIP if label in RELATIONSHIP_LABELS else MetricKind.SCALAR,
        ))
    return tuple(specs)


METRICS: Tuple[MetricSpec, ...] = _build_registry()
BY_KEY = {metric.key: metric for metric in METRICS}

if len(BY_KEY) != len(METRICS):
    raise RuntimeError("Canonical metric-key collision in Aug 18 registry")


def approved_for(surface: str) -> Tuple[MetricSpec, ...]:
    return tuple(metric for metric in METRICS if surface in metric.surfaces)


def unavailable_metrics() -> Tuple[MetricSpec, ...]:
    return tuple(metric for metric in METRICS if metric.status is MetricStatus.UNAVAILABLE)
