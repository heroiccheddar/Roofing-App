"""Census tract model with demographic and housing data.

Stores geometries and socioeconomic data from US Census Bureau.
Used for enriching lead zones with demographic context.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    DateTime,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from geoalchemy2 import Geometry

from app.database import Base


class CensusTract(Base):
    """US Census tract with demographic data."""

    __tablename__ = "census_tracts"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Census identifiers
    geoid = Column(String, unique=True, nullable=False)  # Census FIPS code
    state_fips = Column(String, nullable=False)
    county_fips = Column(String, nullable=False)
    tract_code = Column(String, nullable=False)

    # Spatial data
    geometry = Column(
        Geometry(geometry_type='MULTIPOLYGON', srid=4326), nullable=False
    )

    # Demographic and housing data from ACS
    owner_occupied_pct = Column(Float, nullable=True)  # From ACS B25003
    median_year_built = Column(Integer, nullable=True)  # From ACS B25035
    median_home_value = Column(Float, nullable=True)  # From ACS B25077
    population = Column(Integer, nullable=True)  # From ACS B01003
    housing_units = Column(Integer, nullable=True)

    # Computed fields
    area_sq_km = Column(Float, nullable=True)  # Computed from geometry

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # Spatial index on geometry (GIST)
        Index('ix_census_tracts_geometry', 'geometry', postgresql_using='gist'),
        # Index on state_fips for regional queries
        Index('ix_census_tracts_state_fips', 'state_fips'),
        # Composite index on state + county for faster geographic queries
        Index('ix_census_tracts_state_county', 'state_fips', 'county_fips'),
    )

    def __repr__(self):
        return f"<CensusTract(id={self.id}, geoid={self.geoid}, state={self.state_fips})>"
