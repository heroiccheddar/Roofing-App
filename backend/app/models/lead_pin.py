"""Lead pin and pin activity models for address-level sales tracking.

Roofers drop pins on a map at specific addresses, assign a sales funnel
disposition, and track a full interaction history via pin_activities.
"""

import uuid

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry

from app.database import Base


VALID_DISPOSITIONS = {
    "not_home",
    "callback",
    "interested",
    "inspection_set",
    "contract_signed",
    "not_interested",
}


class LeadPin(Base):
    """A pin dropped by a roofer at a specific address on the map.

    Tracks the current disposition (sales funnel status) for the address.
    Full interaction history is stored in the related PinActivity rows.
    """

    __tablename__ = "lead_pins"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    roofer_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("roofer_accounts.id"),
        nullable=False,
    )
    property_id = Column(
        UUID(as_uuid=True),
        ForeignKey("properties.id"),
        nullable=True,
    )
    lead_zone_id = Column(
        UUID(as_uuid=True),
        ForeignKey("lead_zones.id"),
        nullable=True,
    )

    # Spatial data — WGS 84 POINT
    location = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)

    # Address details
    address = Column(String, nullable=True)

    # Current disposition (sales funnel status)
    disposition = Column(String, nullable=False)

    # Free-form notes on the current status
    notes = Column(Text, nullable=True)

    # Homeowner contact information
    contact_name = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)

    # Scheduled follow-up date (set when disposition is "callback")
    callback_date = Column(DateTime(timezone=True), nullable=True, index=True)

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
    roofer_account = relationship("RooferAccount", back_populates="lead_pins")
    property = relationship("Property", foreign_keys=[property_id])
    lead_zone = relationship("LeadZone", foreign_keys=[lead_zone_id])
    activities = relationship(
        "PinActivity",
        back_populates="lead_pin",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="PinActivity.created_at.desc()",
    )

    __table_args__ = (
        # Spatial index for bbox queries
        Index("ix_lead_pins_location", "location", postgresql_using="gist"),
        # B-tree index for user-scoped queries (most common filter)
        Index("ix_lead_pins_roofer_account_id", "roofer_account_id"),
        # B-tree index for disposition filtering
        Index("ix_lead_pins_disposition", "disposition"),
        # BRIN index for time-range queries
        Index("ix_lead_pins_created_at", "created_at", postgresql_using="brin"),
    )

    def __repr__(self):
        return (
            f"<LeadPin(id={self.id}, disposition={self.disposition}, "
            f"address={self.address})>"
        )


class PinActivity(Base):
    """One row per interaction or disposition change on a LeadPin.

    Provides a full chronological audit trail of all status changes
    and notes recorded against an address.
    """

    __tablename__ = "pin_activities"

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

    # Disposition at the time of this interaction
    disposition = Column(String, nullable=False)

    # Optional notes for this specific interaction
    notes = Column(Text, nullable=True)

    # Timestamp
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    lead_pin = relationship("LeadPin", back_populates="activities")
    roofer_account = relationship("RooferAccount", back_populates="pin_activities")

    __table_args__ = (
        # Composite B-tree for timeline queries ordered by time
        Index("ix_pin_activities_pin_created", "lead_pin_id", "created_at"),
    )

    def __repr__(self):
        return (
            f"<PinActivity(id={self.id}, pin_id={self.lead_pin_id}, "
            f"disposition={self.disposition})>"
        )
