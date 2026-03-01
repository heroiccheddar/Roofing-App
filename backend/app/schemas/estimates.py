"""Estimate schemas for the Estimate Builder feature.

Provides request/response schemas for the /estimates API endpoints.
Line items are represented as typed Pydantic models and stored as JSONB
in the database — conversion is transparent via from_attributes mode.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

VALID_ESTIMATE_STATUSES = {"draft", "sent", "accepted", "declined"}


# ---------------------------------------------------------------------------
# Nested schemas
# ---------------------------------------------------------------------------


class LineItem(BaseModel):
    """A single line item within an estimate."""

    description: str = Field(..., description="Description of the work or material")
    quantity: float = Field(..., gt=0, description="Number of units")
    unit: str = Field(..., description="Unit of measure (e.g. 'sq ft', 'each', 'hr')")
    unit_price: float = Field(..., ge=0, description="Price per unit in dollars")
    total: float = Field(..., ge=0, description="Line item total (quantity * unit_price)")


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class EstimateCreate(BaseModel):
    """Body for POST /estimates — create a new estimate for a lead pin."""

    lead_pin_id: UUID = Field(..., description="Lead pin this estimate is attached to")
    line_items: list[LineItem] = Field(
        ..., min_length=1, description="One or more itemized cost rows"
    )
    tax_rate: float = Field(
        default=0,
        ge=0,
        le=1,
        description="Tax rate as a decimal fraction (e.g. 0.0825 = 8.25%)",
    )
    notes: str | None = Field(None, description="Optional notes to include on the estimate")
    status: str = Field(default="draft", description="Estimate lifecycle status")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Ensure status is one of the four permitted values."""
        if v not in VALID_ESTIMATE_STATUSES:
            raise ValueError(
                f"status must be one of: {sorted(VALID_ESTIMATE_STATUSES)}, got '{v}'"
            )
        return v


class EstimateUpdate(BaseModel):
    """Body for PUT /estimates/{estimate_id} — partial update of an estimate."""

    line_items: list[LineItem] | None = Field(
        None, description="Replacement line items (replaces all existing items)"
    )
    tax_rate: float | None = Field(
        None,
        ge=0,
        le=1,
        description="Updated tax rate as a decimal fraction",
    )
    notes: str | None = Field(None, description="Updated estimate notes")
    status: str | None = Field(None, description="Updated lifecycle status")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        """Ensure status, if provided, is one of the four permitted values."""
        if v is not None and v not in VALID_ESTIMATE_STATUSES:
            raise ValueError(
                f"status must be one of: {sorted(VALID_ESTIMATE_STATUSES)}, got '{v}'"
            )
        return v


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class EstimateResponse(BaseModel):
    """Full estimate response including computed totals."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Estimate UUID")
    lead_pin_id: UUID = Field(..., description="Lead pin this estimate belongs to")
    roofer_account_id: UUID = Field(..., description="Owning roofer account ID")

    line_items: list[LineItem] = Field(..., description="Itemized cost rows")

    subtotal: float = Field(..., description="Sum of all line item totals before tax")
    tax_rate: float = Field(
        ..., description="Tax rate applied as a decimal fraction (e.g. 0.0825)"
    )
    total: float = Field(..., description="subtotal * (1 + tax_rate)")

    status: str = Field(..., description="Estimate lifecycle status")
    notes: str | None = Field(None, description="Optional estimate notes")

    created_at: datetime = Field(..., description="Estimate creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class EstimateListResponse(BaseModel):
    """List of estimates with total count."""

    estimates: list[EstimateResponse] = Field(..., description="Estimates for the user")
    total: int = Field(..., description="Total estimates matching filters")
