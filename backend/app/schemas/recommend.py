"""Pydantic schemas for the recommendation endpoint.

RecommendedZone represents a scored zone that has been re-ranked for
proximity and freshness relative to the canvasser's current position.
RecommendationResponse is the envelope returned by GET /recommendations.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RecommendedZone(BaseModel):
    """A lead zone ranked by the recommendation engine.

    recommendation_score blends composite_score, proximity, zone freshness,
    and storm activity. reason is a human-readable explanation of the
    top factors that drove this zone to the top of the list.
    """

    zone_id: UUID
    h3_index: str
    display_name: str | None = None
    composite_score: float
    recommendation_score: float
    distance_km: float
    last_canvassed_at: datetime | None = None
    has_active_storm: bool = False
    storm_boost: float | None = None
    centroid_lat: float
    centroid_lon: float
    score_band: str
    reason: str


class RecommendationResponse(BaseModel):
    """Envelope returned by GET /recommendations."""

    zones: list[RecommendedZone] = Field(default_factory=list)
    generated_at: datetime
