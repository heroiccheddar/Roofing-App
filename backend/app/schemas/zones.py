"""Lead zone schemas for listing, detail, and GeoJSON responses.

Provides schemas for zone queries, scoring details, and geospatial data.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict


class ZoneListParams(BaseModel):
    """Query parameters for zone listing."""

    min_score: float | None = Field(
        None, ge=0, le=100, description="Minimum composite score filter"
    )
    hail_min: float | None = Field(
        None, ge=0, description="Minimum hail diameter filter (inches)"
    )
    lead_type: str | None = Field(None, description="Filter by lead type: 'storm' or 'roof_age'")
    sort_by: str = Field(
        default="score",
        description="Sort field: 'score', 'time', 'hail'",
    )
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")

    @field_validator("sort_by")
    @classmethod
    def validate_sort_by(cls, v: str) -> str:
        """Ensure sort_by is valid."""
        valid_options = {"score", "time", "hail"}
        if v not in valid_options:
            raise ValueError(
                f"sort_by must be one of: {valid_options}, got '{v}'"
            )
        return v


class StormEventBrief(BaseModel):
    """Brief storm event data for zone detail."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Event ID")
    source: str = Field(..., description="Data source: 'nws', 'spc', 'swdi'")
    event_type: str = Field(..., description="Event type: 'hail', 'wind', 'tornado'")
    hail_diameter: float | None = Field(None, description="Hail diameter (inches)")
    wind_speed: float | None = Field(None, description="Wind speed (mph)")
    event_timestamp: datetime = Field(..., description="Event occurrence time")
    radar_confidence: float | None = Field(
        None, description="Radar confidence score (0.0-1.0)"
    )


class ZoneResponse(BaseModel):
    """Response schema for zone listing item."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Zone ID")
    h3_index: str = Field(..., description="H3 hexagon index")
    lead_type: str = Field(default="storm", description="Lead type: 'storm' or 'roof_age'")

    # Scoring components
    composite_score: float = Field(..., description="Final composite score (0-100)")
    damage_prob: float = Field(..., description="Damage probability sub-score")
    lead_quality: float = Field(..., description="Lead quality sub-score")
    density_bonus: float = Field(..., description="Density bonus sub-score")
    predicted_conversion_rate: float | None = Field(
        None, description="Predicted conversion rate"
    )

    # Score classification
    score_band: str = Field(
        ..., description="Score band: 'hot', 'warm', 'cool', 'skip'"
    )
    model_version: str = Field(..., description="Model version used for scoring")

    # Event aggregation
    event_count: int = Field(..., description="Number of contributing storm events")
    max_hail_diameter: float | None = Field(None, description="Largest hail size (inches)")
    max_wind_speed: float | None = Field(None, description="Peak wind speed (mph)")
    primary_event_timestamp: datetime | None = Field(
        None, description="Most recent event timestamp"
    )

    # Zone lifecycle
    expires_at: datetime = Field(..., description="Zone expiration timestamp")

    # Geospatial
    centroid_lat: float = Field(..., description="Zone centroid latitude")
    centroid_lon: float = Field(..., description="Zone centroid longitude")

    # Timestamps
    created_at: datetime = Field(..., description="Zone creation timestamp")


class ZoneDetailResponse(ZoneResponse):
    """Extended response schema for zone detail page."""

    decay_adjusted_score: float = Field(
        ..., description="Score adjusted for time decay"
    )
    hours_since_storm: float = Field(
        ..., description="Hours elapsed since primary event"
    )
    events: list[StormEventBrief] = Field(
        default_factory=list, description="Contributing storm events"
    )
    avg_roof_age_years: float | None = Field(
        None, description="Average roof age in years (from census median_year_built)"
    )
    avg_median_income: float | None = Field(
        None, description="Area-weighted median household income"
    )
    avg_vacancy_rate: float | None = Field(
        None, description="Area-weighted vacancy rate %"
    )
    avg_single_family_pct: float | None = Field(
        None, description="Area-weighted single-family housing %"
    )
    avg_pct_built_before_1980: float | None = Field(
        None, description="Area-weighted % homes built before 1980"
    )
    nri_hail_risk: str | None = Field(
        None, description="FEMA NRI hail risk rating"
    )
    nri_wind_risk: str | None = Field(
        None, description="FEMA NRI wind risk rating"
    )
    nri_tornado_risk: str | None = Field(
        None, description="FEMA NRI tornado risk rating"
    )
    total_building_count: int | None = Field(
        None, description="Building footprint count in zone area"
    )
    avg_building_area_sqm: float | None = Field(
        None, description="Average building footprint area (sq m)"
    )
    hail_exposure_score: float | None = Field(
        None, description="Historical hail exposure score (0-100)"
    )
    hail_events_3yr: int | None = Field(
        None, description="MESH radar hail observations in last 3 years"
    )
    fema_disaster_count: int | None = Field(
        None, description="FEMA disaster declarations in area"
    )
    fema_disaster_score: float | None = Field(
        None, description="FEMA disaster recency-weighted score (0-100)"
    )
    tree_canopy_mean_pct: float | None = Field(
        None, description="Average tree canopy coverage % (0-100)"
    )
    tree_canopy_risk_score: float | None = Field(
        None, description="Tree canopy risk score (0-100)"
    )
    dominant_decade: str | None = Field(None, description="Most common housing decade (e.g., '1990s')")
    age_clustering_score: float | None = Field(None, description="Age clustering HHI score (0-100)")
    pct_cost_burdened: float | None = Field(None, description="% spending 30%+ of income on housing")
    hpi_5yr_change: float | None = Field(None, description="5-year home price index % change")
    verified_damage_5yr_usd: float | None = Field(None, description="Verified property damage $ (5yr)")
    climate_weathering_score: float | None = Field(None, description="Climate weathering index (0-100)")
    svi_overall: float | None = Field(None, description="CDC SVI overall vulnerability (0-1)")
    svi_housing_type: float | None = Field(None, description="CDC SVI housing type/transport (0-1)")
    ruca_category: str | None = Field(None, description="USDA RUCA classification: urban, large_rural, small_town, isolated_rural")
    bps_single_family_permits: int | None = Field(None, description="Annual single-family building permits (county-level)")
    bps_all_permits: int | None = Field(None, description="Annual total building permits (county-level)")
    bps_total_value: float | None = Field(None, description="Annual total construction value ($)")
    ej_lead_paint: float | None = Field(None, description="EPA EJSCREEN: % pre-1960 housing (lead paint proxy)")
    ej_percentile: float | None = Field(None, description="EPA EJSCREEN: overall EJ index percentile (0-100)")
    flood_risk_category: str | None = Field(None, description="FEMA flood risk: high, moderate, low, minimal")
    flood_insurance_required: bool | None = Field(None, description="Whether NFIP flood insurance is mandatory")
    redfin_median_sale_price: float | None = Field(None, description="Redfin median sale price ($)")
    redfin_median_dom: float | None = Field(None, description="Redfin median days on market")
    redfin_price_drop_pct: float | None = Field(None, description="% of listings with price drops")


class ZoneListResponse(BaseModel):
    """Paginated response for zone listing."""

    zones: list[ZoneResponse] = Field(..., description="List of zones")
    total: int = Field(..., description="Total zones matching filters")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")


class GeoJSONGeometry(BaseModel):
    """GeoJSON geometry object."""

    type: str = Field(..., description="Geometry type (Polygon)")
    coordinates: list[list[list[float]]] = Field(
        ..., description="Polygon coordinates [[[lon, lat], ...]]"
    )


class ZoneGeoJSONFeature(BaseModel):
    """GeoJSON Feature for a single zone."""

    type: str = Field(default="Feature", description="GeoJSON type")
    geometry: GeoJSONGeometry = Field(..., description="Polygon geometry")
    properties: dict = Field(
        ...,
        description="Zone properties (score, band, hail, wind, h3_index, id, etc.)",
    )


class ZoneGeoJSONResponse(BaseModel):
    """GeoJSON FeatureCollection for map rendering."""

    type: str = Field(default="FeatureCollection", description="GeoJSON type")
    features: list[ZoneGeoJSONFeature] = Field(
        default_factory=list, description="List of zone features"
    )
