"""Canvass session schemas for door knock tracking."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class CanvassSessionCreate(BaseModel):
    """Start a new canvassing session in a zone."""

    notes: str | None = Field(None, max_length=1000)


class CanvassSessionUpdate(BaseModel):
    """Update an active canvassing session with counter data."""

    doors_knocked: int | None = Field(None, ge=0)
    doors_answered: int | None = Field(None, ge=0)
    visible_damage_count: int | None = Field(None, ge=0)
    homeowner_interested: int | None = Field(None, ge=0)
    inspections_scheduled: int | None = Field(None, ge=0)
    contracts_signed: int | None = Field(None, ge=0)
    estimated_revenue: float | None = Field(None, ge=0)
    roof_type: str | None = Field(None, max_length=50)
    competitor_presence: str | None = None
    rating: int | None = Field(None, ge=1, le=5)
    notes: str | None = Field(None, max_length=1000)


class CanvassSessionResponse(BaseModel):
    """Response schema for a canvass session."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lead_zone_id: UUID
    roofer_account_id: UUID
    rating: int | None = None
    doors_knocked: int | None = None
    doors_answered: int | None = None
    visible_damage_count: int | None = None
    homeowner_interested: int | None = None
    inspections_scheduled: int | None = None
    contracts_signed: int | None = None
    estimated_revenue: float | None = None
    roof_type: str | None = None
    competitor_presence: str | None = None
    notes: str | None = None
    zone_score_at_time: float | None = None
    created_at: datetime
    updated_at: datetime


class CanvassSessionListResponse(BaseModel):
    """List of canvass sessions."""

    sessions: list[CanvassSessionResponse] = Field(default_factory=list)
    total: int
