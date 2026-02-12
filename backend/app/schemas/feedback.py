"""Zone feedback schemas for POC field validation."""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class ZoneFeedbackCreate(BaseModel):
    """Submit feedback for a zone after canvassing."""
    rating: int = Field(..., ge=1, le=5, description="Zone quality rating (1-5 stars)")
    visible_damage: bool | None = Field(None, description="Was visible roof damage observed?")
    notes: str | None = Field(None, max_length=1000, description="Free-form field notes")


class ZoneFeedbackResponse(BaseModel):
    """Response schema for zone feedback."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lead_zone_id: UUID
    roofer_account_id: UUID
    rating: int
    visible_damage: bool | None
    notes: str | None
    zone_score_at_feedback: float | None
    created_at: datetime


class ZoneFeedbackListResponse(BaseModel):
    """Paginated feedback list."""
    feedbacks: list[ZoneFeedbackResponse] = Field(default_factory=list)
    total: int
