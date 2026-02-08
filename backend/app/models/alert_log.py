"""Alert log for sent notifications.

Tracks all email/SMS/websocket alerts sent to roofers about new high-scoring
lead zones. Used for audit trails, preventing duplicate alerts, and tracking
engagement metrics.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class AlertLog(Base):
    """Log of sent alerts to roofers."""

    __tablename__ = "alert_log"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    roofer_account_id = Column(
        UUID(as_uuid=True), ForeignKey('roofer_accounts.id'), nullable=False
    )
    lead_zone_id = Column(
        UUID(as_uuid=True), ForeignKey('lead_zones.id'), nullable=False
    )

    # Alert metadata
    channel = Column(String, nullable=False)  # 'sms', 'email', 'websocket'

    # Delivery tracking
    sent_at = Column(DateTime(timezone=True), nullable=False)
    opened_at = Column(DateTime(timezone=True), nullable=True)  # When roofer opened alert
    acted_on = Column(
        DateTime(timezone=True), nullable=True
    )  # When roofer opened zone detail from alert

    # External service tracking
    message_id = Column(
        String, nullable=True
    )  # Twilio SID or Resend message ID

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    roofer_account = relationship("RooferAccount", back_populates="alert_logs")
    lead_zone = relationship("LeadZone", back_populates="alert_logs")

    __table_args__ = (
        # Index on roofer_account_id for roofer-based queries
        Index('ix_alert_log_roofer_account_id', 'roofer_account_id'),
        # Index on lead_zone_id for zone-based queries
        Index('ix_alert_log_lead_zone_id', 'lead_zone_id'),
        # Composite index for deduplication checks (prevent duplicate alerts)
        Index(
            'ix_alert_log_dedup',
            'roofer_account_id',
            'lead_zone_id',
            'channel',
        ),
        # Index on sent_at for time-based queries
        Index('ix_alert_log_sent_at', 'sent_at'),
        # Index on channel for channel-based analytics
        Index('ix_alert_log_channel', 'channel'),
    )

    def __repr__(self):
        return f"<AlertLog(id={self.id}, roofer={self.roofer_account_id}, zone={self.lead_zone_id}, channel={self.channel})>"
