"""Property parcel model from county GIS data.

Stores individual property records fetched on-demand from county
ArcGIS REST APIs. Cached locally with TTL-based refresh.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    DateTime,
    Date,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from geoalchemy2 import Geometry

from app.database import Base


class Property(Base):
    """Individual property parcel from county GIS data."""

    __tablename__ = "properties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # County source identification
    county_fips = Column(String(5), nullable=False)
    parcel_id = Column(String, nullable=False)
    source_county = Column(String, nullable=False)  # e.g. "cobb", "fulton"

    # Census tract association (set via spatial join on insert)
    tract_geoid = Column(String, nullable=True)

    # Spatial data
    location = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)

    # Property details (normalized from county-specific fields)
    address = Column(String, nullable=True)
    owner_name = Column(String, nullable=True)
    year_built = Column(Integer, nullable=True)
    assessed_value = Column(Float, nullable=True)
    land_value = Column(Float, nullable=True)
    improvement_value = Column(Float, nullable=True)
    square_footage = Column(Integer, nullable=True)
    lot_size_sqft = Column(Float, nullable=True)
    lot_size_acres = Column(Float, nullable=True)
    zoning = Column(String, nullable=True)
    land_use_code = Column(String, nullable=True)
    property_type = Column(String, nullable=True)
    bedrooms = Column(Integer, nullable=True)
    bathrooms = Column(Float, nullable=True)
    stories = Column(Integer, nullable=True)

    # Sale history
    last_sale_date = Column(Date, nullable=True)
    last_sale_price = Column(Float, nullable=True)

    # Roofing-specific
    estimated_roof_age = Column(Integer, nullable=True)
    roof_material = Column(String, nullable=True)

    # Raw data preservation
    raw_attributes = Column(JSONB, nullable=True)

    # Cache management
    fetched_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_accessed_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

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

    __table_args__ = (
        Index("ix_properties_location", "location", postgresql_using="gist"),
        Index(
            "ix_properties_county_parcel",
            "source_county",
            "parcel_id",
            unique=True,
        ),
        Index("ix_properties_tract_geoid", "tract_geoid"),
        Index("ix_properties_year_built", "year_built"),
        Index("ix_properties_last_accessed_at", "last_accessed_at"),
    )

    def __repr__(self):
        return f"<Property(id={self.id}, parcel={self.parcel_id}, addr={self.address})>"
