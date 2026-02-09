"""Lead zone scoring engine."""

from app.scoring.engine import run_scoring_pipeline, score_single_zone
from app.scoring.decay import calculate_decay, DECAY_RATE, MAX_AGE_DAYS
from app.scoring.spatial import (
    point_to_h3,
    cluster_events_to_h3,
    build_zone_boundary,
    get_intersecting_tracts,
    compute_weighted_demographics,
    compute_housing_density,
)
from app.scoring.weights import (
    CURRENT_MODEL_VERSION,
    ScoreBand,
    get_score_band,
    get_predicted_conversion_rate,
)

__all__ = [
    "run_scoring_pipeline",
    "score_single_zone",
    "calculate_decay",
    "DECAY_RATE",
    "MAX_AGE_DAYS",
    "point_to_h3",
    "cluster_events_to_h3",
    "build_zone_boundary",
    "get_intersecting_tracts",
    "compute_weighted_demographics",
    "compute_housing_density",
    "CURRENT_MODEL_VERSION",
    "ScoreBand",
    "get_score_band",
    "get_predicted_conversion_rate",
]
