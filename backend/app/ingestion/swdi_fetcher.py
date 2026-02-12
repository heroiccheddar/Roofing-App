"""NOAA Severe Weather Data Inventory (SWDI) fetcher.

Fetches high-resolution radar-derived hail data (MESH - Maximum Expected Size of Hail)
from SWDI API for enhanced spatial accuracy and probability assessment.

API Documentation: https://www.ncdc.noaa.gov/swdi/
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from geoalchemy2.shape import from_shape
from shapely import wkt
from shapely.geometry import Point, box
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storm_event import StormEvent

logger = logging.getLogger(__name__)

# SWDI API Configuration
# URL format: {base}/json/{dataset}/{startdate}:{enddate}?bbox=w,s,e,n
SWDI_BASE_URL = "https://www.ncei.noaa.gov/swdiws/"
SWDI_TIMEOUT = 60.0  # SWDI can be slow with large bbox queries
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0  # seconds


async def fetch_swdi_mesh(
    db_session: AsyncSession,
    bbox: tuple[float, float, float, float],
    start_date: datetime,
    end_date: datetime,
) -> dict:
    """Fetch SWDI MESH (radar hail) data for a bounding box and time range.

    Args:
        db_session: SQLAlchemy async session
        bbox: Bounding box as (west_lon, south_lat, east_lon, north_lat)
        start_date: Start of time window
        end_date: End of time window

    Returns:
        dict with counts: {"fetched": N, "new": N, "existing": N, "errors": N}
    """
    west, south, east, north = bbox

    logger.info(
        f"Fetching SWDI MESH data for bbox=({west},{south},{east},{north}) "
        f"from {start_date} to {end_date}"
    )

    # Format dates for SWDI API (YYYYMMDD or YYYY-MM-DD both work)
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")

    # Build SWDI API URL
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
        return {"fetched": 0, "new": 0, "existing": 0, "errors": 1}

    if not mesh_records:
        logger.info("No MESH data found for the specified area and time range")
        return {"fetched": 0, "new": 0, "existing": 0, "errors": 0}

    logger.info(f"Fetched {len(mesh_records)} MESH records from SWDI")

    # Process and insert records
    counts = {"fetched": len(mesh_records), "new": 0, "existing": 0, "errors": 0}

    for record in mesh_records:
        try:
            await _process_mesh_record(db_session, record, counts)
        except Exception as e:
            logger.error(f"Error processing MESH record: {e}", exc_info=True)
            counts["errors"] += 1

    # Commit all changes
    try:
        await db_session.commit()
        logger.info(
            f"SWDI fetch complete: {counts['new']} new, "
            f"{counts['existing']} existing, {counts['errors']} errors"
        )
    except Exception as e:
        logger.error(f"Error committing SWDI data: {e}", exc_info=True)
        await db_session.rollback()
        counts["errors"] += counts["new"]
        counts["new"] = 0

    return counts


async def fetch_swdi_for_warning(
    db_session: AsyncSession,
    warning_polygon_wkt: str,
    event_timestamp: datetime,
    time_window_hours: int = 2,
) -> dict:
    """Fetch SWDI data for an NWS warning polygon area.

    Computes bounding box from warning polygon and fetches MESH data
    for the area around the time of the warning.

    Args:
        db_session: SQLAlchemy async session
        warning_polygon_wkt: WKT of the NWS warning polygon
        event_timestamp: When the warning was issued
        time_window_hours: Hours before/after to search (default ±2 hours)

    Returns:
        dict with counts: {"fetched": N, "new": N, "existing": N, "errors": N}
    """
    try:
        # Parse warning polygon and compute bounding box
        polygon = wkt.loads(warning_polygon_wkt)
        bounds = polygon.bounds  # (minx, miny, maxx, maxy)

        # Add small buffer (0.1 degrees ~= 11km) to catch nearby cells
        buffer = 0.1
        bbox = (
            bounds[0] - buffer,  # west
            bounds[1] - buffer,  # south
            bounds[2] + buffer,  # east
            bounds[3] + buffer,  # north
        )

        # Compute time window
        start_date = event_timestamp - timedelta(hours=time_window_hours)
        end_date = event_timestamp + timedelta(hours=time_window_hours)

        logger.info(
            f"Fetching SWDI for warning at {event_timestamp}, "
            f"time window ±{time_window_hours}h"
        )

        # Fetch MESH data
        return await fetch_swdi_mesh(db_session, bbox, start_date, end_date)

    except Exception as e:
        logger.error(f"Error fetching SWDI for warning: {e}", exc_info=True)
        return {"fetched": 0, "new": 0, "existing": 0, "errors": 1}


async def _fetch_swdi_with_retry(params: dict) -> Optional[list[dict]]:
    """Fetch from SWDI API with retry logic.

    Args:
        params: Query parameters for SWDI API.
            Must include 'dataset', 'startdate', 'enddate'.
            Optional: 'bbox', 'format' (default json).

    Returns:
        List of MESH records, or None if all retries failed
    """
    # Build URL path: {base}/{format}/{dataset}/{startdate}:{enddate}
    fmt = params.pop("format", "json")
    dataset = params.pop("dataset")
    startdate = params.pop("startdate")
    enddate = params.pop("enddate")
    url = f"{SWDI_BASE_URL}{fmt}/{dataset}/{startdate}:{enddate}"

    # Remaining params (e.g. bbox) become query string
    query_params = params

    async with httpx.AsyncClient(timeout=SWDI_TIMEOUT) as client:
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"SWDI API request (attempt {attempt + 1}/{MAX_RETRIES})")
                response = await client.get(url, params=query_params)

                # Handle rate limiting or temporary unavailability
                if response.status_code == 503:
                    logger.warning(f"SWDI API returned 503, attempt {attempt + 1}/{MAX_RETRIES}")
                    if attempt < MAX_RETRIES - 1:
                        await _async_sleep(RETRY_BACKOFF * (attempt + 1))
                        continue
                    return None

                response.raise_for_status()
                data = response.json()

                # Parse response - SWDI has inconsistent response structure
                return _parse_swdi_response(data)

            except httpx.TimeoutException:
                logger.warning(
                    f"SWDI API timeout (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                if attempt < MAX_RETRIES - 1:
                    await _async_sleep(RETRY_BACKOFF * (attempt + 1))
                    continue
                return None

            except httpx.HTTPError as e:
                logger.error(f"SWDI API HTTP error: {e}")
                if attempt < MAX_RETRIES - 1:
                    await _async_sleep(RETRY_BACKOFF * (attempt + 1))
                    continue
                return None

            except Exception as e:
                logger.error(f"Unexpected error fetching SWDI data: {e}", exc_info=True)
                return None

    return None


def _parse_swdi_response(data: dict) -> list[dict]:
    """Parse SWDI JSON response into list of MESH records.

    Handles the SWDI response structure:
    {"swdiJsonResponse": {"columnTypes": {...}}, "result": [...]}

    Args:
        data: JSON response from SWDI API

    Returns:
        List of MESH record dicts
    """
    records = []

    # Primary format: {"swdiJsonResponse": {...}, "result": [...]}
    if isinstance(data, dict) and "result" in data:
        result = data["result"]
        if isinstance(result, list):
            records = result
        elif isinstance(result, dict) and "data" in result:
            records = result["data"]
    # Try direct array
    elif isinstance(data, list):
        records = data
    # Try top-level data key
    elif isinstance(data, dict) and "data" in data:
        records = data["data"]

    if not records:
        logger.debug("No records found in SWDI response")
        return []

    logger.debug(f"Parsed {len(records)} records from SWDI response")
    return records if isinstance(records, list) else []


async def _process_mesh_record(
    db_session: AsyncSession,
    record: dict,
    counts: dict,
) -> None:
    """Process a single MESH record and insert/update in database.

    Args:
        db_session: SQLAlchemy async session
        record: MESH record dict from SWDI API
        counts: Dict to update with processing counts
    """
    # Extract fields — real SWDI field names
    wsr_id = record.get("WSR_ID")
    cell_id = record.get("CELL_ID")
    ztime = record.get("ZTIME")
    shape_wkt = record.get("SHAPE")  # WKT: "POINT (lon lat)"
    max_size = record.get("MAXSIZE")
    prob = record.get("PROB")  # Hail probability (0-100)

    # Validate required fields
    if not all([wsr_id, cell_id, ztime, shape_wkt, max_size]):
        logger.warning(f"Missing required fields in MESH record: {record}")
        counts["errors"] += 1
        return

    # Parse lon/lat from WKT POINT
    try:
        shape_point = wkt.loads(shape_wkt)
        lon_float = shape_point.x
        lat_float = shape_point.y
    except Exception as e:
        logger.warning(f"Error parsing SHAPE WKT '{shape_wkt}': {e}")
        counts["errors"] += 1
        return

    # Parse numeric values (SWDI returns strings)
    try:
        mesh_inches = float(max_size)
        posh_value = float(prob) if prob else None
    except (ValueError, TypeError) as e:
        logger.warning(f"Error parsing MESH numeric values: {e}, record: {record}")
        counts["errors"] += 1
        return

    # Parse timestamp (YYYYMMDD_HHMM format)
    try:
        event_timestamp = _parse_swdi_timestamp(ztime)
    except Exception as e:
        logger.warning(f"Error parsing MESH timestamp '{ztime}': {e}")
        counts["errors"] += 1
        return

    # Generate unique cell ID for dedup
    swdi_cell_id = f"{wsr_id}_{cell_id}_{ztime}"

    # Check if record already exists
    existing = await db_session.execute(
        select(StormEvent).where(
            StormEvent.swdi_cell_id == swdi_cell_id,
            StormEvent.event_timestamp == event_timestamp,
        )
    )
    if existing.scalar_one_or_none():
        counts["existing"] += 1
        return

    # Convert POSH (0-100) to confidence (0.0-1.0)
    radar_confidence = (posh_value / 100.0) if posh_value is not None else None

    # Create point geometry
    point = Point(lon_float, lat_float)
    location_geom = from_shape(point, srid=4326)

    # Create StormEvent record
    storm_event = StormEvent(
        source="swdi",
        event_type="hail",
        location=location_geom,
        warning_polygon=None,  # SWDI records are point observations
        hail_diameter=mesh_inches,
        wind_speed=None,  # Not applicable for MESH data
        event_timestamp=event_timestamp,
        swdi_cell_id=swdi_cell_id,
        radar_confidence=radar_confidence,
        raw_data=record,
        scored=False,
    )

    db_session.add(storm_event)
    counts["new"] += 1

    logger.debug(
        f"Added SWDI MESH event: cell={swdi_cell_id}, "
        f"hail={mesh_inches}in, POSH={posh_value}%, "
        f"location=({lat_float},{lon_float}), time={event_timestamp}"
    )


def _parse_swdi_timestamp(ztime: str) -> datetime:
    """Parse SWDI ZTIME format to datetime.

    SWDI returns ISO 8601 format: "2023-06-04T22:05:53Z"

    Args:
        ztime: Timestamp string from SWDI

    Returns:
        datetime object (naive, UTC)

    Raises:
        ValueError: If timestamp format is invalid
    """
    ztime = ztime.strip()

    # ISO format: "2023-06-04T22:05:53Z" (primary format from real API)
    if "T" in ztime:
        dt = datetime.fromisoformat(ztime.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None)

    # Legacy YYYYMMDD_HHMM format
    if "_" in ztime:
        date_part, time_part = ztime.split("_")
        return datetime.strptime(f"{date_part}{time_part}", "%Y%m%d%H%M")

    # YYYYMMDDHHMM format
    if len(ztime) == 12:
        return datetime.strptime(ztime, "%Y%m%d%H%M")

    raise ValueError(f"Unrecognized SWDI timestamp format: {ztime}")


async def _async_sleep(seconds: float) -> None:
    """Async sleep helper for retry backoff."""
    import asyncio
    await asyncio.sleep(seconds)
