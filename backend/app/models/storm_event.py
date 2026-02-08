"""Storm event model representing NWS/SPC/SWDI severe weather events.

This model stores individual storm reports (hail, wind, tornado) from
NWS Storm Data, SPC reports, and SWDI radar data. Each event has a point
location and intensity measurements used for scoring.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Float,
    Boolean,
    Integer,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from geoalchemy2 import Geometry

from app.database import Base


class StormEvent(Base):
    """Storm event from NWS/SPC/SWDI data sources."""

    __tablename__ = "storm_events"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Source and event type
    source = Column(String, nullable=False)  # 'nws', 'spc', 'swdi'
    event_type = Column(String, nullable=False)  # 'hail', 'wind', 'tornado'

    # Spatial data
    location = Column(Geometry(geometry_type='POINT', srid=4326), nullable=False)
    warning_polygon = Column(
        Geometry(geometry_type='POLYGON', srid=4326), nullable=True
    )  # NWS warnings, nullable for SPC reports

    # Intensity measurements
    hail_diameter = Column(Float, nullable=True)  # inches
    wind_speed = Column(Float, nullable=True)  # mph

    # Temporal data
    event_timestamp = Column(DateTime(timezone=True), nullable=False)

    # Source-specific identifiers for deduplication
    nws_event_id = Column(String, nullable=True, unique=True)  # NWS Storm Data ID
    spc_report_id = Column(String, nullable=True)  # SPC report ID
    swdi_cell_id = Column(String, nullable=True)  # SWDI MESH cell ID

    # Data quality and corroboration
    radar_confidence = Column(Float, nullable=True)  # 0.0-1.0, from SWDI MESH
    corroborated = Column(Boolean, default=False)  # Confirmed by multiple sources
    corroboration_sources = Column(
        JSONB, nullable=True
    )  # List of confirming source IDs

    # Raw data storage
    raw_data = Column(JSONB, nullable=True)  # Original API response

    # Processing status
    scored = Column(Boolean, default=False)  # Has this been processed by scoring engine

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # Spatial index on location (GIST)
        Index('ix_storm_events_location', 'location', postgresql_using='gist'),
        # Spatial index on warning_polygon (GIST)
        Index('ix_storm_events_warning_polygon', 'warning_polygon', postgresql_using='gist'),
        # BRIN index on event_timestamp for time-range queries
        Index('ix_storm_events_event_timestamp', 'event_timestamp', postgresql_using='brin'),
        # Index on source for source-based queries
        Index('ix_storm_events_source', 'source'),
        # Index on scored status for processing queries
        Index('ix_storm_events_scored', 'scored'),
    )

    def __repr__(self):
        return f"<StormEvent(id={self.id}, source={self.source}, event_type={self.event_type}, timestamp={self.event_timestamp})>"
