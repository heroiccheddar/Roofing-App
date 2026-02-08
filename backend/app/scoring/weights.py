"""Scoring weights module.

Defines the model version, weight configuration, score bands, and predicted
conversion lookups. This module is imported by the scoring engine, zone
generation, calibration engine, and admin endpoints.

All weights are internal data structures (dataclasses), not API schemas.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, Any


class ScoreBand(Enum):
    """Score band classifications with ranges and predicted conversion rates."""

    HOT = ("hot", 80, 100, 0.12)
    WARM = ("warm", 60, 79, 0.07)
    COOL = ("cool", 40, 59, 0.03)
    SKIP = ("skip", 0, 39, 0.01)

    def __init__(self, band_name: str, min_score: float, max_score: float, conversion_rate: float):
        self.band_name = band_name
        self.min_score = min_score
        self.max_score = max_score
        self.conversion_rate = conversion_rate

    @classmethod
    def from_score(cls, score: float) -> "ScoreBand":
        """Return the score band for a given composite score."""
        if score >= 80:
            return cls.HOT
        elif score >= 60:
            return cls.WARM
        elif score >= 40:
            return cls.COOL
        else:
            return cls.SKIP


@dataclass
class DamageWeights:
    """Weights for computing damage_prob sub-score from storm event data.

    Must sum to 1.0 (within tolerance).
    """
    hail_diameter: float
    wind_speed: float
    radar_confidence: float
    report_corroboration: float

    def sum(self) -> float:
        """Return the sum of all weights."""
        return (
            self.hail_diameter +
            self.wind_speed +
            self.radar_confidence +
            self.report_corroboration
        )


@dataclass
class LeadQualityWeights:
    """Weights for computing lead_quality sub-score from census data.

    Must sum to 1.0 (within tolerance).
    """
    owner_occupied_pct: float
    median_home_value: float
    median_year_built: float  # older = higher (inverted)
    housing_density: float

    def sum(self) -> float:
        """Return the sum of all weights."""
        return (
            self.owner_occupied_pct +
            self.median_home_value +
            self.median_year_built +
            self.housing_density
        )


@dataclass
class CompositeWeights:
    """Weights for combining sub-scores into final lead score.

    Formula: LEAD_SCORE = (DAMAGE_PROB × 0.50 + LEAD_QUALITY × 0.30 + DENSITY_BONUS × 0.20) × TIME_DECAY
    Must sum to 1.0 (within tolerance).
    """
    damage_prob: float
    lead_quality: float
    density_bonus: float

    def sum(self) -> float:
        """Return the sum of all weights."""
        return (
            self.damage_prob +
            self.lead_quality +
            self.density_bonus
        )


@dataclass
class ModelVersion:
    """Complete model version with all weight configurations.

    Used for versioning, serialization to lead_zones.score_weights_snapshot,
    and validation.
    """
    version: str  # semver, e.g., "1.0.0"
    damage_weights: DamageWeights
    lead_quality_weights: LeadQualityWeights
    composite_weights: CompositeWeights
    created_at: datetime
    description: str

    def validate(self, tolerance: float = 0.001) -> None:
        """Validate that all weight groups sum to 1.0 within tolerance.

        Args:
            tolerance: Acceptable deviation from 1.0 for floating point comparison

        Raises:
            ValueError: If any weight group does not sum to 1.0 within tolerance
        """
        damage_sum = self.damage_weights.sum()
        if abs(damage_sum - 1.0) > tolerance:
            raise ValueError(
                f"Damage weights sum to {damage_sum:.6f}, expected 1.0 ± {tolerance}"
            )

        quality_sum = self.lead_quality_weights.sum()
        if abs(quality_sum - 1.0) > tolerance:
            raise ValueError(
                f"Lead quality weights sum to {quality_sum:.6f}, expected 1.0 ± {tolerance}"
            )

        composite_sum = self.composite_weights.sum()
        if abs(composite_sum - 1.0) > tolerance:
            raise ValueError(
                f"Composite weights sum to {composite_sum:.6f}, expected 1.0 ± {tolerance}"
            )

    def to_snapshot(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict for storage in lead_zones.score_weights_snapshot.

        Returns:
            JSON-serializable dictionary
        """
        return {
            "version": self.version,
            "damage_weights": asdict(self.damage_weights),
            "lead_quality_weights": asdict(self.lead_quality_weights),
            "composite_weights": asdict(self.composite_weights),
            "created_at": self.created_at.isoformat(),
            "description": self.description,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "ModelVersion":
        """Deserialize from stored JSON snapshot.

        Args:
            data: Dictionary from to_snapshot()

        Returns:
            Reconstructed ModelVersion instance
        """
        return cls(
            version=data["version"],
            damage_weights=DamageWeights(**data["damage_weights"]),
            lead_quality_weights=LeadQualityWeights(**data["lead_quality_weights"]),
            composite_weights=CompositeWeights(**data["composite_weights"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            description=data["description"],
        )


# v1.0.0 model weights (initial production configuration)
CURRENT_MODEL_VERSION = ModelVersion(
    version="1.0.0",
    damage_weights=DamageWeights(
        hail_diameter=0.40,
        wind_speed=0.25,
        radar_confidence=0.20,
        report_corroboration=0.15,
    ),
    lead_quality_weights=LeadQualityWeights(
        owner_occupied_pct=0.35,
        median_home_value=0.30,
        median_year_built=0.25,
        housing_density=0.10,
    ),
    composite_weights=CompositeWeights(
        damage_prob=0.50,
        lead_quality=0.30,
        density_bonus=0.20,
    ),
    created_at=datetime(2025, 1, 1, 0, 0, 0),
    description="Initial production model weights based on domain expertise",
)


def get_score_band(score: float) -> ScoreBand:
    """Return the score band for a given composite score.

    Args:
        score: Composite lead score (0-100)

    Returns:
        ScoreBand enum value
    """
    return ScoreBand.from_score(score)


def get_predicted_conversion_rate(score: float) -> float:
    """Return the predicted conversion rate for a given score.

    Args:
        score: Composite lead score (0-100)

    Returns:
        Predicted conversion rate (0.0-1.0)
    """
    band = get_score_band(score)
    return band.conversion_rate


def get_predicted_conversion_for_band(band: ScoreBand) -> float:
    """Return the predicted conversion rate for a given band.

    Args:
        band: ScoreBand enum value

    Returns:
        Predicted conversion rate (0.0-1.0)
    """
    return band.conversion_rate
