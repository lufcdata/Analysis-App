"""Single aggregation entrypoint for implemented Aug-18 canonical metrics."""
from .metric_registry import BY_KEY, MetricKind, MetricStatus, METRIC_SET_VERSION
from .canonical_pass_metrics import calculate_pass_metrics
from .canonical_progressive_pass_metrics import calculate_progressive_pass_metrics
from .canonical_pass_receiver_metrics import calculate_pass_receiver_metrics
from .canonical_attack_metrics import calculate_attack_metrics
from .canonical_touch_metrics import calculate_touch_metrics
from .canonical_defensive_duel_metrics import calculate_defensive_duel_metrics
from .canonical_corner_metrics import calculate_corner_metrics
from .canonical_chance_metrics import calculate_chance_metrics
from .canonical_throw_metrics import calculate_throw_metrics
from .canonical_big_chance_metrics import calculate_big_chance_metrics
from .canonical_possession_metrics import calculate_possession_metrics
from .canonical_goalkeeper_metrics import calculate_goalkeeper_metrics
from .canonical_free_kick_metrics import calculate_free_kick_metrics
from .canonical_cross_metrics import calculate_cross_metrics
from .canonical_discipline_metrics import calculate_discipline_metrics


def calculate_canonical_metrics(events, team_id=None, player_id=None, canonical_player_id=None, player_id_map=None, pass_receiver_assignments=None, assisted_source_event_ids=None, goalkeeper_active_windows=None, roster_player_ids=None, surface="live"):
    merged = {}
    for calculator, kwargs in (
        (calculate_pass_metrics, {}),
        (calculate_progressive_pass_metrics, {}),
        (calculate_pass_receiver_metrics, {"player_id": canonical_player_id, "player_id_map": player_id_map, "assignments": pass_receiver_assignments}),
        (calculate_attack_metrics, {}),
        (calculate_touch_metrics, {}),
        (calculate_defensive_duel_metrics, {}),
        (calculate_corner_metrics, {"assisted_source_event_ids": assisted_source_event_ids}),
        (calculate_chance_metrics, {"assisted_source_event_ids": assisted_source_event_ids}),
        (calculate_throw_metrics, {}),
        (calculate_big_chance_metrics, {}),
        (calculate_possession_metrics, {}),
        (calculate_goalkeeper_metrics, {"active_windows": goalkeeper_active_windows}),
        (calculate_free_kick_metrics, {}),
        (calculate_cross_metrics, {}),
        (calculate_discipline_metrics, {"roster_player_ids": roster_player_ids}),
    ):
        if calculator is calculate_pass_receiver_metrics:
            values = calculator(events, team_id=team_id, **kwargs)
        else:
            values = calculator(events, team_id=team_id, player_id=player_id, **kwargs)
        overlap = set(merged).intersection(values)
        if overlap:
            raise RuntimeError(f"Duplicate canonical metric implementation: {sorted(overlap)}")
        merged.update(values)
    scalar_allowed = {key for key, spec in BY_KEY.items() if spec.status is MetricStatus.IMPLEMENT and spec.kind is MetricKind.SCALAR and surface in spec.surfaces}
    relationship_active = sorted(key for key, spec in BY_KEY.items() if spec.status is MetricStatus.IMPLEMENT and spec.kind is MetricKind.RELATIONSHIP and surface in spec.surfaces)
    return {
        "metric_set_version": METRIC_SET_VERSION,
        "metrics": {key: merged.get(key, 0) for key in sorted(scalar_allowed) if key in merged},
        "unimplemented_active_keys": sorted(key for key in scalar_allowed if key not in merged),
        "active_relationship_keys": relationship_active,
    }
