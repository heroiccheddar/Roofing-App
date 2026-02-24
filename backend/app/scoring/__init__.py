"""Lead zone scoring engine."""

# Storm rescore pipeline (primary name) + backward-compat alias
from app.scoring.engine import (
    run_storm_rescore_pipeline,
    run_scoring_pipeline,  # alias -> run_storm_rescore_pipeline
    score_single_zone,
)

# Base scoring pipeline (scores all GA census tracts)
from app.scoring.base_engine import run_base_scoring_pipeline

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
    UNIFIED_MODEL_VERSION,
    ScoreBand,
    get_score_band,
    get_predicted_conversion_rate,
)

__all__ = [
    # Storm pipeline (new name + alias)
    "run_storm_rescore_pipeline",
    "run_scoring_pipeline",
    "score_single_zone",
    # Base pipeline
    "run_base_scoring_pipeline",
    # Decay
    "calculate_decay",
    "DECAY_RATE",
    "MAX_AGE_DAYS",
    # Spatial utilities
    "point_to_h3",
    "cluster_events_to_h3",
    "build_zone_boundary",
    "get_intersecting_tracts",
    "compute_weighted_demographics",
    "compute_housing_density",
    # Model versions
    "CURRENT_MODEL_VERSION",
    "UNIFIED_MODEL_VERSION",
    "ScoreBand",
    "get_score_band",
    "get_predicted_conversion_rate",
]
