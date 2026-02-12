"""Spatial analysis utilities for the scoring engine.

This module provides PostGIS spatial helpers for:
- H3 hexagon operations (point-to-hex conversion, boundary generation)
- Census tract spatial queries (intersections, demographic aggregation)
- Storm event clustering and spatial grouping
- Housing density calculations

All database operations are async using SQLAlchemy with GeoAlchemy2.
"""

from typing import Any
import h3
from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from shapely.geometry import Point, Polygon
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract
from app.models.storm_event import StormEvent


def point_to_h3(lat: float, lon: float, resolution: int = 7) -> str:
    """Convert latitude/longitude to H3 hex index.

    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees
        resolution: H3 resolution level (0-15), defaults to 7
                   Resolution 7 ≈ 5.16 km² hexagons

    Returns:
        H3 hex index as string (e.g., '8728308281fffff')

    Examples:
        >>> point_to_h3(39.7392, -104.9903)  # Denver, CO
        '8728308281fffff'
    """
    return h3.latlng_to_cell(lat, lon, resolution)


def h3_to_boundary(h3_index: str) -> list[tuple[float, float]]:
    """Get the boundary polygon coordinates for an H3 hex.

    Args:
        h3_index: H3 hex index string

    Returns:
        List of (lon, lat) coordinate pairs suitable for creating
        a Shapely Polygon or PostGIS geometry

    Notes:
        - H3 returns boundary coordinates as (lat, lon) pairs
        - This function swaps to (lon, lat) for GIS convention
        - The boundary is a closed ring (first point == last point)

    Examples:
        >>> coords = h3_to_boundary('8728308281fffff')
        >>> polygon = Polygon(coords)
    """
    # h3.cell_to_boundary returns LatLngPoly with (lat, lon) pairs
    boundary = h3.cell_to_boundary(h3_index)

    # Convert to (lon, lat) for GIS convention and ensure closed ring
    coords = [(lon, lat) for lat, lon in boundary]

    # H3 v4 returns a closed boundary, but ensure it's closed
    if coords[0] != coords[-1]:
        coords.append(coords[0])

    return coords


async def get_intersecting_tracts(
    session: AsyncSession, geometry_wkt: str
) -> list[CensusTract]:
    """Find all census tracts that intersect a given geometry.

    Args:
        session: AsyncSession for database queries
        geometry_wkt: WKT string representation of geometry
                     (e.g., 'POLYGON((-105 40, -104 40, -104 39, -105 39, -105 40))')

    Returns:
        List of CensusTract model instances that spatially intersect
        the provided geometry

    Examples:
        >>> tracts = await get_intersecting_tracts(session, zone_wkt)
        >>> print(f"Found {len(tracts)} intersecting tracts")
    """
    # Create a WKTElement for spatial comparison
    geom = WKTElement(geometry_wkt, srid=4326)

    # Query using ST_Intersects
    stmt = select(CensusTract).where(
        func.ST_Intersects(CensusTract.geometry, geom)
    )

    result = await session.execute(stmt)
    return list(result.scalars().all())


def compute_housing_density(tract: CensusTract) -> float:
    """Calculate housing density for a census tract.

    Args:
        tract: CensusTract model instance

    Returns:
        Housing density as housing_units / area_sq_km
        Returns 0.0 if area is zero/None or housing_units is None

    Examples:
        >>> density = compute_housing_density(tract)
        >>> print(f"Density: {density:.2f} units/km²")
    """
    # Handle None or zero values
    if not tract.housing_units or not tract.area_sq_km or tract.area_sq_km == 0:
        return 0.0

    return tract.housing_units / tract.area_sq_km


def compute_weighted_demographics(tracts: list[CensusTract]) -> dict[str, Any]:
    """Aggregate demographics across multiple census tracts.

    Uses area-weighted averaging for percentage/value fields,
    summing for count fields.

    Args:
        tracts: List of CensusTract model instances

    Returns:
        Dictionary with aggregated demographics:
        - avg_owner_occupied_pct: Area-weighted average owner occupancy %
        - avg_median_home_value: Area-weighted average median home value
        - avg_median_year_built: Area-weighted average median year built
        - total_housing_units: Sum of all housing units
        - total_population: Sum of all population
        - avg_housing_density: Area-weighted average housing density
        - avg_nri_hail_afreq: Area-weighted average NRI hail frequency
        - avg_nri_hail_ealt: Area-weighted average NRI hail expected annual loss
        - avg_nri_swnd_afreq: Area-weighted average NRI severe wind frequency
        - avg_nri_swnd_ealt: Area-weighted average NRI severe wind expected annual loss
        - avg_nri_trnd_afreq: Area-weighted average NRI tornado frequency
        - avg_median_household_income: Area-weighted average median household income
        - avg_vacancy_rate: Area-weighted average vacancy rate
        - avg_single_family_pct: Area-weighted average single-family percentage
        - avg_pct_built_before_1980: Area-weighted average percentage built before 1980
        - total_building_count: Sum of building counts
        - avg_building_area_sqm: Area-weighted average building area

    Notes:
        - Returns zeros for empty tract lists
        - Skips tracts with None values when computing weighted averages
        - Area weighting: each tract's contribution is proportional to its area

    Examples:
        >>> demo = compute_weighted_demographics(intersecting_tracts)
        >>> print(f"Avg home value: ${demo['avg_median_home_value']:,.0f}")
    """
    # Default percentile values for empty/zero-area cases
    _default_pctiles = {
        f"pctile_{k}": 50.0 for k in [
            "owner_occupied", "home_value", "roof_age", "income", "density",
            "single_family", "low_vacancy", "low_cost_burden", "hpi_appreciation",
            "verified_damage", "climate_weathering", "fema_risk", "canopy_risk",
            "age_clustering", "pre1980_housing", "svi_vulnerability",
            "market_activity",
        ]
    }

    if not tracts:
        return {
            "avg_owner_occupied_pct": 0.0,
            "avg_median_home_value": 0.0,
            "avg_median_year_built": 0.0,
            "total_housing_units": 0,
            "total_population": 0,
            "avg_housing_density": 0.0,
            "avg_nri_hail_afreq": 0.0,
            "avg_nri_hail_ealt": 0.0,
            "avg_nri_swnd_afreq": 0.0,
            "avg_nri_swnd_ealt": 0.0,
            "avg_nri_trnd_afreq": 0.0,
            "avg_median_household_income": 0.0,
            "avg_vacancy_rate": 0.0,
            "avg_single_family_pct": 0.0,
            "avg_pct_built_before_1980": 0.0,
            "total_building_count": 0,
            "avg_building_area_sqm": 0.0,
            "avg_hail_exposure_score": 0.0,
            "avg_hail_events_3yr": 0.0,
            "avg_fema_disaster_score": 0.0,
            "avg_fema_disaster_count": 0.0,
            "avg_tree_canopy_mean_pct": 0.0,
            "avg_tree_canopy_risk_score": 0.0,
            "avg_dominant_decade_pct": 0.0,
            "avg_age_clustering_score": 0.0,
            "avg_pct_cost_burdened": 0.0,
            "avg_hpi_5yr_change": 0.0,
            "avg_verified_damage_5yr_usd": 0.0,
            "avg_verified_events_5yr": 0.0,
            "avg_freeze_thaw_days": 0.0,
            "avg_annual_solar_ghi": 0.0,
            "avg_climate_weathering_score": 0.0,
            "avg_svi_overall": 0.0,
            "avg_svi_socioeconomic": 0.0,
            "avg_svi_housing_type": 0.0,
            "avg_redfin_median_sale_price": 0.0,
            "avg_redfin_median_dom": 0.0,
            "avg_redfin_price_drop_pct": 0.0,
            **_default_pctiles,
        }

    # Calculate total area for weighting
    total_area = sum(t.area_sq_km or 0.0 for t in tracts)

    if total_area == 0:
        return {
            "avg_owner_occupied_pct": 0.0,
            "avg_median_home_value": 0.0,
            "avg_median_year_built": 0.0,
            "total_housing_units": sum(t.housing_units or 0 for t in tracts),
            "total_population": sum(t.population or 0 for t in tracts),
            "avg_housing_density": 0.0,
            "avg_nri_hail_afreq": 0.0,
            "avg_nri_hail_ealt": 0.0,
            "avg_nri_swnd_afreq": 0.0,
            "avg_nri_swnd_ealt": 0.0,
            "avg_nri_trnd_afreq": 0.0,
            "avg_median_household_income": 0.0,
            "avg_vacancy_rate": 0.0,
            "avg_single_family_pct": 0.0,
            "avg_pct_built_before_1980": 0.0,
            "total_building_count": sum(t.building_count or 0 for t in tracts),
            "avg_building_area_sqm": 0.0,
            "avg_hail_exposure_score": 0.0,
            "avg_hail_events_3yr": 0.0,
            "avg_fema_disaster_score": 0.0,
            "avg_fema_disaster_count": 0.0,
            "avg_tree_canopy_mean_pct": 0.0,
            "avg_tree_canopy_risk_score": 0.0,
            "avg_dominant_decade_pct": 0.0,
            "avg_age_clustering_score": 0.0,
            "avg_pct_cost_burdened": 0.0,
            "avg_hpi_5yr_change": 0.0,
            "avg_verified_damage_5yr_usd": 0.0,
            "avg_verified_events_5yr": 0.0,
            "avg_freeze_thaw_days": 0.0,
            "avg_annual_solar_ghi": 0.0,
            "avg_climate_weathering_score": 0.0,
            "avg_svi_overall": 0.0,
            "avg_svi_socioeconomic": 0.0,
            "avg_svi_housing_type": 0.0,
            "avg_redfin_median_sale_price": 0.0,
            "avg_redfin_median_dom": 0.0,
            "avg_redfin_price_drop_pct": 0.0,
            **_default_pctiles,
        }

    # Area-weighted averages
    weighted_owner_occupied = 0.0
    weighted_home_value = 0.0
    weighted_year_built = 0.0
    weighted_density = 0.0
    weighted_nri_hail_afreq = 0.0
    weighted_nri_hail_ealt = 0.0
    weighted_nri_swnd_afreq = 0.0
    weighted_nri_swnd_ealt = 0.0
    weighted_nri_trnd_afreq = 0.0
    weighted_median_household_income = 0.0
    weighted_vacancy_rate = 0.0
    weighted_single_family_pct = 0.0
    weighted_pct_built_before_1980 = 0.0
    weighted_building_area_sqm = 0.0
    weighted_hail_exposure_score = 0.0
    weighted_hail_events_3yr = 0.0
    weighted_fema_disaster_score = 0.0
    weighted_fema_disaster_count = 0.0
    weighted_tree_canopy_mean_pct = 0.0
    weighted_tree_canopy_risk_score = 0.0
    weighted_dominant_decade_pct = 0.0
    weighted_age_clustering_score = 0.0
    weighted_pct_cost_burdened = 0.0
    weighted_hpi_5yr_change = 0.0
    weighted_verified_damage_5yr_usd = 0.0
    weighted_verified_events_5yr = 0.0
    weighted_freeze_thaw_days = 0.0
    weighted_annual_solar_ghi = 0.0
    weighted_climate_weathering_score = 0.0
    weighted_svi_overall = 0.0
    weighted_svi_socioeconomic = 0.0
    weighted_svi_housing_type = 0.0
    weighted_redfin_median_sale_price = 0.0
    weighted_redfin_median_dom = 0.0
    weighted_redfin_price_drop_pct = 0.0
    pctile_accum: dict[str, float] = {}

    for tract in tracts:
        if not tract.area_sq_km:
            continue

        weight = tract.area_sq_km / total_area

        if tract.owner_occupied_pct is not None:
            weighted_owner_occupied += tract.owner_occupied_pct * weight

        if tract.median_home_value is not None:
            weighted_home_value += tract.median_home_value * weight

        if tract.median_year_built is not None:
            weighted_year_built += tract.median_year_built * weight

        density = compute_housing_density(tract)
        weighted_density += density * weight

        # NRI risk metrics
        if tract.nri_hail_afreq is not None:
            weighted_nri_hail_afreq += tract.nri_hail_afreq * weight

        if tract.nri_hail_ealt is not None:
            weighted_nri_hail_ealt += tract.nri_hail_ealt * weight

        if tract.nri_swnd_afreq is not None:
            weighted_nri_swnd_afreq += tract.nri_swnd_afreq * weight

        if tract.nri_swnd_ealt is not None:
            weighted_nri_swnd_ealt += tract.nri_swnd_ealt * weight

        if tract.nri_trnd_afreq is not None:
            weighted_nri_trnd_afreq += tract.nri_trnd_afreq * weight

        # Additional Census ACS variables
        if tract.median_household_income is not None:
            weighted_median_household_income += tract.median_household_income * weight

        if tract.vacancy_rate is not None:
            weighted_vacancy_rate += tract.vacancy_rate * weight

        if tract.single_family_pct is not None:
            weighted_single_family_pct += tract.single_family_pct * weight

        if tract.pct_built_before_1980 is not None:
            weighted_pct_built_before_1980 += tract.pct_built_before_1980 * weight

        # Building footprint data
        if tract.avg_building_area_sqm is not None:
            weighted_building_area_sqm += tract.avg_building_area_sqm * weight

        # Historical hail exposure
        if tract.hail_exposure_score is not None:
            weighted_hail_exposure_score += tract.hail_exposure_score * weight

        if tract.hail_events_3yr is not None:
            weighted_hail_events_3yr += tract.hail_events_3yr * weight

        # FEMA disaster declarations
        if tract.fema_disaster_score is not None:
            weighted_fema_disaster_score += tract.fema_disaster_score * weight

        if tract.fema_disaster_count is not None:
            weighted_fema_disaster_count += tract.fema_disaster_count * weight

        # Tree canopy coverage
        if tract.tree_canopy_mean_pct is not None:
            weighted_tree_canopy_mean_pct += tract.tree_canopy_mean_pct * weight

        if tract.tree_canopy_risk_score is not None:
            weighted_tree_canopy_risk_score += tract.tree_canopy_risk_score * weight

        # Age clustering
        if tract.dominant_decade_pct is not None:
            weighted_dominant_decade_pct += tract.dominant_decade_pct * weight
        if tract.age_clustering_score is not None:
            weighted_age_clustering_score += tract.age_clustering_score * weight

        # Housing cost burden
        if tract.pct_cost_burdened is not None:
            weighted_pct_cost_burdened += tract.pct_cost_burdened * weight

        # FHFA House Price Index
        if tract.hpi_5yr_change is not None:
            weighted_hpi_5yr_change += tract.hpi_5yr_change * weight

        # NCEI verified damage
        if tract.verified_damage_5yr_usd is not None:
            weighted_verified_damage_5yr_usd += tract.verified_damage_5yr_usd * weight
        if tract.verified_events_5yr is not None:
            weighted_verified_events_5yr += tract.verified_events_5yr * weight

        # NASA POWER climate weathering
        if tract.freeze_thaw_days is not None:
            weighted_freeze_thaw_days += tract.freeze_thaw_days * weight
        if tract.annual_solar_ghi is not None:
            weighted_annual_solar_ghi += tract.annual_solar_ghi * weight
        if tract.climate_weathering_score is not None:
            weighted_climate_weathering_score += tract.climate_weathering_score * weight

        # CDC SVI
        if tract.svi_overall is not None:
            weighted_svi_overall += tract.svi_overall * weight
        if tract.svi_socioeconomic is not None:
            weighted_svi_socioeconomic += tract.svi_socioeconomic * weight
        if tract.svi_housing_type is not None:
            weighted_svi_housing_type += tract.svi_housing_type * weight

        # Redfin housing market
        if tract.redfin_median_sale_price is not None:
            weighted_redfin_median_sale_price += tract.redfin_median_sale_price * weight
        if tract.redfin_median_dom is not None:
            weighted_redfin_median_dom += tract.redfin_median_dom * weight
        if tract.redfin_price_drop_pct is not None:
            weighted_redfin_price_drop_pct += tract.redfin_price_drop_pct * weight

        # Percentile ranks (from JSONB column)
        if tract.percentile_ranks:
            for key, val in tract.percentile_ranks.items():
                pctile_accum[key] = pctile_accum.get(key, 0.0) + val * weight

    # Build output with pctile_ prefix, default 50.0 for missing keys
    _pctile_keys = [
        "owner_occupied", "home_value", "roof_age", "income", "density",
        "single_family", "low_vacancy", "low_cost_burden", "hpi_appreciation",
        "verified_damage", "climate_weathering", "fema_risk", "canopy_risk",
        "age_clustering", "pre1980_housing", "svi_vulnerability",
        "market_activity",
    ]
    pctile_out = {f"pctile_{k}": pctile_accum.get(k, 50.0) for k in _pctile_keys}

    return {
        "avg_owner_occupied_pct": weighted_owner_occupied,
        "avg_median_home_value": weighted_home_value,
        "avg_median_year_built": weighted_year_built,
        "total_housing_units": sum(t.housing_units or 0 for t in tracts),
        "total_population": sum(t.population or 0 for t in tracts),
        "avg_housing_density": weighted_density,
        "avg_nri_hail_afreq": weighted_nri_hail_afreq,
        "avg_nri_hail_ealt": weighted_nri_hail_ealt,
        "avg_nri_swnd_afreq": weighted_nri_swnd_afreq,
        "avg_nri_swnd_ealt": weighted_nri_swnd_ealt,
        "avg_nri_trnd_afreq": weighted_nri_trnd_afreq,
        "avg_median_household_income": weighted_median_household_income,
        "avg_vacancy_rate": weighted_vacancy_rate,
        "avg_single_family_pct": weighted_single_family_pct,
        "avg_pct_built_before_1980": weighted_pct_built_before_1980,
        "total_building_count": sum(t.building_count or 0 for t in tracts),
        "avg_building_area_sqm": weighted_building_area_sqm,
        "avg_hail_exposure_score": weighted_hail_exposure_score,
        "avg_hail_events_3yr": weighted_hail_events_3yr,
        "avg_fema_disaster_score": weighted_fema_disaster_score,
        "avg_fema_disaster_count": weighted_fema_disaster_count,
        "avg_tree_canopy_mean_pct": weighted_tree_canopy_mean_pct,
        "avg_tree_canopy_risk_score": weighted_tree_canopy_risk_score,
        "avg_dominant_decade_pct": weighted_dominant_decade_pct,
        "avg_age_clustering_score": weighted_age_clustering_score,
        "avg_pct_cost_burdened": weighted_pct_cost_burdened,
        "avg_hpi_5yr_change": weighted_hpi_5yr_change,
        "avg_verified_damage_5yr_usd": weighted_verified_damage_5yr_usd,
        "avg_verified_events_5yr": weighted_verified_events_5yr,
        "avg_freeze_thaw_days": weighted_freeze_thaw_days,
        "avg_annual_solar_ghi": weighted_annual_solar_ghi,
        "avg_climate_weathering_score": weighted_climate_weathering_score,
        "avg_svi_overall": weighted_svi_overall,
        "avg_svi_socioeconomic": weighted_svi_socioeconomic,
        "avg_svi_housing_type": weighted_svi_housing_type,
        "avg_redfin_median_sale_price": weighted_redfin_median_sale_price,
        "avg_redfin_median_dom": weighted_redfin_median_dom,
        "avg_redfin_price_drop_pct": weighted_redfin_price_drop_pct,
        **pctile_out,
    }


def cluster_events_to_h3(
    events: list[StormEvent], resolution: int = 7
) -> dict[str, list[StormEvent]]:
    """Group storm events by their H3 hex cell.

    Args:
        events: List of StormEvent model instances
        resolution: H3 resolution level (0-15), defaults to 7

    Returns:
        Dictionary mapping h3_index -> list of events in that cell

    Notes:
        - Events with None locations are skipped
        - Uses geoalchemy2.shape.to_shape to extract coordinates from
          PostGIS geometry elements
        - Multiple events in the same hex are grouped together

    Examples:
        >>> clustered = cluster_events_to_h3(storm_events)
        >>> for h3_idx, events in clustered.items():
        ...     print(f"Hex {h3_idx}: {len(events)} events")
    """
    clusters: dict[str, list[StormEvent]] = {}

    for event in events:
        if not event.location:
            continue

        # Convert GeoAlchemy2 element to Shapely geometry
        try:
            geom = to_shape(event.location)

            # Extract lat/lon from Point geometry
            if isinstance(geom, Point):
                lon, lat = geom.x, geom.y
            else:
                # Shouldn't happen with POINT geometry, but handle gracefully
                continue

            # Convert to H3 hex
            h3_index = point_to_h3(lat, lon, resolution)

            # Add to cluster
            if h3_index not in clusters:
                clusters[h3_index] = []
            clusters[h3_index].append(event)

        except Exception:
            # Skip events that fail geometry conversion
            continue

    return clusters


def build_zone_boundary(h3_index: str) -> tuple[str, str]:
    """Build a zone boundary polygon and centroid from an H3 hex.

    Args:
        h3_index: H3 hex index string

    Returns:
        Tuple of (boundary_wkt, centroid_wkt) as WKT strings
        suitable for PostGIS POLYGON and POINT insertion

    Examples:
        >>> boundary_wkt, centroid_wkt = build_zone_boundary('8728308281fffff')
        >>> # Insert into LeadZone
        >>> zone = LeadZone(
        ...     boundary=boundary_wkt,
        ...     centroid=centroid_wkt,
        ...     h3_index=h3_index
        ... )
    """
    # Get boundary coordinates
    coords = h3_to_boundary(h3_index)

    # Create Shapely polygon
    polygon = Polygon(coords)

    # Get centroid
    centroid = polygon.centroid

    # Convert to WKT
    boundary_wkt = polygon.wkt
    centroid_wkt = centroid.wkt

    return boundary_wkt, centroid_wkt
