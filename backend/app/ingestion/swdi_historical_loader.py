"""NOAA SWDI Historical Hail Loader.

Aggregates 3 years of NOAA radar-derived hail (MESH) data to census tracts
for hail exposure scoring and risk assessment.

This loader:
1. Fetches historical MESH (Maximum Expected Size of Hail) data from SWDI API
2. Uses spatial indexing (STRtree) to aggregate hail events to census tracts
3. Computes exposure metrics: event count, max/avg diameter, exposure score
4. Bulk updates census_tracts table with historical hail data

MESH data provides high-resolution radar-derived hail estimates with diameter
measurements in inches, enabling fine-grained hail risk assessment.
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from shapely.strtree import STRtree
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from shapely import wkt as shapely_wkt

from app.database import AsyncSessionLocal
from app.models.census_tract import CensusTract
from app.ingestion.swdi_fetcher import _fetch_swdi_with_retry, _parse_swdi_response

logger = logging.getLogger(__name__)


async def get_state_bbox(
    session: AsyncSession,
    state_fips: str,
) -> tuple[float, float, float, float]:
    """Get bounding box for a state from census tract geometries.

    Args:
        session: Async database session
        state_fips: Two-digit state FIPS code

    Returns:
        Tuple of (west, south, east, north) in decimal degrees
        with 0.05 degree buffer on all sides

    Raises:
        ValueError: If no tracts found for state or extent query fails
    """
    logger.info(f"Computing bounding box for state {state_fips}")

    # Query ST_Extent to get bounding box of all tracts in state
    result = await session.execute(
        select(func.ST_Extent(CensusTract.geometry))
        .where(CensusTract.state_fips == state_fips)
    )
    extent = result.scalar()

    if not extent:
        raise ValueError(f"No census tracts found for state {state_fips}")

    # Parse BOX format: "BOX(west south,east north)"
    # Example: "BOX(-106.645646 25.837377,-93.508039 36.500704)"
    extent_str = extent.replace("BOX(", "").replace(")", "")
    coords = extent_str.split(",")
    west_south = coords[0].strip().split()
    east_north = coords[1].strip().split()

    west = float(west_south[0])
    south = float(west_south[1])
    east = float(east_north[0])
    north = float(east_north[1])

    # Add buffer to catch hail events near state boundaries
    buffer = 0.05
    bbox = (west - buffer, south - buffer, east + buffer, north + buffer)

    logger.info(
        f"State {state_fips} bbox: ({bbox[0]:.4f}, {bbox[1]:.4f}, "
        f"{bbox[2]:.4f}, {bbox[3]:.4f})"
    )

    return bbox


async def load_tract_geometries(
    session: AsyncSession,
    state_fips: str,
) -> tuple[list[str], STRtree, list]:
    """Load census tract geometries for a state and build spatial index.

    Args:
        session: Async database session
        state_fips: Two-digit state FIPS code

    Returns:
        Tuple of (geoid_list, STRtree, geometry_list)
        - geoid_list: List of GEOIDs, parallel to geometry_list
        - STRtree: Spatial index for fast point-in-polygon queries
        - geometry_list: List of Shapely geometries, parallel to geoid_list

    Raises:
        ValueError: If no tracts found for state
    """
    logger.info(f"Loading census tract geometries for state {state_fips}")

    # Query all tracts for this state
    result = await session.execute(
        select(CensusTract.geoid, CensusTract.geometry)
        .where(CensusTract.state_fips == state_fips)
    )
    rows = result.fetchall()

    if not rows:
        raise ValueError(f"No census tracts found for state {state_fips}")

    # Convert WKB geometries to Shapely geometries
    geoids = []
    geometries = []

    for geoid, wkb_geom in rows:
        geoids.append(geoid)
        shapely_geom = to_shape(wkb_geom)
        geometries.append(shapely_geom)

    # Build spatial index for fast point-in-polygon queries
    tree = STRtree(geometries)

    logger.info(f"Loaded {len(geoids)} census tracts for state {state_fips}")

    return geoids, tree, geometries


def aggregate_mesh_to_tracts(
    mesh_points: list[tuple[float, float, float]],
    geoids: list[str],
    tree: STRtree,
    geometries: list,
) -> dict[str, dict]:
    """Aggregate MESH hail points to census tracts.

    Uses spatial indexing (STRtree) to efficiently assign each hail point
    to its containing census tract and accumulate statistics.

    Args:
        mesh_points: List of (lon, lat, hail_diameter_inches) tuples
        geoids: List of census tract GEOIDs (parallel to geometries)
        tree: STRtree spatial index for tracts
        geometries: List of census tract Shapely geometries (parallel to geoids)

    Returns:
        Dict mapping GEOID to aggregated stats:
        {
            "geoid": {
                "count": int,           # Number of hail events
                "max_diameter": float,  # Max hail diameter in inches
                "sum_diameter": float,  # Sum of diameters for averaging
            }
        }
    """
    logger.info(f"Aggregating {len(mesh_points)} MESH points to census tracts")

    # Accumulator: geoid -> {count, max_diameter, sum_diameter}
    aggregates = defaultdict(lambda: {"count": 0, "max_diameter": 0.0, "sum_diameter": 0.0})

    matched = 0
    unmatched = 0

    for lon, lat, diameter in mesh_points:
        point = Point(lon, lat)

        # Find containing tract via spatial index
        candidate_indices = tree.query(point)

        tract_geoid = None
        for idx in candidate_indices:
            if geometries[idx].contains(point):
                tract_geoid = geoids[idx]
                break

        if tract_geoid:
            aggregates[tract_geoid]["count"] += 1
            aggregates[tract_geoid]["max_diameter"] = max(
                aggregates[tract_geoid]["max_diameter"], diameter
            )
            aggregates[tract_geoid]["sum_diameter"] += diameter
            matched += 1
        else:
            unmatched += 1

    logger.info(
        f"Aggregation complete: {matched} hail events matched to "
        f"{len(aggregates)} tracts ({unmatched} unmatched)"
    )

    return dict(aggregates)


async def fetch_historical_mesh(
    bbox: tuple[float, float, float, float],
    start_date: datetime,
    end_date: datetime,
) -> list[tuple[float, float, float]]:
    """Fetch historical MESH data from SWDI API.

    Args:
        bbox: Bounding box as (west, south, east, north)
        start_date: Start of time window
        end_date: End of time window

    Returns:
        List of (lon, lat, hail_diameter_inches) tuples, deduplicated by
        unique cell identifier (wsr_id, cell_id, ztime)

    Note:
        Uses _fetch_swdi_with_retry and _parse_swdi_response from swdi_fetcher
        for consistent API interaction and retry logic.
    """
    west, south, east, north = bbox

    logger.info(
        f"Fetching SWDI MESH data for bbox=({west},{south},{east},{north}) "
        f"from {start_date.date()} to {end_date.date()}"
    )

    # Format dates for SWDI API (YYYYMMDD)
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")

    # Build SWDI API request params
    params = {
        "dataset": "nx3hail",
        "startdate": start_str,
        "enddate": end_str,
        "bbox": f"{west},{south},{east},{north}",
        "format": "json",
    }

    # Fetch data with retries
    mesh_records = await _fetch_swdi_with_retry(params)

    if mesh_records is None:
        logger.error("Failed to fetch SWDI data after retries")
        return []

    if not mesh_records:
        logger.debug("No MESH data found for the specified area and time range")
        return []

    logger.info(f"Fetched {len(mesh_records)} MESH records from SWDI")

    # Parse and deduplicate records
    mesh_points = []
    seen_cells = set()

    for record in mesh_records:
        # Extract fields — real SWDI field names
        wsr_id = record.get("WSR_ID")
        cell_id = record.get("CELL_ID")
        ztime = record.get("ZTIME")
        shape_wkt = record.get("SHAPE")  # WKT: "POINT (lon lat)"
        max_size = record.get("MAXSIZE")

        # Validate required fields
        if not all([wsr_id, cell_id, ztime, shape_wkt, max_size]):
            logger.warning(f"Missing required fields in MESH record: {record}")
            continue

        # Deduplicate by unique cell identifier
        cell_key = (wsr_id, cell_id, ztime)
        if cell_key in seen_cells:
            continue
        seen_cells.add(cell_key)

        # Parse lon/lat from WKT POINT and numeric values
        try:
            shape_point = shapely_wkt.loads(shape_wkt)
            lon_float = shape_point.x
            lat_float = shape_point.y
            diameter_inches = float(max_size)
        except Exception as e:
            logger.warning(f"Error parsing MESH record: {e}, record: {record}")
            continue

        mesh_points.append((lon_float, lat_float, diameter_inches))

    logger.info(f"Parsed {len(mesh_points)} unique MESH points (after deduplication)")

    return mesh_points


async def bulk_update_hail_exposure(
    session: AsyncSession,
    aggregates: dict[str, dict],
    batch_size: int = 500,
) -> dict:
    """Bulk update census tracts with historical hail exposure data.

    Computes hail exposure metrics from aggregated MESH data:
    - hail_events_3yr: Total number of hail events
    - max_hail_diameter_3yr: Maximum hail diameter observed (inches)
    - avg_hail_diameter_3yr: Average hail diameter (inches)
    - hail_exposure_score: Composite score (0-100) based on frequency and severity

    Args:
        session: Async database session
        aggregates: Dict mapping GEOID to {count, max_diameter, sum_diameter}
        batch_size: Number of updates per batch (default 500)

    Returns:
        Stats dict with "updated" and "errors" counts
    """
    if not aggregates:
        logger.warning("No aggregates to update")
        return {"updated": 0, "errors": 0}

    logger.info(f"Updating {len(aggregates)} census tracts with hail exposure data")

    updated_count = 0
    error_count = 0

    # Process in batches
    geoids = list(aggregates.keys())
    for i in range(0, len(geoids), batch_size):
        batch_geoids = geoids[i : i + batch_size]

        try:
            # Update each tract in the batch
            for geoid in batch_geoids:
                stats = aggregates[geoid]
                count = stats["count"]
                max_diameter = stats["max_diameter"]
                sum_diameter = stats["sum_diameter"]

                # Compute metrics
                avg_diameter = sum_diameter / count if count > 0 else None

                # Hail exposure score: weighted by frequency and severity
                # Formula: min(count * 5 + max_diameter * 10, 100)
                # - Each event adds 5 points (frequency component)
                # - Max diameter adds 10 points per inch (severity component)
                # - Capped at 100
                exposure_score = min(count * 5.0 + max_diameter * 10.0, 100.0)

                # Update the tract
                stmt = (
                    update(CensusTract)
                    .where(CensusTract.geoid == geoid)
                    .values(
                        hail_events_3yr=count,
                        max_hail_diameter_3yr=max_diameter,
                        avg_hail_diameter_3yr=avg_diameter,
                        hail_exposure_score=exposure_score,
                    )
                )
                await session.execute(stmt)
                updated_count += 1

            # Commit batch
            await session.commit()
            logger.info(f"  Updated batch {i // batch_size + 1} ({len(batch_geoids)} tracts)")

        except Exception as e:
            logger.error(f"Error updating batch {i // batch_size + 1}: {e}", exc_info=True)
            await session.rollback()
            error_count += len(batch_geoids)

    logger.info(f"Update complete: {updated_count} tracts updated, {error_count} errors")

    return {
        "updated": updated_count,
        "errors": error_count,
    }


async def load_swdi_historical(
    state_fips_codes: list[str],
    session: AsyncSession,
    years_back: int = 3,
) -> dict:
    """Load historical SWDI MESH data for given states.

    Orchestrates the full pipeline:
    1. For each state:
       a. Get state bounding box from census tract geometries
       b. Load census tract geometries and build spatial index
       c. Fetch MESH data in quarterly batches over years_back years
       d. Aggregate hail events to census tracts
       e. Bulk update census_tracts table with exposure metrics
    2. Rate limit API calls (2 second delay between requests)
    3. Return aggregate statistics

    Args:
        state_fips_codes: List of 2-digit state FIPS codes (e.g., ['13', '48'])
        session: Async database session
        years_back: Number of years of historical data to fetch (default 3)

    Returns:
        Dict with aggregate stats:
        - states_processed: Number of states successfully processed
        - total_hail_events: Total number of hail events fetched
        - total_tracts_updated: Total number of tracts updated
        - errors: Number of states that failed

    Example:
        >>> result = await load_swdi_historical(['13'], session, years_back=3)
        >>> print(f"Processed {result['total_hail_events']:,} hail events")
    """
    total_states_processed = 0
    total_hail_events = 0
    total_tracts_updated = 0
    total_errors = 0

    logger.info(
        f"Starting SWDI historical load for {len(state_fips_codes)} states "
        f"({years_back} years back)"
    )

    for state_fips in state_fips_codes:
        try:
            logger.info(f"Processing state {state_fips}")

            # Get state bounding box
            bbox = await get_state_bbox(session, state_fips)

            # Load tract geometries and build spatial index
            geoids, tree, geometries = await load_tract_geometries(session, state_fips)

            # Generate monthly date ranges for fetching (API can't handle 90-day windows
            # for state-wide bboxes — returns 500; 30-day windows succeed)
            end = datetime.now()
            start = end - timedelta(days=years_back * 365)

            months = []
            current = start
            while current < end:
                m_end = min(current + timedelta(days=30), end)
                months.append((current, m_end))
                current = m_end

            logger.info(f"Fetching MESH data in {len(months)} monthly batches")

            # Accumulate all MESH points across months
            all_mesh_points = []

            for m_idx, (m_start, m_end) in enumerate(months, 1):
                logger.info(
                    f"  Month {m_idx}/{len(months)}: "
                    f"{m_start.date()} to {m_end.date()}"
                )

                # Fetch MESH data for this month
                mesh_points = await fetch_historical_mesh(bbox, m_start, m_end)

                if mesh_points:
                    all_mesh_points.extend(mesh_points)
                    logger.info(f"    Fetched {len(mesh_points)} MESH points")
                else:
                    logger.info("    No MESH data for this month")

                # Rate limit: 2 second delay between API calls
                if m_idx < len(months):  # Don't delay after last month
                    await asyncio.sleep(2)

            logger.info(
                f"Fetched {len(all_mesh_points)} total MESH points for state {state_fips}"
            )

            if not all_mesh_points:
                logger.warning(f"No MESH data found for state {state_fips}, skipping update")
                continue

            # Aggregate MESH points to census tracts
            aggregates = aggregate_mesh_to_tracts(all_mesh_points, geoids, tree, geometries)

            # Use a fresh session for DB updates (the original session may have
            # timed out during the long API fetching phase)
            async with AsyncSessionLocal() as update_session:
                update_stats = await bulk_update_hail_exposure(update_session, aggregates, batch_size=500)

            # Accumulate stats
            total_states_processed += 1
            total_hail_events += len(all_mesh_points)
            total_tracts_updated += update_stats["updated"]

            logger.info(
                f"State {state_fips} complete: {len(aggregates)} tracts updated "
                f"with {len(all_mesh_points)} hail events"
            )

        except ValueError as e:
            logger.error(f"Failed to load SWDI data for state {state_fips}: {e}")
            total_errors += 1
        except Exception as e:
            logger.error(
                f"Unexpected error loading SWDI data for state {state_fips}: {e}",
                exc_info=True,
            )
            total_errors += 1

    logger.info(
        f"SWDI historical load complete: {total_states_processed} states processed, "
        f"{total_hail_events:,} hail events fetched, "
        f"{total_tracts_updated} tracts updated, "
        f"{total_errors} errors"
    )

    return {
        "states_processed": total_states_processed,
        "total_hail_events": total_hail_events,
        "total_tracts_updated": total_tracts_updated,
        "errors": total_errors,
    }
