"""Pin photo model for S3-stored photos on lead pins."""

import uuid

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class PinPhoto(Base):
    __tablename__ = "pin_photos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_pin_id = Column(
        UUID(as_uuid=True),
        ForeignKey("lead_pins.id", ondelete="CASCADE"),
        nullable=False,
    )
    roofer_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("roofer_accounts.id"),
        nullable=False,
    )
    s3_key = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    content_type = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    lead_pin = relationship("LeadPin")
    roofer_account = relationship("RooferAccount")

    __table_args__ = (
        Index("ix_pin_photos_lead_pin_id", "lead_pin_id"),
    )
