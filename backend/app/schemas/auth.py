"""Authentication schemas for registration and login.

Handles account creation with service area definition and
JWT token issuance.
"""

from pydantic import BaseModel, Field, EmailStr, field_validator


class AuthRegister(BaseModel):
    """Request schema for user registration."""

    email: EmailStr = Field(..., description="Roofer's email address")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")
    company_name: str = Field(..., min_length=1, description="Roofing company name")
    phone_number: str | None = Field(None, description="Contact phone number")

    service_area_lat: float = Field(
        ..., ge=-90, le=90, description="Service area center latitude"
    )
    service_area_lon: float = Field(
        ..., ge=-180, le=180, description="Service area center longitude"
    )
    service_area_radius_km: float = Field(
        ..., gt=0, le=500, description="Service area radius in kilometers"
    )

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Ensure password meets minimum security requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("company_name")
    @classmethod
    def validate_company_name(cls, v: str) -> str:
        """Ensure company name is not empty."""
        if not v.strip():
            raise ValueError("Company name cannot be empty")
        return v.strip()


class AuthLogin(BaseModel):
    """Request schema for user login."""

    email: EmailStr = Field(..., description="Roofer's email address")
    password: str = Field(..., description="Password")


class TokenResponse(BaseModel):
    """Response schema for authentication tokens."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type (always 'bearer')")
