"""Lead pin and pin activity schemas for address-level sales tracking.

Provides request/response schemas for the /leads API endpoints.
Geometry (POINT) is exposed as separate lat/lon floats — conversion
from PostGIS format happens in the API layer.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict


# ---------------------------------------------------------------------------
# Disposition constants
# ---------------------------------------------------------------------------

VALID_DISPOSITIONS = {
    "not_home",
    "callback",
    "interested",
    "inspection_set",
    "contract_signed",
    "not_interested",
}


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class LeadPinCreate(BaseModel):
    """Body for POST /leads — create a new pin at a specific address."""

    lat: float = Field(..., ge=-90, le=90, description="Latitude (WGS 84)")
    lon: float = Field(..., ge=-180, le=180, description="Longitude (WGS 84)")
    disposition: str = Field(..., description="Initial sales funnel status")
    address: str | None = Field(None, description="Street address label for the pin")
    notes: str | None = Field(
        None, max_length=1000, description="Free-form notes on this interaction"
    )
    property_id: str | None = Field(
        None, description="Optional FK to a cached property record"
    )
    lead_zone_id: str | None = Field(
        None, description="Optional FK to the lead zone this pin falls within"
    )
    callback_date: datetime | None = Field(None, description="Scheduled follow-up date")
    contact_name: str | None = Field(None, max_length=200, description="Homeowner name")
    contact_phone: str | None = Field(None, max_length=30, description="Homeowner phone")
    contact_email: str | None = Field(None, max_length=254, description="Homeowner email")
    estimated_value: float | None = Field(None, description="Estimated deal value")

    @field_validator("disposition")
    @classmethod
    def validate_disposition(cls, v: str) -> str:
        """Ensure disposition is one of the six permitted values."""
        if v not in VALID_DISPOSITIONS:
            raise ValueError(
                f"disposition must be one of: {sorted(VALID_DISPOSITIONS)}, got '{v}'"
            )
        return v


class LeadPinUpdate(BaseModel):
    """Body for PUT /leads/{pin_id} — update disposition or notes."""

    disposition: str | None = Field(None, description="New sales funnel status")
    notes: str | None = Field(
        None, max_length=1000, description="Updated notes on the current status"
    )
    callback_date: datetime | None = Field(None, description="Reschedule follow-up")
    contact_name: str | None = Field(None, max_length=200, description="Homeowner name")
    contact_phone: str | None = Field(None, max_length=30, description="Homeowner phone")
    contact_email: str | None = Field(None, max_length=254, description="Homeowner email")
    estimated_value: float | None = Field(None, description="Estimated deal value")

    @field_validator("disposition")
    @classmethod
    def validate_disposition(cls, v: str | None) -> str | None:
        """Ensure disposition, if provided, is one of the six permitted values."""
        if v is not None and v not in VALID_DISPOSITIONS:
            raise ValueError(
                f"disposition must be one of: {sorted(VALID_DISPOSITIONS)}, got '{v}'"
            )
        return v


class PinActivityCreate(BaseModel):
    """Body for POST /leads/{pin_id}/activities — log a communication log entry."""

    notes: str = Field(..., min_length=1, max_length=1000, description="Visit note")
    activity_type: str = Field(default="note", description="Type: call, text, email, visit, note")

    @field_validator("activity_type")
    @classmethod
    def validate_activity_type(cls, v: str) -> str:
        valid = {"call", "text", "email", "visit", "note"}
        if v not in valid:
            raise ValueError(f"activity_type must be one of: {sorted(valid)}, got '{v}'")
        return v


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class LeadPinResponse(BaseModel):
    """Full lead pin response. lat/lon are extracted from PostGIS POINT."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Pin UUID")
    roofer_account_id: UUID = Field(..., description="Owning roofer account ID")
    property_id: UUID | None = Field(None, description="Linked property record ID")
    lead_zone_id: UUID | None = Field(None, description="Linked lead zone ID")

    # Coordinates are resolved from PostGIS geometry in the API layer
    lat: float = Field(..., description="Latitude (WGS 84)")
    lon: float = Field(..., description="Longitude (WGS 84)")

    address: str | None = Field(None, description="Street address label")
    disposition: str = Field(..., description="Current sales funnel status")
    notes: str | None = Field(None, description="Current notes")
    callback_date: datetime | None = Field(None, description="Scheduled follow-up date")
    contact_name: str | None = Field(None, description="Homeowner name")
    contact_phone: str | None = Field(None, description="Homeowner phone")
    contact_email: str | None = Field(None, description="Homeowner email")
    estimated_value: float | None = Field(None, description="Estimated deal value")

    created_at: datetime = Field(..., description="Pin creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    roofer_name: str | None = Field(None, description="Rep name (team queries only)")


class LeadPinListResponse(BaseModel):
    """Paginated list of lead pins."""

    pins: list[LeadPinResponse] = Field(..., description="Lead pins for the user")
    total: int = Field(..., description="Total pins matching filters")


class PinActivityResponse(BaseModel):
    """Single activity entry in a pin's interaction history."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Activity UUID")
    lead_pin_id: UUID = Field(..., description="Parent pin ID")
    disposition: str = Field(..., description="Disposition recorded at this interaction")
    activity_type: str = Field(..., description="Activity type: disposition_change, call, text, email, visit, note")
    notes: str | None = Field(None, description="Notes recorded at this interaction")
    created_at: datetime = Field(..., description="Interaction timestamp")


class PinActivityListResponse(BaseModel):
    """Full activity timeline for a lead pin."""

    activities: list[PinActivityResponse] = Field(
        ..., description="Activities ordered newest first"
    )
    total: int = Field(..., description="Total activity count for this pin")


# ---------------------------------------------------------------------------
# GeoJSON schemas (lightweight — for map rendering)
# ---------------------------------------------------------------------------


class LeadPinGeoJSONProperties(BaseModel):
    """Minimal properties included in each GeoJSON feature."""

    id: str = Field(..., description="Pin UUID as string")
    disposition: str = Field(..., description="Current sales funnel status")
    is_own: bool = Field(True, description="Whether this pin belongs to the current user")


class LeadPinGeoJSONFeature(BaseModel):
    """GeoJSON Point feature for a single lead pin."""

    type: str = Field(default="Feature", description="GeoJSON type")
    geometry: dict = Field(
        ..., description="GeoJSON Point geometry: {type, coordinates}"
    )
    properties: LeadPinGeoJSONProperties = Field(..., description="Pin properties")


class LeadPinGeoJSONResponse(BaseModel):
    """GeoJSON FeatureCollection of lead pin points for map rendering."""

    type: str = Field(default="FeatureCollection", description="GeoJSON type")
    features: list[LeadPinGeoJSONFeature] = Field(
        default_factory=list, description="Pin point features"
    )
