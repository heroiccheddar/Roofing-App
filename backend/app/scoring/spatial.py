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

    Notes:
        - Returns zeros for empty tract lists
        - Skips tracts with None values when computing weighted averages
        - Area weighting: each tract's contribution is proportional to its area

    Examples:
        >>> demo = compute_weighted_demographics(intersecting_tracts)
        >>> print(f"Avg home value: ${demo['avg_median_home_value']:,.0f}")
    """
    if not tracts:
        return {
            "avg_owner_occupied_pct": 0.0,
            "avg_median_home_value": 0.0,
            "avg_median_year_built": 0.0,
            "total_housing_units": 0,
            "total_population": 0,
            "avg_housing_density": 0.0,
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
        }

    # Area-weighted averages
    weighted_owner_occupied = 0.0
    weighted_home_value = 0.0
    weighted_year_built = 0.0
    weighted_density = 0.0

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

    return {
        "avg_owner_occupied_pct": weighted_owner_occupied,
        "avg_median_home_value": weighted_home_value,
        "avg_median_year_built": weighted_year_built,
        "total_housing_units": sum(t.housing_units or 0 for t in tracts),
        "total_population": sum(t.population or 0 for t in tracts),
        "avg_housing_density": weighted_density,
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
