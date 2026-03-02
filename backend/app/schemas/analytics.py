"""Pydantic response schemas for the analytics dashboard endpoint."""

from pydantic import BaseModel, Field


class AnalyticsSummary(BaseModel):
    """Aggregate performance metrics for the selected period."""

    total_pins: int = Field(..., description="Total pins dropped in the period")
    contracts_signed: int = Field(..., description="Pins with disposition contract_signed")
    conversion_rate: float = Field(
        ..., description="contracts_signed / total_pins (0.0 if no pins)"
    )
    callbacks_pending: int = Field(
        ..., description="Pins with disposition callback"
    )
    inspections_set: int = Field(
        ..., description="Pins with disposition inspection_set"
    )
    avg_pins_per_day: float = Field(
        ..., description="total_pins divided by elapsed calendar days in period"
    )


class DailyActivityPoint(BaseModel):
    """Pin and contract counts for a single calendar day.

    Used to populate time-series bar charts on the dashboard. Days with zero
    activity are included so the chart has no gaps.
    """

    date: str = Field(..., description="ISO 8601 date string (YYYY-MM-DD)")
    pins_created: int = Field(..., description="Pins dropped on this date")
    contracts_signed: int = Field(
        ..., description="Pins marked contract_signed on this date"
    )


class FunnelStage(BaseModel):
    """One stage in the sales funnel, ordered from top to bottom."""

    stage: str = Field(..., description="Human-readable stage label")
    count: int = Field(..., description="Number of pins at this stage in the period")


class SourceBreakdown(BaseModel):
    """Pin count for a single lead source value."""

    source: str = Field(..., description="Lead source value (or 'unknown' if unset)")
    count: int = Field(..., description="Number of pins with this lead source")


class AnalyticsDashboardResponse(BaseModel):
    """Full analytics dashboard payload returned by GET /analytics/dashboard."""

    period: str = Field(..., description="The requested period value (e.g. this_week)")
    summary: AnalyticsSummary
    daily_activity: list[DailyActivityPoint] = Field(
        ..., description="Per-day activity ordered chronologically, gaps filled with zeros"
    )
    funnel: list[FunnelStage] = Field(
        ..., description="Sales funnel stages ordered from broadest to narrowest"
    )
    source_breakdown: list[SourceBreakdown] = Field(
        ..., description="Pin counts grouped by lead source, ordered by count descending"
    )
