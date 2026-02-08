"""Feedback and analytics schemas for canvassing sessions.

Handles tiered feedback submission (required/encouraged/detailed),
updates, history, and personal performance analytics.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict


class FeedbackCreate(BaseModel):
    """Request schema for creating canvass session feedback."""

    # Tier 1: Required (star rating)
    rating: int = Field(..., ge=1, le=5, description="Zone quality rating (1-5 stars)")

    # Tier 2: Encouraged (basic metrics)
    doors_knocked: int | None = Field(None, ge=0, description="Number of doors knocked")
    doors_answered: int | None = Field(None, ge=0, description="Number of doors answered")
    visible_damage_count: int | None = Field(
        None, ge=0, description="Count of homes with visible damage"
    )
    homeowner_interested: int | None = Field(
        None, ge=0, description="Count of interested homeowners"
    )

    # Tier 3: Detailed (business outcomes)
    inspections_scheduled: int | None = Field(
        None, ge=0, description="Number of inspections scheduled"
    )
    contracts_signed: int | None = Field(
        None, ge=0, description="Number of contracts signed"
    )
    estimated_revenue: float | None = Field(
        None, ge=0, description="Estimated revenue from this session"
    )
    roof_type: str | None = Field(
        None, description="Predominant roof type (e.g., 'asphalt', '3-tab', 'architectural')"
    )
    competitor_presence: str | None = Field(
        None, description="Competitor saturation: 'none', 'low', 'medium', 'high'"
    )

    # Additional context
    notes: str | None = Field(None, description="Free-form notes about the session")

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: int) -> int:
        """Ensure rating is between 1 and 5."""
        if v < 1 or v > 5:
            raise ValueError("rating must be between 1 and 5")
        return v

    @field_validator("competitor_presence")
    @classmethod
    def validate_competitor_presence(cls, v: str | None) -> str | None:
        """Ensure competitor_presence is valid if provided."""
        if v is not None:
            valid_options = {"none", "low", "medium", "high"}
            if v not in valid_options:
                raise ValueError(
                    f"competitor_presence must be one of: {valid_options}, got '{v}'"
                )
        return v


class FeedbackUpdate(BaseModel):
    """Request schema for updating existing feedback (partial updates)."""

    # All fields optional for partial updates
    rating: int | None = Field(None, ge=1, le=5, description="Zone quality rating (1-5 stars)")

    # Tier 2
    doors_knocked: int | None = Field(None, ge=0, description="Number of doors knocked")
    doors_answered: int | None = Field(None, ge=0, description="Number of doors answered")
    visible_damage_count: int | None = Field(
        None, ge=0, description="Count of homes with visible damage"
    )
    homeowner_interested: int | None = Field(
        None, ge=0, description="Count of interested homeowners"
    )

    # Tier 3
    inspections_scheduled: int | None = Field(
        None, ge=0, description="Number of inspections scheduled"
    )
    contracts_signed: int | None = Field(
        None, ge=0, description="Number of contracts signed"
    )
    estimated_revenue: float | None = Field(
        None, ge=0, description="Estimated revenue from this session"
    )
    roof_type: str | None = Field(
        None, description="Predominant roof type"
    )
    competitor_presence: str | None = Field(
        None, description="Competitor saturation: 'none', 'low', 'medium', 'high'"
    )

    notes: str | None = Field(None, description="Free-form notes")

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: int | None) -> int | None:
        """Ensure rating is valid if provided."""
        if v is not None and (v < 1 or v > 5):
            raise ValueError("rating must be between 1 and 5")
        return v

    @field_validator("competitor_presence")
    @classmethod
    def validate_competitor_presence(cls, v: str | None) -> str | None:
        """Ensure competitor_presence is valid if provided."""
        if v is not None:
            valid_options = {"none", "low", "medium", "high"}
            if v not in valid_options:
                raise ValueError(
                    f"competitor_presence must be one of: {valid_options}, got '{v}'"
                )
        return v


class FeedbackResponse(BaseModel):
    """Response schema for feedback/canvass session."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Session ID")
    lead_zone_id: UUID = Field(..., description="Zone ID this feedback is for")

    # Tier 1
    rating: int = Field(..., description="Zone quality rating (1-5 stars)")

    # Tier 2
    doors_knocked: int | None = Field(None, description="Number of doors knocked")
    doors_answered: int | None = Field(None, description="Number of doors answered")
    visible_damage_count: int | None = Field(
        None, description="Count of homes with visible damage"
    )
    homeowner_interested: int | None = Field(
        None, description="Count of interested homeowners"
    )

    # Tier 3
    inspections_scheduled: int | None = Field(
        None, description="Number of inspections scheduled"
    )
    contracts_signed: int | None = Field(
        None, description="Number of contracts signed"
    )
    estimated_revenue: float | None = Field(
        None, description="Estimated revenue from this session"
    )
    roof_type: str | None = Field(None, description="Predominant roof type")
    competitor_presence: str | None = Field(
        None, description="Competitor saturation level"
    )

    notes: str | None = Field(None, description="Free-form notes")
    zone_score_at_time: float | None = Field(
        None, description="Zone score when feedback was submitted"
    )

    # Timestamps
    created_at: datetime = Field(..., description="Feedback creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class FeedbackHistoryResponse(BaseModel):
    """Paginated response for feedback history."""

    sessions: list[FeedbackResponse] = Field(
        default_factory=list, description="List of canvass sessions"
    )
    total: int = Field(..., description="Total sessions for this roofer")


class ConversionByBand(BaseModel):
    """Conversion rate breakdown by score band."""

    hot: float | None = Field(None, description="Conversion rate for 'hot' zones")
    warm: float | None = Field(None, description="Conversion rate for 'warm' zones")
    cool: float | None = Field(None, description="Conversion rate for 'cool' zones")


class ConversionOverTime(BaseModel):
    """Time-series conversion data point."""

    date: str = Field(..., description="Date (YYYY-MM-DD)")
    conversion_rate: float = Field(..., description="Conversion rate on that date")
    zones_canvassed: int = Field(..., description="Number of zones canvassed")


class PerformanceAnalytics(BaseModel):
    """Personal performance analytics dashboard."""

    total_zones_canvassed: int = Field(..., description="Total zones canvassed")
    avg_conversion_rate: float = Field(
        ..., description="Average conversion rate across all zones"
    )
    best_score_band: str | None = Field(
        None, description="Score band with best conversion rate"
    )
    best_hail_range: str | None = Field(
        None, description="Hail size range with best conversion rate"
    )
    revenue_per_trip: float = Field(
        ..., description="Average revenue per canvassing session"
    )
    conversion_by_band: ConversionByBand = Field(
        ..., description="Conversion rates broken down by score band"
    )
    conversion_over_time: list[ConversionOverTime] = Field(
        default_factory=list, description="Time-series conversion trend"
    )
