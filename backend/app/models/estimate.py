"""Estimate model for the Estimate Builder feature.

Roofers create itemized estimates against a lead pin, track line items
as JSONB, and manage estimate lifecycle (draft → sent → accepted/declined).
"""

import uuid

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


VALID_STATUSES = {"draft", "sent", "accepted", "declined"}


class Estimate(Base):
    """An itemized cost estimate created by a roofer for a specific lead pin.

    Line items are stored as a JSONB array, each with shape:
      {description: str, quantity: float, unit: str, unit_price: float, total: float}

    subtotal, tax_rate, and total are stored as Numeric for precision.
    status tracks lifecycle: draft → sent → accepted or declined.
    """

    __tablename__ = "estimates"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
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

    # Line items — array of {description, quantity, unit, unit_price, total}
    line_items = Column(JSONB, nullable=False, default=list)

    # Pricing
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    tax_rate = Column(Numeric(5, 4), nullable=False, default=0)  # e.g. 0.0825 = 8.25%
    total = Column(Numeric(12, 2), nullable=False, default=0)

    # Lifecycle status
    status = Column(String, nullable=False, default="draft")

    # Optional notes
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    lead_pin = relationship("LeadPin")
    roofer_account = relationship("RooferAccount")

    __table_args__ = (
        Index("ix_estimates_lead_pin_id", "lead_pin_id"),
        Index("ix_estimates_roofer_account_id", "roofer_account_id"),
    )

    def __repr__(self):
        return (
            f"<Estimate(id={self.id}, status={self.status}, "
            f"total={self.total}, lead_pin_id={self.lead_pin_id})>"
        )
