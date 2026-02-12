"""Zone feedback model for POC field validation.

Simplified feedback system replacing complex canvass_session model.
Captures basic field observations after canvassing a zone.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Float,
    DateTime,
    Integer,
    Boolean,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class ZoneFeedback(Base):
    """Field feedback submitted by roofer after canvassing a zone."""

    __tablename__ = "zone_feedback"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    lead_zone_id = Column(
        UUID(as_uuid=True),
        ForeignKey("lead_zones.id"),
        nullable=False,
    )
    roofer_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("roofer_accounts.id"),
        nullable=False,
    )

    # Feedback data
    rating = Column(Integer, nullable=False)  # 1-5 stars
    visible_damage = Column(Boolean, nullable=True)
    notes = Column(String, nullable=True)

    # Snapshot of zone score at feedback time
    zone_score_at_feedback = Column(Float, nullable=True)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    lead_zone = relationship("LeadZone", back_populates="zone_feedbacks")
    roofer_account = relationship("RooferAccount", back_populates="zone_feedbacks")

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            'lead_zone_id',
            'roofer_account_id',
            name='uq_zone_feedback_zone_roofer'
        ),
    )

    def __repr__(self):
        return f"<ZoneFeedback(id={self.id}, zone_id={self.lead_zone_id}, rating={self.rating})>"
