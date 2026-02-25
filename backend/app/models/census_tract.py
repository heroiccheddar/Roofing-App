"""Census tract model with demographic and housing data.

Stores geometries and socioeconomic data from US Census Bureau.
Used for enriching lead zones with demographic context.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    String,
    Float,
    Integer,
    DateTime,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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

    # Human-readable name (lazily populated via Mapbox reverse geocoding)
    neighborhood_name = Column(String, nullable=True)

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

    # FEMA National Risk Index (NRI)
    nri_hail_afreq = Column(Float, nullable=True)
    nri_hail_expb = Column(Float, nullable=True)
    nri_hail_ealt = Column(Float, nullable=True)
    nri_hail_riskr = Column(String, nullable=True)
    nri_swnd_afreq = Column(Float, nullable=True)
    nri_swnd_expb = Column(Float, nullable=True)
    nri_swnd_ealt = Column(Float, nullable=True)
    nri_swnd_riskr = Column(String, nullable=True)
    nri_trnd_afreq = Column(Float, nullable=True)
    nri_trnd_expb = Column(Float, nullable=True)
    nri_trnd_ealt = Column(Float, nullable=True)
    nri_trnd_riskr = Column(String, nullable=True)

    # Additional Census ACS Variables
    median_household_income = Column(Float, nullable=True)
    vacancy_rate = Column(Float, nullable=True)
    single_family_pct = Column(Float, nullable=True)
    pct_built_before_1980 = Column(Float, nullable=True)

    # Microsoft Building Footprints (aggregated to tract)
    building_count = Column(Integer, nullable=True)
    avg_building_area_sqm = Column(Float, nullable=True)
    total_building_area_sqm = Column(Float, nullable=True)

    # Historical Hail Exposure (NOAA SWDI MESH, aggregated over 3 years)
    hail_events_3yr = Column(Integer, nullable=True)
    max_hail_diameter_3yr = Column(Float, nullable=True)  # inches
    avg_hail_diameter_3yr = Column(Float, nullable=True)  # inches
    hail_exposure_score = Column(Float, nullable=True)  # 0-100

    # FEMA Disaster Declarations (county-level, mapped to tracts)
    fema_disaster_count = Column(Integer, nullable=True)
    fema_last_disaster_date = Column(DateTime(timezone=True), nullable=True)
    fema_disaster_types = Column(JSONB, nullable=True)  # e.g. ["Severe Storm(s)", "Tornado"]
    fema_disaster_score = Column(Float, nullable=True)  # 0-100, recency-weighted

    # Tree Canopy Coverage (USFS NLCD, aggregated from 30m raster)
    tree_canopy_mean_pct = Column(Float, nullable=True)   # 0-100%
    tree_canopy_max_pct = Column(Float, nullable=True)    # 0-100%
    tree_canopy_std_pct = Column(Float, nullable=True)    # Standard deviation
    tree_canopy_risk_score = Column(Float, nullable=True) # 0-100, computed risk score

    # Subdivision Age Clustering (Census ACS B25034 decade distribution)
    dominant_decade = Column(String, nullable=True)     # e.g., "1990s"
    dominant_decade_pct = Column(Float, nullable=True)  # 0-100
    age_hhi = Column(Float, nullable=True)              # 0.0-1.0, Herfindahl index
    age_clustering_score = Column(Float, nullable=True) # 0-100

    # Housing Cost Burden (Census ACS B25091)
    pct_cost_burdened = Column(Float, nullable=True)  # % spending 30%+ income on housing

    # FHFA House Price Index
    hpi_5yr_change = Column(Float, nullable=True)  # 5-year HPI % change

    # NCEI Storm Events (Verified Damage)
    verified_damage_5yr_usd = Column(Float, nullable=True)  # Total property damage last 5 years
    verified_events_5yr = Column(Integer, nullable=True)  # Count of verified severe events

    # NASA POWER Climate Weathering
    freeze_thaw_days = Column(Float, nullable=True)  # Annual freeze-thaw cycle days
    annual_solar_ghi = Column(Float, nullable=True)  # Annual solar radiation kWh/m2
    climate_weathering_score = Column(Float, nullable=True)  # 0-100

    # CDC Social Vulnerability Index (SVI 2022)
    svi_overall = Column(Float, nullable=True)        # RPL_THEMES: 0-1 overall vulnerability
    svi_socioeconomic = Column(Float, nullable=True)  # RPL_THEME1: 0-1 socioeconomic
    svi_housing_type = Column(Float, nullable=True)   # RPL_THEME4: 0-1 housing type/transport

    # USDA Rural-Urban Commuting Area (RUCA) Codes 2020
    ruca_primary = Column(Integer, nullable=True)    # Primary RUCA code 1-10 (1=metro core, 10=rural)
    ruca_category = Column(String, nullable=True)    # 'urban', 'large_rural', 'small_town', 'isolated_rural'

    # Census Building Permits Survey (BPS) — county-level, shared by all tracts in county
    bps_single_family_permits = Column(Integer, nullable=True)  # Annual 1-unit building permits
    bps_all_permits = Column(Integer, nullable=True)            # Annual total building permits (all types)
    bps_total_value = Column(Float, nullable=True)              # Total construction value ($)
    bps_survey_year = Column(Integer, nullable=True)            # Year of the BPS data

    # EPA EJSCREEN — tract-level environmental justice indicators
    ej_pm25 = Column(Float, nullable=True)                # PM2.5 air quality (µg/m³)
    ej_lead_paint = Column(Float, nullable=True)          # % pre-1960 housing (lead paint proxy)
    ej_superfund_proximity = Column(Float, nullable=True) # Proximity to Superfund sites
    ej_wastewater = Column(Float, nullable=True)          # Wastewater discharge indicator
    ej_percentile = Column(Float, nullable=True)          # Overall EJ index percentile (0-100)

    # FEMA Flood Hazard (NFHL) — dominant flood zone for the tract
    flood_zone_code = Column(String, nullable=True)       # e.g., 'A', 'AE', 'X', 'VE'
    flood_risk_category = Column(String, nullable=True)   # 'high', 'moderate', 'low', 'minimal'
    flood_insurance_required = Column(Boolean, nullable=True)  # NFIP mandatory purchase

    # Redfin Housing Market — ZIP-level, allocated to tracts via HUD crosswalk
    redfin_median_sale_price = Column(Float, nullable=True)   # Median sale price ($)
    redfin_median_dom = Column(Float, nullable=True)          # Median days on market
    redfin_inventory = Column(Integer, nullable=True)         # Active listings count
    redfin_price_drop_pct = Column(Float, nullable=True)      # % of listings with price drops
    redfin_data_month = Column(String, nullable=True)         # e.g., "2025-12"

    # Pre-computed percentile ranks (0-100) within state for scoring normalization
    percentile_ranks = Column(JSONB, nullable=True)

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
