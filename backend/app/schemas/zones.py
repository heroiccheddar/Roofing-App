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
