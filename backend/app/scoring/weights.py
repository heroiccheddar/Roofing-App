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

    HOT = ("hot", 70, 100, 0.12)
    WARM = ("warm", 50, 69, 0.07)
    COOL = ("cool", 30, 49, 0.03)
    SKIP = ("skip", 0, 29, 0.01)

    def __init__(self, band_name: str, min_score: float, max_score: float, conversion_rate: float):
        self.band_name = band_name
        self.min_score = min_score
        self.max_score = max_score
        self.conversion_rate = conversion_rate

    @classmethod
    def from_score(cls, score: float) -> "ScoreBand":
        """Return the score band for a given composite score."""
        if score >= 70:
            return cls.HOT
        elif score >= 50:
            return cls.WARM
        elif score >= 30:
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
    income_bonus_max: float           # Max points from income (default 10.0)
    single_family_bonus_max: float    # Max points from single-family % (default 5.0)
    vacancy_penalty_max: float        # Max penalty from vacancy rate (default 5.0)

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
class NRIRiskWeights:
    """Weights for NRI risk contribution to damage_prob."""
    hail_freq_multiplier: float
    swnd_freq_multiplier: float
    trnd_freq_multiplier: float
    max_nri_bonus: float


@dataclass
class HistoricalExposureWeights:
    """Weights for historical hail and FEMA disaster exposure modifiers."""
    hail_exposure_max_bonus: float  # Max points from historical hail (default 15.0)
    fema_disaster_max_bonus: float  # Max points from FEMA declarations (default 10.0)


@dataclass
class TreeCanopyWeights:
    """Weights for tree canopy coverage modifiers."""
    storm_canopy_max_bonus: float   # Max pts from canopy in storm scoring (default 8.0)
    roof_age_canopy_max_bonus: float # Max pts from canopy in roof age scoring (default 5.0)


@dataclass
class AgeClusteringWeights:
    """Weights for subdivision age clustering modifiers."""
    roof_age_clustering_max_bonus: float  # Max pts in roof age scoring (default 8.0)


@dataclass
class ClimateWeatheringWeights:
    """Weights for climate-based weathering modifiers."""
    storm_climate_max_bonus: float        # Wind climatology bonus for storm damage (default 5.0)
    roof_age_climate_max_modifier: float  # Climate weathering modifier for roof age (default 10.0)


@dataclass
class FinancialCapacityWeights:
    """Weights for financial capacity modifiers (cost burden + HPI appreciation)."""
    cost_burden_max_bonus: float     # Low cost burden bonus in lead_quality (default 5.0)
    appreciation_max_bonus: float    # HPI appreciation bonus in lead_quality (default 5.0)


@dataclass
class VerifiedDamageWeights:
    """Weights for verified NCEI historical damage modifiers."""
    verified_damage_max_bonus: float  # Verified $ damage bonus in damage_prob (default 10.0)


@dataclass
class SVIWeights:
    """Weights for CDC Social Vulnerability Index modifiers."""
    storm_svi_max_bonus: float       # SVI vulnerability bonus in storm damage_prob (default 5.0)
    roof_age_svi_max_bonus: float    # SVI housing type bonus in roof age scoring (default 3.0)


@dataclass
class RedfinMarketWeights:
    """Weights for Redfin housing market activity modifiers."""
    market_activity_lq_weight: float    # Weight in lead_quality percentile mix (default 0.10)
    market_activity_ra_weight: float    # Weight in roof_age percentile mix (default 0.04)


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
    nri_weights: NRIRiskWeights
    historical_exposure_weights: HistoricalExposureWeights
    tree_canopy_weights: TreeCanopyWeights
    age_clustering_weights: AgeClusteringWeights
    climate_weathering_weights: ClimateWeatheringWeights
    financial_capacity_weights: FinancialCapacityWeights
    verified_damage_weights: VerifiedDamageWeights
    svi_weights: SVIWeights
    redfin_market_weights: RedfinMarketWeights
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
            "nri_weights": asdict(self.nri_weights),
            "historical_exposure_weights": asdict(self.historical_exposure_weights),
            "tree_canopy_weights": asdict(self.tree_canopy_weights),
            "age_clustering_weights": asdict(self.age_clustering_weights),
            "climate_weathering_weights": asdict(self.climate_weathering_weights),
            "financial_capacity_weights": asdict(self.financial_capacity_weights),
            "verified_damage_weights": asdict(self.verified_damage_weights),
            "svi_weights": asdict(self.svi_weights),
            "redfin_market_weights": asdict(self.redfin_market_weights),
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
        # Handle v1 snapshots without nri_weights (backward compatibility)
        if "nri_weights" not in data:
            nri_weights = NRIRiskWeights(
                hail_freq_multiplier=0.0,
                swnd_freq_multiplier=0.0,
                trnd_freq_multiplier=0.0,
                max_nri_bonus=0.0,
            )
        else:
            nri_weights = NRIRiskWeights(**data["nri_weights"])

        # Handle v1/v2 snapshots without historical_exposure_weights
        if "historical_exposure_weights" not in data:
            historical_exposure_weights = HistoricalExposureWeights(
                hail_exposure_max_bonus=0.0,
                fema_disaster_max_bonus=0.0,
            )
        else:
            historical_exposure_weights = HistoricalExposureWeights(**data["historical_exposure_weights"])

        # Handle snapshots without tree_canopy_weights
        if "tree_canopy_weights" not in data:
            tree_canopy_weights = TreeCanopyWeights(
                storm_canopy_max_bonus=0.0,
                roof_age_canopy_max_bonus=0.0,
            )
        else:
            tree_canopy_weights = TreeCanopyWeights(**data["tree_canopy_weights"])

        # Handle snapshots without age_clustering_weights
        if "age_clustering_weights" not in data:
            age_clustering_weights = AgeClusteringWeights(
                roof_age_clustering_max_bonus=0.0,
            )
        else:
            age_clustering_weights = AgeClusteringWeights(**data["age_clustering_weights"])

        # Handle snapshots without climate_weathering_weights
        if "climate_weathering_weights" not in data:
            climate_weathering_weights = ClimateWeatheringWeights(
                storm_climate_max_bonus=0.0,
                roof_age_climate_max_modifier=0.0,
            )
        else:
            climate_weathering_weights = ClimateWeatheringWeights(**data["climate_weathering_weights"])

        # Handle snapshots without financial_capacity_weights
        if "financial_capacity_weights" not in data:
            financial_capacity_weights = FinancialCapacityWeights(
                cost_burden_max_bonus=0.0,
                appreciation_max_bonus=0.0,
            )
        else:
            financial_capacity_weights = FinancialCapacityWeights(**data["financial_capacity_weights"])

        # Handle snapshots without verified_damage_weights
        if "verified_damage_weights" not in data:
            verified_damage_weights = VerifiedDamageWeights(
                verified_damage_max_bonus=0.0,
            )
        else:
            verified_damage_weights = VerifiedDamageWeights(**data["verified_damage_weights"])

        # Handle snapshots without svi_weights
        if "svi_weights" not in data:
            svi_weights = SVIWeights(
                storm_svi_max_bonus=0.0,
                roof_age_svi_max_bonus=0.0,
            )
        else:
            svi_weights = SVIWeights(**data["svi_weights"])

        # Handle snapshots without redfin_market_weights
        if "redfin_market_weights" not in data:
            redfin_market_weights = RedfinMarketWeights(
                market_activity_lq_weight=0.0,
                market_activity_ra_weight=0.0,
            )
        else:
            redfin_market_weights = RedfinMarketWeights(**data["redfin_market_weights"])

        return cls(
            version=data["version"],
            damage_weights=DamageWeights(**data["damage_weights"]),
            lead_quality_weights=LeadQualityWeights(**data["lead_quality_weights"]),
            composite_weights=CompositeWeights(**data["composite_weights"]),
            nri_weights=nri_weights,
            historical_exposure_weights=historical_exposure_weights,
            tree_canopy_weights=tree_canopy_weights,
            age_clustering_weights=age_clustering_weights,
            climate_weathering_weights=climate_weathering_weights,
            financial_capacity_weights=financial_capacity_weights,
            verified_damage_weights=verified_damage_weights,
            svi_weights=svi_weights,
            redfin_market_weights=redfin_market_weights,
            created_at=datetime.fromisoformat(data["created_at"]),
            description=data["description"],
        )


# v1.0.0 model weights (initial production configuration)
V1_MODEL_VERSION = ModelVersion(
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
        income_bonus_max=0.0,
        single_family_bonus_max=0.0,
        vacancy_penalty_max=0.0,
    ),
    composite_weights=CompositeWeights(
        damage_prob=0.50,
        lead_quality=0.30,
        density_bonus=0.20,
    ),
    nri_weights=NRIRiskWeights(
        hail_freq_multiplier=0.0,
        swnd_freq_multiplier=0.0,
        trnd_freq_multiplier=0.0,
        max_nri_bonus=0.0,
    ),
    historical_exposure_weights=HistoricalExposureWeights(
        hail_exposure_max_bonus=0.0,
        fema_disaster_max_bonus=0.0,
    ),
    tree_canopy_weights=TreeCanopyWeights(
        storm_canopy_max_bonus=0.0,
        roof_age_canopy_max_bonus=0.0,
    ),
    age_clustering_weights=AgeClusteringWeights(
        roof_age_clustering_max_bonus=0.0,
    ),
    climate_weathering_weights=ClimateWeatheringWeights(
        storm_climate_max_bonus=0.0,
        roof_age_climate_max_modifier=0.0,
    ),
    financial_capacity_weights=FinancialCapacityWeights(
        cost_burden_max_bonus=0.0,
        appreciation_max_bonus=0.0,
    ),
    verified_damage_weights=VerifiedDamageWeights(
        verified_damage_max_bonus=0.0,
    ),
    svi_weights=SVIWeights(
        storm_svi_max_bonus=0.0,
        roof_age_svi_max_bonus=0.0,
    ),
    redfin_market_weights=RedfinMarketWeights(
        market_activity_lq_weight=0.0,
        market_activity_ra_weight=0.0,
    ),
    created_at=datetime(2025, 1, 1, 0, 0, 0),
    description="Initial production model weights based on domain expertise",
)

# v2.0.0 model weights (adds NRI risk, income, occupancy, building footprints)
V2_MODEL_VERSION = ModelVersion(
    version="2.0.0",
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
        income_bonus_max=10.0,
        single_family_bonus_max=5.0,
        vacancy_penalty_max=5.0,
    ),
    composite_weights=CompositeWeights(
        damage_prob=0.50,
        lead_quality=0.30,
        density_bonus=0.20,
    ),
    nri_weights=NRIRiskWeights(
        hail_freq_multiplier=5.0,
        swnd_freq_multiplier=2.5,
        trnd_freq_multiplier=10.0,
        max_nri_bonus=15.0,
    ),
    historical_exposure_weights=HistoricalExposureWeights(
        hail_exposure_max_bonus=0.0,
        fema_disaster_max_bonus=0.0,
    ),
    tree_canopy_weights=TreeCanopyWeights(
        storm_canopy_max_bonus=0.0,
        roof_age_canopy_max_bonus=0.0,
    ),
    age_clustering_weights=AgeClusteringWeights(
        roof_age_clustering_max_bonus=0.0,
    ),
    climate_weathering_weights=ClimateWeatheringWeights(
        storm_climate_max_bonus=0.0,
        roof_age_climate_max_modifier=0.0,
    ),
    financial_capacity_weights=FinancialCapacityWeights(
        cost_burden_max_bonus=0.0,
        appreciation_max_bonus=0.0,
    ),
    verified_damage_weights=VerifiedDamageWeights(
        verified_damage_max_bonus=0.0,
    ),
    svi_weights=SVIWeights(
        storm_svi_max_bonus=0.0,
        roof_age_svi_max_bonus=0.0,
    ),
    redfin_market_weights=RedfinMarketWeights(
        market_activity_lq_weight=0.0,
        market_activity_ra_weight=0.0,
    ),
    created_at=datetime(2026, 2, 10, 0, 0, 0),
    description="v2.0.0: Adds NRI risk, income, occupancy, building footprints",
)

# v3.0.0 model weights (adds historical hail exposure + FEMA disaster declarations)
V3_MODEL_VERSION = ModelVersion(
    version="3.0.0",
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
        income_bonus_max=10.0,
        single_family_bonus_max=5.0,
        vacancy_penalty_max=5.0,
    ),
    composite_weights=CompositeWeights(
        damage_prob=0.50,
        lead_quality=0.30,
        density_bonus=0.20,
    ),
    nri_weights=NRIRiskWeights(
        hail_freq_multiplier=5.0,
        swnd_freq_multiplier=2.5,
        trnd_freq_multiplier=10.0,
        max_nri_bonus=15.0,
    ),
    historical_exposure_weights=HistoricalExposureWeights(
        hail_exposure_max_bonus=15.0,
        fema_disaster_max_bonus=10.0,
    ),
    tree_canopy_weights=TreeCanopyWeights(
        storm_canopy_max_bonus=0.0,
        roof_age_canopy_max_bonus=0.0,
    ),
    age_clustering_weights=AgeClusteringWeights(
        roof_age_clustering_max_bonus=0.0,
    ),
    climate_weathering_weights=ClimateWeatheringWeights(
        storm_climate_max_bonus=0.0,
        roof_age_climate_max_modifier=0.0,
    ),
    financial_capacity_weights=FinancialCapacityWeights(
        cost_burden_max_bonus=0.0,
        appreciation_max_bonus=0.0,
    ),
    verified_damage_weights=VerifiedDamageWeights(
        verified_damage_max_bonus=0.0,
    ),
    svi_weights=SVIWeights(
        storm_svi_max_bonus=0.0,
        roof_age_svi_max_bonus=0.0,
    ),
    redfin_market_weights=RedfinMarketWeights(
        market_activity_lq_weight=0.0,
        market_activity_ra_weight=0.0,
    ),
    created_at=datetime(2026, 2, 10, 0, 0, 0),
    description="v3.0.0: Adds historical hail exposure + FEMA disaster declarations",
)

# v4.0.0 model weights (adds tree canopy coverage)
V4_MODEL_VERSION = ModelVersion(
    version="4.0.0",
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
        income_bonus_max=10.0,
        single_family_bonus_max=5.0,
        vacancy_penalty_max=5.0,
    ),
    composite_weights=CompositeWeights(
        damage_prob=0.50,
        lead_quality=0.30,
        density_bonus=0.20,
    ),
    nri_weights=NRIRiskWeights(
        hail_freq_multiplier=5.0,
        swnd_freq_multiplier=2.5,
        trnd_freq_multiplier=10.0,
        max_nri_bonus=15.0,
    ),
    historical_exposure_weights=HistoricalExposureWeights(
        hail_exposure_max_bonus=15.0,
        fema_disaster_max_bonus=10.0,
    ),
    tree_canopy_weights=TreeCanopyWeights(
        storm_canopy_max_bonus=8.0,
        roof_age_canopy_max_bonus=5.0,
    ),
    age_clustering_weights=AgeClusteringWeights(
        roof_age_clustering_max_bonus=0.0,
    ),
    climate_weathering_weights=ClimateWeatheringWeights(
        storm_climate_max_bonus=0.0,
        roof_age_climate_max_modifier=0.0,
    ),
    financial_capacity_weights=FinancialCapacityWeights(
        cost_burden_max_bonus=0.0,
        appreciation_max_bonus=0.0,
    ),
    verified_damage_weights=VerifiedDamageWeights(
        verified_damage_max_bonus=0.0,
    ),
    svi_weights=SVIWeights(
        storm_svi_max_bonus=0.0,
        roof_age_svi_max_bonus=0.0,
    ),
    redfin_market_weights=RedfinMarketWeights(
        market_activity_lq_weight=0.0,
        market_activity_ra_weight=0.0,
    ),
    created_at=datetime(2026, 2, 10, 12, 0, 0),
    description="v4.0.0: Adds tree canopy coverage as damage amplifier",
)

# v5.0.0 model weights (adds subdivision age clustering)
V5_MODEL_VERSION = ModelVersion(
    version="5.0.0",
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
        income_bonus_max=10.0,
        single_family_bonus_max=5.0,
        vacancy_penalty_max=5.0,
    ),
    composite_weights=CompositeWeights(
        damage_prob=0.50,
        lead_quality=0.30,
        density_bonus=0.20,
    ),
    nri_weights=NRIRiskWeights(
        hail_freq_multiplier=5.0,
        swnd_freq_multiplier=2.5,
        trnd_freq_multiplier=10.0,
        max_nri_bonus=15.0,
    ),
    historical_exposure_weights=HistoricalExposureWeights(
        hail_exposure_max_bonus=15.0,
        fema_disaster_max_bonus=10.0,
    ),
    tree_canopy_weights=TreeCanopyWeights(
        storm_canopy_max_bonus=8.0,
        roof_age_canopy_max_bonus=5.0,
    ),
    age_clustering_weights=AgeClusteringWeights(
        roof_age_clustering_max_bonus=8.0,
    ),
    climate_weathering_weights=ClimateWeatheringWeights(
        storm_climate_max_bonus=0.0,
        roof_age_climate_max_modifier=0.0,
    ),
    financial_capacity_weights=FinancialCapacityWeights(
        cost_burden_max_bonus=0.0,
        appreciation_max_bonus=0.0,
    ),
    verified_damage_weights=VerifiedDamageWeights(
        verified_damage_max_bonus=0.0,
    ),
    svi_weights=SVIWeights(
        storm_svi_max_bonus=0.0,
        roof_age_svi_max_bonus=0.0,
    ),
    redfin_market_weights=RedfinMarketWeights(
        market_activity_lq_weight=0.0,
        market_activity_ra_weight=0.0,
    ),
    created_at=datetime(2026, 2, 10, 14, 0, 0),
    description="v5.0.0: Adds subdivision age clustering for roof age leads",
)

# v6.0.0 model weights (adds climate weathering, financial capacity, verified damage)
V6_MODEL_VERSION = ModelVersion(
    version="6.0.0",
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
        income_bonus_max=10.0,
        single_family_bonus_max=5.0,
        vacancy_penalty_max=5.0,
    ),
    composite_weights=CompositeWeights(
        damage_prob=0.50,
        lead_quality=0.30,
        density_bonus=0.20,
    ),
    nri_weights=NRIRiskWeights(
        hail_freq_multiplier=5.0,
        swnd_freq_multiplier=2.5,
        trnd_freq_multiplier=10.0,
        max_nri_bonus=15.0,
    ),
    historical_exposure_weights=HistoricalExposureWeights(
        hail_exposure_max_bonus=15.0,
        fema_disaster_max_bonus=10.0,
    ),
    tree_canopy_weights=TreeCanopyWeights(
        storm_canopy_max_bonus=8.0,
        roof_age_canopy_max_bonus=5.0,
    ),
    age_clustering_weights=AgeClusteringWeights(
        roof_age_clustering_max_bonus=8.0,
    ),
    climate_weathering_weights=ClimateWeatheringWeights(
        storm_climate_max_bonus=5.0,
        roof_age_climate_max_modifier=10.0,
    ),
    financial_capacity_weights=FinancialCapacityWeights(
        cost_burden_max_bonus=5.0,
        appreciation_max_bonus=5.0,
    ),
    verified_damage_weights=VerifiedDamageWeights(
        verified_damage_max_bonus=10.0,
    ),
    svi_weights=SVIWeights(
        storm_svi_max_bonus=0.0,
        roof_age_svi_max_bonus=0.0,
    ),
    redfin_market_weights=RedfinMarketWeights(
        market_activity_lq_weight=0.0,
        market_activity_ra_weight=0.0,
    ),
    created_at=datetime(2026, 2, 10, 16, 0, 0),
    description="v6.0.0: Adds climate weathering, financial capacity, verified NCEI damage",
)

# v7.0.0 model weights (percentile-normalized lead_quality + density_bonus)
V7_MODEL_VERSION = ModelVersion(
    version="7.0.0",
    damage_weights=DamageWeights(
        hail_diameter=0.40,
        wind_speed=0.25,
        radar_confidence=0.20,
        report_corroboration=0.15,
    ),
    lead_quality_weights=LeadQualityWeights(
        owner_occupied_pct=0.20,
        median_home_value=0.15,
        median_year_built=0.20,
        housing_density=0.05,
        income_bonus_max=0.15,
        single_family_bonus_max=0.05,
        vacancy_penalty_max=0.05,
    ),
    composite_weights=CompositeWeights(
        damage_prob=0.50,
        lead_quality=0.30,
        density_bonus=0.20,
    ),
    nri_weights=NRIRiskWeights(
        hail_freq_multiplier=5.0,
        swnd_freq_multiplier=2.5,
        trnd_freq_multiplier=10.0,
        max_nri_bonus=15.0,
    ),
    historical_exposure_weights=HistoricalExposureWeights(
        hail_exposure_max_bonus=15.0,
        fema_disaster_max_bonus=10.0,
    ),
    tree_canopy_weights=TreeCanopyWeights(
        storm_canopy_max_bonus=8.0,
        roof_age_canopy_max_bonus=5.0,
    ),
    age_clustering_weights=AgeClusteringWeights(
        roof_age_clustering_max_bonus=8.0,
    ),
    climate_weathering_weights=ClimateWeatheringWeights(
        storm_climate_max_bonus=5.0,
        roof_age_climate_max_modifier=10.0,
    ),
    financial_capacity_weights=FinancialCapacityWeights(
        cost_burden_max_bonus=5.0,
        appreciation_max_bonus=5.0,
    ),
    verified_damage_weights=VerifiedDamageWeights(
        verified_damage_max_bonus=10.0,
    ),
    svi_weights=SVIWeights(
        storm_svi_max_bonus=0.0,
        roof_age_svi_max_bonus=0.0,
    ),
    redfin_market_weights=RedfinMarketWeights(
        market_activity_lq_weight=0.0,
        market_activity_ra_weight=0.0,
    ),
    created_at=datetime(2026, 2, 11, 0, 0, 0),
    description="v7.0.0: Percentile-normalized lead_quality and density_bonus for better score spread",
)

# v8.0.0 model weights (adds CDC SVI social vulnerability)
V8_MODEL_VERSION = ModelVersion(
    version="8.0.0",
    damage_weights=DamageWeights(
        hail_diameter=0.40,
        wind_speed=0.25,
        radar_confidence=0.20,
        report_corroboration=0.15,
    ),
    lead_quality_weights=LeadQualityWeights(
        owner_occupied_pct=0.20,
        median_home_value=0.15,
        median_year_built=0.20,
        housing_density=0.05,
        income_bonus_max=0.15,
        single_family_bonus_max=0.05,
        vacancy_penalty_max=0.05,
    ),
    composite_weights=CompositeWeights(
        damage_prob=0.50,
        lead_quality=0.30,
        density_bonus=0.20,
    ),
    nri_weights=NRIRiskWeights(
        hail_freq_multiplier=5.0,
        swnd_freq_multiplier=2.5,
        trnd_freq_multiplier=10.0,
        max_nri_bonus=15.0,
    ),
    historical_exposure_weights=HistoricalExposureWeights(
        hail_exposure_max_bonus=15.0,
        fema_disaster_max_bonus=10.0,
    ),
    tree_canopy_weights=TreeCanopyWeights(
        storm_canopy_max_bonus=8.0,
        roof_age_canopy_max_bonus=5.0,
    ),
    age_clustering_weights=AgeClusteringWeights(
        roof_age_clustering_max_bonus=8.0,
    ),
    climate_weathering_weights=ClimateWeatheringWeights(
        storm_climate_max_bonus=5.0,
        roof_age_climate_max_modifier=10.0,
    ),
    financial_capacity_weights=FinancialCapacityWeights(
        cost_burden_max_bonus=5.0,
        appreciation_max_bonus=5.0,
    ),
    verified_damage_weights=VerifiedDamageWeights(
        verified_damage_max_bonus=10.0,
    ),
    svi_weights=SVIWeights(
        storm_svi_max_bonus=5.0,
        roof_age_svi_max_bonus=3.0,
    ),
    redfin_market_weights=RedfinMarketWeights(
        market_activity_lq_weight=0.0,
        market_activity_ra_weight=0.0,
    ),
    created_at=datetime(2026, 2, 11, 18, 0, 0),
    description="v8.0.0: Adds CDC SVI social vulnerability for disaster susceptibility",
)

# v9.0.0 model weights (adds Redfin market activity signals)
V9_MODEL_VERSION = ModelVersion(
    version="9.0.0",
    damage_weights=DamageWeights(
        hail_diameter=0.40,
        wind_speed=0.25,
        radar_confidence=0.20,
        report_corroboration=0.15,
    ),
    lead_quality_weights=LeadQualityWeights(
        owner_occupied_pct=0.18,
        median_home_value=0.14,
        median_year_built=0.18,
        housing_density=0.05,
        income_bonus_max=0.14,
        single_family_bonus_max=0.05,
        vacancy_penalty_max=0.05,
    ),
    composite_weights=CompositeWeights(
        damage_prob=0.50,
        lead_quality=0.30,
        density_bonus=0.20,
    ),
    nri_weights=NRIRiskWeights(
        hail_freq_multiplier=5.0,
        swnd_freq_multiplier=2.5,
        trnd_freq_multiplier=10.0,
        max_nri_bonus=15.0,
    ),
    historical_exposure_weights=HistoricalExposureWeights(
        hail_exposure_max_bonus=15.0,
        fema_disaster_max_bonus=10.0,
    ),
    tree_canopy_weights=TreeCanopyWeights(
        storm_canopy_max_bonus=8.0,
        roof_age_canopy_max_bonus=5.0,
    ),
    age_clustering_weights=AgeClusteringWeights(
        roof_age_clustering_max_bonus=8.0,
    ),
    climate_weathering_weights=ClimateWeatheringWeights(
        storm_climate_max_bonus=5.0,
        roof_age_climate_max_modifier=10.0,
    ),
    financial_capacity_weights=FinancialCapacityWeights(
        cost_burden_max_bonus=5.0,
        appreciation_max_bonus=5.0,
    ),
    verified_damage_weights=VerifiedDamageWeights(
        verified_damage_max_bonus=10.0,
    ),
    svi_weights=SVIWeights(
        storm_svi_max_bonus=5.0,
        roof_age_svi_max_bonus=3.0,
    ),
    redfin_market_weights=RedfinMarketWeights(
        market_activity_lq_weight=0.10,
        market_activity_ra_weight=0.04,
    ),
    created_at=datetime(2026, 2, 12, 0, 0, 0),
    description="v9.0.0: Adds Redfin market activity signals (sale price, DOM, price drops)",
)

CURRENT_MODEL_VERSION = V9_MODEL_VERSION


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


def renormalize_scores(
    raw_scores: list[float],
    low_pct: float = 2.0,
    high_pct: float = 98.0,
) -> list[float]:
    """Re-normalize scores to fill 0-100 using a sigmoid (logistic) stretch.

    Instead of linear min-max scaling which hard-clips at 0 and 100, this
    uses a logistic function centered on the median. The slope is calibrated
    so that the low_pct percentile maps to ~2 and the high_pct percentile
    maps to ~98, but extreme scores smoothly asymptote toward 0/100 without
    ever piling up at the boundaries.

    Args:
        raw_scores: List of raw composite scores
        low_pct: Lower percentile for slope calibration (default 2nd)
        high_pct: Upper percentile for slope calibration (default 98th)

    Returns:
        List of re-normalized scores in same order as input
    """
    import math

    if len(raw_scores) < 2:
        return list(raw_scores)

    sorted_scores = sorted(raw_scores)
    n = len(sorted_scores)
    median = sorted_scores[n // 2]
    p_low = sorted_scores[max(0, int(n * low_pct / 100))]
    p_high = sorted_scores[min(n - 1, int(n * high_pct / 100))]

    if p_high <= p_low:
        return [50.0] * len(raw_scores)

    # Calibrate slope: we want sigmoid(p_high) ≈ 0.98
    # sigmoid(x) = 1 / (1 + exp(-k*(x - median)))
    # 0.98 = 1 / (1 + exp(-k*(p_high - median)))
    # => k = -ln(1/0.98 - 1) / (p_high - median) = ln(49) / (p_high - median)
    half_span = max(p_high - median, median - p_low)
    k = math.log(49) / half_span  # ln(49) ≈ 3.89

    return [
        round(100.0 / (1.0 + math.exp(-k * (s - median))), 2)
        for s in raw_scores
    ]


@dataclass
class RoofAgeCompositeWeights:
    """Weights for roof-age-based lead scoring (no storm component)."""
    roof_age: float       # Primary signal - older = better lead
    owner_occupied: float  # Owner-occupied more likely to hire
    home_value: float     # Can afford the work
    housing_density: float # Efficient canvassing

    def sum(self) -> float:
        return self.roof_age + self.owner_occupied + self.home_value + self.housing_density


@dataclass
class RoofAgeModelVersion:
    """Model version for roof-age scoring."""
    version: str
    weights: RoofAgeCompositeWeights
    created_at: datetime
    description: str

    def to_snapshot(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "lead_type": "roof_age",
            "weights": asdict(self.weights),
            "created_at": self.created_at.isoformat(),
            "description": self.description,
        }


V1_ROOF_AGE_MODEL_VERSION = RoofAgeModelVersion(
    version="1.0.0-roof-age",
    weights=RoofAgeCompositeWeights(
        roof_age=0.55,
        owner_occupied=0.20,
        home_value=0.15,
        housing_density=0.10,
    ),
    created_at=datetime(2025, 1, 1, 0, 0, 0),
    description="Roof age scoring model - identifies areas with aging roofs likely needing replacement",
)

V2_ROOF_AGE_MODEL_VERSION = RoofAgeModelVersion(
    version="2.0.0-roof-age",
    weights=RoofAgeCompositeWeights(
        roof_age=0.50,
        owner_occupied=0.20,
        home_value=0.15,
        housing_density=0.10,
    ),
    created_at=datetime(2026, 2, 10, 0, 0, 0),
    description="v2.0.0: Enhanced with pre-1980 housing, income, single-family pct",
)

V3_ROOF_AGE_MODEL_VERSION = RoofAgeModelVersion(
    version="3.0.0-roof-age",
    weights=RoofAgeCompositeWeights(
        roof_age=0.50,
        owner_occupied=0.20,
        home_value=0.15,
        housing_density=0.10,
    ),
    created_at=datetime(2026, 2, 10, 0, 0, 0),
    description="v3.0.0: Adds historical hail exposure + FEMA disaster storm history bonus",
)

V4_ROOF_AGE_MODEL_VERSION = RoofAgeModelVersion(
    version="4.0.0-roof-age",
    weights=RoofAgeCompositeWeights(
        roof_age=0.50,
        owner_occupied=0.20,
        home_value=0.15,
        housing_density=0.10,
    ),
    created_at=datetime(2026, 2, 10, 12, 0, 0),
    description="v4.0.0: Adds tree canopy coverage as aging accelerant",
)

V5_ROOF_AGE_MODEL_VERSION = RoofAgeModelVersion(
    version="5.0.0-roof-age",
    weights=RoofAgeCompositeWeights(
        roof_age=0.50,
        owner_occupied=0.20,
        home_value=0.15,
        housing_density=0.10,
    ),
    created_at=datetime(2026, 2, 10, 14, 0, 0),
    description="v5.0.0: Adds subdivision age clustering bonus",
)

V6_ROOF_AGE_MODEL_VERSION = RoofAgeModelVersion(
    version="6.0.0-roof-age",
    weights=RoofAgeCompositeWeights(
        roof_age=0.50,
        owner_occupied=0.20,
        home_value=0.15,
        housing_density=0.10,
    ),
    created_at=datetime(2026, 2, 10, 16, 0, 0),
    description="v6.0.0: Adds climate weathering, financial capacity, verified damage",
)

V7_ROOF_AGE_MODEL_VERSION = RoofAgeModelVersion(
    version="7.0.0-roof-age",
    weights=RoofAgeCompositeWeights(
        roof_age=0.25,
        owner_occupied=0.12,
        home_value=0.08,
        housing_density=0.06,
    ),
    created_at=datetime(2026, 2, 11, 0, 0, 0),
    description="v7.0.0: Percentile-normalized scoring for full 0-100 range spread",
)

V8_ROOF_AGE_MODEL_VERSION = RoofAgeModelVersion(
    version="8.0.0-roof-age",
    weights=RoofAgeCompositeWeights(
        roof_age=0.25,
        owner_occupied=0.12,
        home_value=0.08,
        housing_density=0.06,
    ),
    created_at=datetime(2026, 2, 11, 18, 0, 0),
    description="v8.0.0: Adds CDC SVI social vulnerability percentile feature",
)

V9_ROOF_AGE_MODEL_VERSION = RoofAgeModelVersion(
    version="9.0.0-roof-age",
    weights=RoofAgeCompositeWeights(
        roof_age=0.25,
        owner_occupied=0.12,
        home_value=0.08,
        housing_density=0.06,
    ),
    created_at=datetime(2026, 2, 12, 1, 0, 0),
    description="v9.0.0: Adds Redfin market_activity percentile feature",
)

ROOF_AGE_MODEL_VERSION = RoofAgeModelVersion(
    version="10.0.0-roof-age",
    weights=RoofAgeCompositeWeights(
        roof_age=0.25,
        owner_occupied=0.12,
        home_value=0.08,
        housing_density=0.06,
    ),
    created_at=datetime(2026, 2, 12, 12, 0, 0),
    description="v10.0.0: Percentile-based score re-normalization for full 0-100 range spread",
)


# ---------------------------------------------------------------------------
# v11.0.0 — Unified roofing lead intelligence model
#
# Replaces the dual-engine (storm + roof_age) design with a single zone per
# H3 hex that carries 4 orthogonal sub-scores and an optional storm boost.
#
# Composite formula (no storm):  base_score = rc*0.35 + mq*0.30 + re*0.20 + ce*0.15
# Composite formula (storm):     composite  = base_score*0.80 + storm_boost*0.20
# ---------------------------------------------------------------------------

@dataclass
class UnifiedSubScoreWeights:
    """Feature weights for a single sub-score.

    All weights within a sub-score must sum to 1.0.
    Each feature key corresponds to a pctile_<key> value from
    compute_weighted_demographics().
    """
    weights: Dict[str, float]

    def sum(self) -> float:
        return sum(self.weights.values())

    def to_dict(self) -> Dict[str, float]:
        return dict(self.weights)


@dataclass
class UnifiedCompositeWeights:
    """Weights for combining the 4 sub-scores into base_score."""
    roof_condition: float   # 0.35
    market_quality: float   # 0.30
    risk_exposure: float    # 0.20
    canvass_efficiency: float  # 0.15

    def sum(self) -> float:
        return self.roof_condition + self.market_quality + self.risk_exposure + self.canvass_efficiency


@dataclass
class UnifiedModelVersion:
    """Complete weight configuration for the unified RoofIQ scoring model v11.

    Sub-scores
    ----------
    roof_condition     : How old/degraded the roof is likely to be.
    market_quality     : How financially attractive/accessible the market is.
    risk_exposure      : How exposed the area is to storm/environmental damage.
    canvass_efficiency : How efficiently canvassers can work the area.

    Storm boost
    -----------
    When an active storm event exists for a hex, the composite score blends
    base_score (0.80) + storm_boost (0.20).  When no storm is active,
    composite_score == base_score.
    """
    version: str
    description: str
    created_at: datetime

    roof_condition_weights: UnifiedSubScoreWeights
    market_quality_weights: UnifiedSubScoreWeights
    risk_exposure_weights: UnifiedSubScoreWeights
    canvass_efficiency_weights: UnifiedSubScoreWeights
    composite_weights: UnifiedCompositeWeights

    # Blend weights when storm is active
    base_weight_with_storm: float    # 0.80
    storm_boost_weight: float        # 0.20

    def to_snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict for storage in score_weights_snapshot."""
        return {
            "version": self.version,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "lead_type": "unified",
            "roof_condition_weights": self.roof_condition_weights.to_dict(),
            "market_quality_weights": self.market_quality_weights.to_dict(),
            "risk_exposure_weights": self.risk_exposure_weights.to_dict(),
            "canvass_efficiency_weights": self.canvass_efficiency_weights.to_dict(),
            "composite_weights": {
                "roof_condition": self.composite_weights.roof_condition,
                "market_quality": self.composite_weights.market_quality,
                "risk_exposure": self.composite_weights.risk_exposure,
                "canvass_efficiency": self.composite_weights.canvass_efficiency,
            },
            "base_weight_with_storm": self.base_weight_with_storm,
            "storm_boost_weight": self.storm_boost_weight,
        }


UNIFIED_MODEL_VERSION = UnifiedModelVersion(
    version="11.0.0",
    description=(
        "Unified roofing lead intelligence model with 4 base sub-scores "
        "(roof_condition, market_quality, risk_exposure, canvass_efficiency) "
        "plus optional storm boost. Replaces dual storm/roof_age engine design."
    ),
    created_at=datetime(2026, 2, 23, 0, 0, 0),

    # roof_condition: How degraded/aged the roof is likely to be
    # Feature weights sum to 1.0
    roof_condition_weights=UnifiedSubScoreWeights(weights={
        "roof_age":           0.35,
        "climate_weathering": 0.20,
        "pre1980_housing":    0.15,
        "age_clustering":     0.10,
        "canopy_risk":        0.10,
        "svi_vulnerability":  0.10,
    }),

    # market_quality: Financial accessibility and investment attractiveness
    # Feature weights sum to 1.0
    market_quality_weights=UnifiedSubScoreWeights(weights={
        "owner_occupied":     0.20,
        "income":             0.18,
        "home_value":         0.15,
        "market_activity":    0.11,
        "hpi_appreciation":   0.10,
        "low_cost_burden":    0.10,
        "low_vacancy":        0.08,
        "single_family":      0.08,
    }),

    # risk_exposure: Environmental and structural damage vulnerability
    # Feature weights sum to 1.0
    risk_exposure_weights=UnifiedSubScoreWeights(weights={
        "hail_exposure":      0.20,
        "fema_risk":          0.20,
        "verified_damage":    0.20,
        "canopy_risk":        0.15,
        "climate_weathering": 0.15,
        "svi_vulnerability":  0.10,
    }),

    # canvass_efficiency: How productive a canvassing run will be
    # Feature weights sum to 1.0
    canvass_efficiency_weights=UnifiedSubScoreWeights(weights={
        "density":            0.60,
        "single_family":      0.25,
        "market_activity":    0.15,
    }),

    # How the 4 sub-scores combine into base_score
    composite_weights=UnifiedCompositeWeights(
        roof_condition=0.35,
        market_quality=0.30,
        risk_exposure=0.20,
        canvass_efficiency=0.15,
    ),

    # Storm blend: composite = base_score * 0.80 + storm_boost * 0.20
    base_weight_with_storm=0.80,
    storm_boost_weight=0.20,
)
