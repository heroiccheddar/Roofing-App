"""Pin photo schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PinPhotoResponse(BaseModel):
    id: UUID
    lead_pin_id: UUID
    roofer_account_id: UUID
    url: str = Field(..., description="Public S3 URL")
    original_filename: str
    file_size_bytes: int
    content_type: str
    created_at: datetime


class PinPhotoListResponse(BaseModel):
    photos: list[PinPhotoResponse]
    count: int
