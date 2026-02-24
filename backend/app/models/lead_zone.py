"""Lead zone model representing scored geographic areas for roofing lead intelligence.

Lead zones are H3 hexagons scored based on roof condition, market quality,
risk exposure, and canvassing efficiency. Storm activity may boost a zone's
score when active weather events are present. These are the primary output
of the scoring engine.
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
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry

from app.database import Base


class LeadZone(Base):
    """Scored geographic zone for canvassing."""

    __tablename__ = "lead_zones"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Spatial data
    boundary = Column(Geometry(geometry_type='POLYGON', srid=4326), nullable=False)
    centroid = Column(Geometry(geometry_type='POINT', srid=4326), nullable=False)

    # H3 identifier
    h3_index = Column(String, nullable=False)  # Primary H3 hex identifier

    # Human-readable location label (e.g., "Plano, TX")
    display_name = Column(String, nullable=True)

    # Lead type: 'standard' (baseline) or 'storm_boosted' (active storm present)
    # Backward compat: 'storm' and 'roof_age' are accepted for legacy records
    lead_type = Column(String, nullable=False, default='standard', server_default='standard')

    # Scoring components
    composite_score = Column(Float, nullable=False)  # 0-100
    damage_prob = Column(Float, nullable=False)  # Sub-score
    lead_quality = Column(Float, nullable=False)  # Sub-score
    density_bonus = Column(Float, nullable=False)  # Sub-score

    # Unified scoring sub-scores (v9+ model)
    roof_condition = Column(Float, nullable=True)       # 0-100
    market_quality = Column(Float, nullable=True)       # 0-100
    risk_exposure = Column(Float, nullable=True)        # 0-100
    canvass_efficiency = Column(Float, nullable=True)   # 0-100
    storm_boost = Column(Float, nullable=True)          # 0-100, null if no storm
    base_score = Column(Float, nullable=True)           # 0-100, composite without storm
    has_active_storm = Column(Boolean, nullable=False, default=False, server_default='false')
    base_scored_at = Column(DateTime(timezone=True), nullable=True)

    predicted_conversion_rate = Column(Float, nullable=True)  # Lookup from score band

    # Score band classification
    score_band = Column(
        String, nullable=False
    )  # 'hot', 'warm', 'cool', 'skip'

    # Model metadata
    score_weights_snapshot = Column(
        JSONB, nullable=False
    )  # Frozen weights at scoring time
    model_version = Column(String, nullable=False)  # e.g., '1.0.0'

    # Event aggregation
    event_count = Column(Integer, nullable=False, default=1)
    max_hail_diameter = Column(Float, nullable=True)
    max_wind_speed = Column(Float, nullable=True)
    primary_event_timestamp = Column(
        DateTime(timezone=True), nullable=True
    )  # Most recent contributing event

    # Zone lifecycle
    expires_at = Column(
        DateTime(timezone=True), nullable=False
    )  # 14 days from latest event
    active = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Zone staleness tracking — updated when canvass session or feedback is submitted
    last_canvassed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    canvass_sessions = relationship(
        "CanvassSession", back_populates="lead_zone", lazy="select"
    )
    alert_logs = relationship("AlertLog", back_populates="lead_zone", lazy="select")
    zone_feedbacks = relationship("ZoneFeedback", back_populates="lead_zone", lazy="select")

    __table_args__ = (
        # Spatial index on boundary (GIST)
        Index('ix_lead_zones_boundary', 'boundary', postgresql_using='gist'),
        # Spatial index on centroid (GIST)
        Index('ix_lead_zones_centroid', 'centroid', postgresql_using='gist'),
        # BRIN index on created_at for time-range queries
        Index('ix_lead_zones_created_at', 'created_at', postgresql_using='brin'),
        # Composite index on score + expires_at for zone listing queries
        Index(
            'ix_lead_zones_score_expires',
            'composite_score',
            'expires_at',
            postgresql_ops={'composite_score': 'DESC'},
        ),
        # Index on h3_index for spatial lookups
        Index('ix_lead_zones_h3_index', 'h3_index'),
        # Index on score_band for filtering by quality
        Index('ix_lead_zones_score_band', 'score_band'),
        # Index on active status
        Index('ix_lead_zones_active', 'active'),
        # Index on expires_at for cleanup queries
        Index('ix_lead_zones_expires_at', 'expires_at'),
        # Index on lead_type for filtering
        Index('ix_lead_zones_lead_type', 'lead_type'),
        # Composite index for lead_type + active + score queries
        Index('ix_lead_zones_type_active_score', 'lead_type', 'active', 'composite_score'),
        # Partial unique index: only one active zone per H3 hex at a time
        Index(
            'ix_lead_zones_h3_active_unique',
            'h3_index',
            unique=True,
            postgresql_where=text('active = true'),
        ),
        # Composite index on has_active_storm + active for storm-filtered queries
        Index('ix_lead_zones_has_active_storm', 'has_active_storm', 'active'),
        # Index on last_canvassed_at for freshness queries in recommendation engine
        Index('ix_lead_zones_last_canvassed_at', 'last_canvassed_at'),
    )

    def __repr__(self):
        return f"<LeadZone(id={self.id}, h3={self.h3_index}, score={self.composite_score}, band={self.score_band})>"
