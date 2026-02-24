"""Canvass session model for roofer feedback.

Tracks individual canvassing sessions where roofers provide ground-truth
feedback about actual damage rates in lead zones. Uses progressive disclosure
with Tier 1 (required), Tier 2 (encouraged), and Tier 3 (detailed) fields.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Float,
    Integer,
    ForeignKey,
    Text,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class CanvassSession(Base):
    """Roofer canvassing session with damage feedback."""

    __tablename__ = "canvass_sessions"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    lead_zone_id = Column(
        UUID(as_uuid=True), ForeignKey('lead_zones.id'), nullable=False
    )
    roofer_account_id = Column(
        UUID(as_uuid=True), ForeignKey('roofer_accounts.id'), nullable=False
    )

    # Tier 1: Required feedback (star rating)
    rating = Column(Integer, nullable=True)  # 1-5 stars, set when session ends

    # Tier 2: Encouraged feedback (basic metrics)
    doors_knocked = Column(Integer, nullable=True)
    doors_answered = Column(Integer, nullable=True)
    visible_damage_count = Column(Integer, nullable=True)
    homeowner_interested = Column(Integer, nullable=True)

    # Tier 3: Detailed feedback (business outcomes)
    inspections_scheduled = Column(Integer, nullable=True)
    contracts_signed = Column(Integer, nullable=True)
    estimated_revenue = Column(Float, nullable=True)
    roof_type = Column(String, nullable=True)  # e.g., 'asphalt', '3-tab', 'architectural'
    competitor_presence = Column(
        String, nullable=True
    )  # 'none', 'low', 'medium', 'high'

    # Additional context
    notes = Column(Text, nullable=True)
    zone_score_at_time = Column(
        Float, nullable=True
    )  # Snapshot of zone score when feedback submitted

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    lead_zone = relationship("LeadZone", back_populates="canvass_sessions")
    roofer_account = relationship("RooferAccount", back_populates="canvass_sessions")

    __table_args__ = (
        # Index on lead_zone_id for zone-based queries
        Index('ix_canvass_sessions_lead_zone_id', 'lead_zone_id'),
        # Index on roofer_account_id for roofer-based queries
        Index('ix_canvass_sessions_roofer_account_id', 'roofer_account_id'),
        # Index on created_at for time-based queries
        Index('ix_canvass_sessions_created_at', 'created_at'),
        # Index on rating for filtering high/low ratings
        Index('ix_canvass_sessions_rating', 'rating'),
    )

    def __repr__(self):
        return f"<CanvassSession(id={self.id}, zone={self.lead_zone_id}, rating={self.rating})>"
