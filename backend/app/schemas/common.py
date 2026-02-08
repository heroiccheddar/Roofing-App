"""Common schemas used across API endpoints.

Provides reusable base models for pagination, error responses,
and other shared structures.
"""

from pydantic import BaseModel, Field, field_validator


class PaginationParams(BaseModel):
    """Base model for pagination query parameters."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")

    @field_validator("page")
    @classmethod
    def validate_page(cls, v: int) -> int:
        """Ensure page is at least 1."""
        if v < 1:
            raise ValueError("page must be >= 1")
        return v

    @field_validator("page_size")
    @classmethod
    def validate_page_size(cls, v: int) -> int:
        """Ensure page_size is reasonable."""
        if v < 1 or v > 100:
            raise ValueError("page_size must be between 1 and 100")
        return v


class ErrorResponse(BaseModel):
    """Standard error response structure."""

    detail: str = Field(..., description="Human-readable error message")
    code: str | None = Field(None, description="Machine-readable error code")
