"""Account management schemas.

Handles service area updates, alert preferences, and account profile.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict


class ServiceAreaUpdate(BaseModel):
    """Request schema for updating service area."""

    lat: float = Field(..., ge=-90, le=90, description="Service area center latitude")
    lon: float = Field(..., ge=-180, le=180, description="Service area center longitude")
    radius_km: float = Field(
        ..., gt=0, le=500, description="Service area radius in kilometers"
    )


class QuietHours(BaseModel):
    """Quiet hours configuration for alerts."""

    start: str = Field(
        ...,
        pattern=r"^([01]\d|2[0-3]):([0-5]\d)$",
        description="Start time in HH:MM format (24-hour)",
    )
    end: str = Field(
        ...,
        pattern=r"^([01]\d|2[0-3]):([0-5]\d)$",
        description="End time in HH:MM format (24-hour)",
    )


class AlertPreferences(BaseModel):
    """Alert preferences configuration."""

    min_score: float = Field(
        default=70.0,
        ge=0,
        le=100,
        description="Minimum composite score to trigger alerts (0-100)",
    )
    min_hail_inches: float = Field(
        default=1.0, ge=0, description="Minimum hail diameter to trigger alerts (inches)"
    )
    channels: list[str] = Field(
        default_factory=lambda: ["email"],
        description="Alert channels: 'email', 'sms', 'push'",
    )
    quiet_hours: QuietHours | None = Field(
        None, description="Optional quiet hours when no alerts are sent"
    )

    @field_validator("channels")
    @classmethod
    def validate_channels(cls, v: list[str]) -> list[str]:
        """Ensure all channels are valid."""
        valid_channels = {"email", "sms", "push"}
        invalid = [ch for ch in v if ch not in valid_channels]
        if invalid:
            raise ValueError(
                f"Invalid channels: {invalid}. Must be one of: {valid_channels}"
            )
        return v

    @field_validator("min_score")
    @classmethod
    def validate_min_score(cls, v: float) -> float:
        """Ensure min_score is within valid range."""
        if v < 0 or v > 100:
            raise ValueError("min_score must be between 0 and 100")
        return v


class AccountResponse(BaseModel):
    """Response schema for account profile."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Account ID")
    email: str = Field(..., description="Email address")
    company_name: str = Field(..., description="Company name")
    phone_number: str | None = Field(None, description="Phone number")
    subscription_tier: str = Field(..., description="Subscription tier: 'free' or 'pro'")
    alert_preferences: dict = Field(
        default_factory=dict, description="Alert preferences JSON"
    )
    is_admin: bool = Field(..., description="Admin flag")
    created_at: datetime = Field(..., description="Account creation timestamp")
