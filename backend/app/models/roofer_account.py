"""Roofer account model for authentication and subscription.

Represents individual roofer users with authentication credentials,
subscription status, and contact preferences for alerts.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Boolean,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry

from app.database import Base


class RooferAccount(Base):
    """Roofer user account."""

    __tablename__ = "roofer_accounts"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Authentication
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)

    # Profile
    company_name = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)

    # Service area (geographic boundary)
    service_area = Column(Geometry(geometry_type='POLYGON', srid=4326), nullable=False)

    # Alert preferences (JSONB with flexible structure)
    alert_preferences = Column(JSONB, nullable=False, server_default='{}')
    # Example structure: {"email_enabled": true, "sms_enabled": false, "min_score": 70}

    # Subscription
    subscription_tier = Column(String, nullable=False, default='free')  # 'free' or 'pro'

    # Account status
    is_admin = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)

    # Activity tracking
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    canvass_sessions = relationship(
        "CanvassSession", back_populates="roofer_account", lazy="select"
    )
    alert_logs = relationship("AlertLog", back_populates="roofer_account", lazy="select")
    zone_feedbacks = relationship("ZoneFeedback", back_populates="roofer_account", lazy="select")

    __table_args__ = (
        # Spatial index on service_area (GIST)
        Index('ix_roofer_accounts_service_area', 'service_area', postgresql_using='gist'),
        # Index on subscription_tier for tier-based queries
        Index('ix_roofer_accounts_subscription_tier', 'subscription_tier'),
        # Index on is_active for filtering active accounts
        Index('ix_roofer_accounts_is_active', 'is_active'),
    )

    def __repr__(self):
        return f"<RooferAccount(id={self.id}, email={self.email}, company={self.company_name})>"
