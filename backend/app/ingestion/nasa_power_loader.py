"""NASA POWER Climate Data loader.

Fetches satellite-derived climate parameters for census tract centroids from
NASA POWER API and computes roof weathering metrics.

Data source: https://power.larc.nasa.gov/api/temporal/climatology/point
Parameters: T2M_MAX, T2M_MIN, ALLSKY_SFC_SW_DWN, PRECTOTCORR, WS10M
No API key required. Rate limit: ~30 requests/minute.

Uses grid optimization to reduce API calls by ~90%: nearby census tract centroids
are grouped into 0.5-degree grid cells and one API call services all tracts in each cell.
"""

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Optional, Any

import httpx
from geoalchemy2.shape import to_shape
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract

logger = logging.getLogger(__name__)

# NASA POWER API configuration
NASA_POWER_API_URL = "https://power.larc.nasa.gov/api/temporal/climatology/point"
NASA_POWER_TIMEOUT = 30.0
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0
RATE_LIMIT_DELAY = 2.0  # Seconds between API calls (30 requests/minute = ~2s delay)

# Climate parameters to fetch
CLIMATE_PARAMETERS = [
    "T2M_MAX",  # Maximum Temperature at 2 Meters (°C)
    "T2M_MIN",  # Minimum Temperature at 2 Meters (°C)
    "ALLSKY_SFC_SW_DWN",  # All Sky Surface Shortwave Downward Irradiance (kWh/m²/day)
    "PRECTOTCORR",  # Precipitation Corrected (mm/day)
    "WS10M",  # Wind Speed at 10 Meters (m/s)
]

# Days per month for non-leap year
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


async def fetch_climate_for_point(
    lat: float,
    lon: float,
    max_retries: int = MAX_RETRIES,
) -> Optional[dict]:
    """Fetch climatology data for a specific point from NASA POWER API.

    Args:
        lat: Latitude in decimal degrees (-90 to 90)
        lon: Longitude in decimal degrees (-180 to 180)
        max_retries: Maximum number of retry attempts

    Returns:
        Dict with monthly climate parameters, or None if request fails.
        Response structure:
        {
            "T2M_MAX": {"1": 10.5, "2": 12.3, ..., "12": 9.8, "13": 11.2},
            "T2M_MIN": {"1": -2.1, "2": -0.5, ..., "12": -3.0, "13": -1.5},
            ...
        }
        Keys "1" through "12" are monthly values, "13" is annual average.

    Raises:
        httpx.HTTPError: If API request fails after retries
    """
    params = {
        "parameters": ",".join(CLIMATE_PARAMETERS),
        "community": "RE",  # Renewable Energy community
        "longitude": lon,
        "latitude": lat,
        "format": "JSON",
    }

    async with httpx.AsyncClient(timeout=NASA_POWER_TIMEOUT, follow_redirects=True) as client:
        for attempt in range(max_retries):
            try:
                response = await client.get(NASA_POWER_API_URL, params=params)
                response.raise_for_status()

                data = response.json()

                # Extract parameter data from nested structure
                parameter_data = data.get("properties", {}).get("parameter", {})

                if not parameter_data:
                    logger.warning(f"No parameter data returned for ({lat:.4f}, {lon:.4f})")
                    return None

                logger.debug(f"Fetched climate data for ({lat:.4f}, {lon:.4f})")
                return parameter_data

            except httpx.HTTPError as e:
                if attempt == max_retries - 1:
                    logger.error(
                        f"Failed to fetch NASA POWER data for ({lat:.4f}, {lon:.4f}) "
                        f"after {max_retries} attempts: {e}"
                    )
                    return None

                logger.warning(
                    f"Attempt {attempt + 1} failed for ({lat:.4f}, {lon:.4f}), "
                    f"retrying in {RETRY_BACKOFF ** attempt}s: {e}"
                )
                await asyncio.sleep(RETRY_BACKOFF ** attempt)

        return None


def compute_freeze_thaw_days(
    monthly_t2m_max: dict[str, float],
    monthly_t2m_min: dict[str, float],
) -> float:
    """Compute estimated annual freeze-thaw cycle days.

    A freeze-thaw cycle occurs when temperatures cross the freezing point.
    For months where the monthly average T2M_MIN <= 0°C and T2M_MAX > 0°C,
    we count all days in that month as experiencing freeze-thaw cycles.

    Args:
        monthly_t2m_max: Dict of monthly max temps (keys "1"-"12" for months)
        monthly_t2m_min: Dict of monthly min temps (keys "1"-"12" for months)

    Returns:
        Estimated annual freeze-thaw cycle days
    """
    freeze_thaw_days = 0.0

    for month in range(1, 13):
        month_str = str(month)

        # Skip if data is missing for this month
        if month_str not in monthly_t2m_max or month_str not in monthly_t2m_min:
            continue

        t_max = monthly_t2m_max[month_str]
        t_min = monthly_t2m_min[month_str]

        # Check if this month experiences freeze-thaw (min <= 0°C, max > 0°C)
        if t_min <= 0.0 and t_max > 0.0:
            # Count all days in this month
            freeze_thaw_days += DAYS_IN_MONTH[month - 1]

    return freeze_thaw_days


def compute_annual_solar_ghi(monthly_sw: dict[str, float]) -> float:
    """Compute annual solar global horizontal irradiance (GHI).

    Sums the total solar energy received over the year.

    Args:
        monthly_sw: Dict of monthly avg daily irradiance in kWh/m²/day (keys "1"-"12")

    Returns:
        Annual solar GHI in kWh/m²/year
    """
    annual_ghi = 0.0

    for month in range(1, 13):
        month_str = str(month)

        # Skip if data is missing for this month
        if month_str not in monthly_sw:
            continue

        daily_irradiance = monthly_sw[month_str]
        days_in_month = DAYS_IN_MONTH[month - 1]

        # Total energy for this month
        annual_ghi += daily_irradiance * days_in_month

    return annual_ghi


def compute_climate_weathering_score(
    freeze_thaw_days: float,
    annual_solar_ghi: float,
    monthly_precip: dict[str, float],
    monthly_wind: dict[str, float],
) -> float:
    """Compute composite climate weathering score (0-100).

    Combines 4 equal components (25 points each):
    1. Freeze-thaw cycles: More cycles = more roof stress from expansion/contraction
    2. Solar UV exposure: Higher irradiance = faster material degradation
    3. Precipitation: More rain/snow = more moisture damage potential
    4. Wind: Higher winds = more mechanical stress and debris impact

    Args:
        freeze_thaw_days: Annual freeze-thaw cycle days
        annual_solar_ghi: Annual solar GHI in kWh/m²/year
        monthly_precip: Dict of monthly avg daily precipitation in mm/day
        monthly_wind: Dict of monthly avg wind speed in m/s

    Returns:
        Climate weathering score (0-100)
    """
    # Component 1: Freeze-thaw (0-25 points)
    # Severe climates can have 120+ freeze-thaw days per year
    freeze_thaw_score = min(freeze_thaw_days / 120.0 * 25.0, 25.0)

    # Component 2: Solar UV (0-25 points)
    # High-irradiance areas can receive 2000+ kWh/m²/year
    solar_score = min(annual_solar_ghi / 2000.0 * 25.0, 25.0)

    # Component 3: Precipitation (0-25 points)
    # Calculate average daily precipitation across all months
    precip_values = [
        monthly_precip[str(month)]
        for month in range(1, 13)
        if str(month) in monthly_precip
    ]
    avg_daily_precip = sum(precip_values) / len(precip_values) if precip_values else 0.0
    # Wet climates can average 6+ mm/day
    precip_score = min(avg_daily_precip / 6.0 * 25.0, 25.0)

    # Component 4: Wind (0-25 points)
    # Calculate average wind speed across all months
    wind_values = [
        monthly_wind[str(month)]
        for month in range(1, 13)
        if str(month) in monthly_wind
    ]
    avg_wind_speed = sum(wind_values) / len(wind_values) if wind_values else 0.0
    # Windy areas can average 8+ m/s
    wind_score = min(avg_wind_speed / 8.0 * 25.0, 25.0)

    # Total score (capped at 100)
    total_score = freeze_thaw_score + solar_score + precip_score + wind_score
    return min(total_score, 100.0)


async def load_tract_centroids(
    session: AsyncSession,
    state_fips: str,
) -> list[tuple[str, float, float]]:
    """Load census tract centroids for a state.

    Args:
        session: Async database session
        state_fips: 2-digit state FIPS code

    Returns:
        List of tuples: (geoid, latitude, longitude)
    """
    logger.info(f"Loading census tract centroids for state {state_fips}")

    stmt = select(
        CensusTract.geoid,
        CensusTract.geometry,
    ).where(
        CensusTract.state_fips == state_fips
    )

    result = await session.execute(stmt)
    rows = result.fetchall()

    centroids = []
    for geoid, geometry_wkb in rows:
        # Convert PostGIS geometry to Shapely and get centroid
        shape = to_shape(geometry_wkb)
        centroid = shape.centroid
        centroids.append((geoid, centroid.y, centroid.x))  # (geoid, lat, lon)

    logger.info(f"Loaded {len(centroids)} tract centroids for state {state_fips}")
    return centroids


def group_centroids_to_grid(
    centroids: list[tuple[str, float, float]],
    grid_size: float = 0.5,
) -> dict[tuple[float, float], list[tuple[str, float, float]]]:
    """Group centroids into grid cells to reduce API calls.

    Instead of making one API call per tract, we group nearby tracts into
    grid cells and make one API call per cell. All tracts in a cell share
    the same climate data.

    For a 0.5-degree grid:
    - A state with 1000 tracts typically reduces to 50-100 grid cells
    - API calls reduced by ~90%, from 2000s to 100-200s

    Args:
        centroids: List of (geoid, lat, lon) tuples
        grid_size: Grid cell size in degrees (default: 0.5)

    Returns:
        Dict mapping (grid_lat, grid_lon) to list of (geoid, lat, lon) tuples
    """
    grid_cells = {}

    for geoid, lat, lon in centroids:
        # Compute grid cell center
        # Floor to grid_size multiples and add half grid_size to get center
        grid_lat = math.floor(lat / grid_size) * grid_size + (grid_size / 2.0)
        grid_lon = math.floor(lon / grid_size) * grid_size + (grid_size / 2.0)

        grid_key = (grid_lat, grid_lon)

        if grid_key not in grid_cells:
            grid_cells[grid_key] = []

        grid_cells[grid_key].append((geoid, lat, lon))

    logger.info(
        f"Grouped {len(centroids)} centroids into {len(grid_cells)} grid cells "
        f"(~{len(centroids) / len(grid_cells):.1f} tracts per cell)"
    )

    return grid_cells


async def bulk_update_climate(
    session: AsyncSession,
    climate_data: dict[str, dict[str, float]],
    batch_size: int = 500,
) -> dict[str, int]:
    """Bulk update census tracts with climate data.

    Args:
        session: Async database session
        climate_data: Dict mapping geoid to computed climate metrics:
            {
                "geoid": {
                    "freeze_thaw_days": float,
                    "annual_solar_ghi": float,
                    "climate_weathering_score": float,
                }
            }
        batch_size: Number of tracts to update per batch

    Returns:
        Dict with counts:
        - tracts_updated: Number of tracts successfully updated
        - errors: Number of errors encountered
    """
    if not climate_data:
        return {"tracts_updated": 0, "errors": 0}

    logger.info(f"Updating {len(climate_data)} census tracts with climate data")

    tracts_updated = 0
    errors = 0

    geoids = list(climate_data.keys())

    for batch_start in range(0, len(geoids), batch_size):
        batch_geoids = geoids[batch_start:batch_start + batch_size]

        try:
            # Build list of update cases
            for geoid in batch_geoids:
                metrics = climate_data[geoid]

                update_stmt = (
                    update(CensusTract)
                    .where(CensusTract.geoid == geoid)
                    .values(
                        freeze_thaw_days=metrics["freeze_thaw_days"],
                        annual_solar_ghi=metrics["annual_solar_ghi"],
                        climate_weathering_score=metrics["climate_weathering_score"],
                    )
                )

                result = await session.execute(update_stmt)
                tracts_updated += result.rowcount

            await session.commit()

            logger.info(
                f"  Updated batch {batch_start // batch_size + 1}: "
                f"{len(batch_geoids)} tracts"
            )

        except Exception as e:
            logger.error(f"Error updating batch at offset {batch_start}: {e}", exc_info=True)
            await session.rollback()
            errors += len(batch_geoids)

    logger.info(
        f"Bulk update complete: {tracts_updated} tracts updated, {errors} errors"
    )

    return {
        "tracts_updated": tracts_updated,
        "errors": errors,
    }


async def load_climate_data(
    state_fips_codes: list[str],
    session: AsyncSession,
) -> dict[str, Any]:
    """Load NASA POWER climate data for multiple states.

    Orchestrates the full process:
    1. Load census tract centroids for each state
    2. Group centroids into grid cells to reduce API calls
    3. Fetch climate data from NASA POWER API for each grid cell
    4. Compute weathering metrics for each tract
    5. Bulk update census tracts with computed metrics

    Args:
        state_fips_codes: List of 2-digit state FIPS codes (e.g., ["13", "48"])
        session: Async database session

    Returns:
        Dict with aggregate stats:
        - states_processed: Number of states processed
        - total_tracts: Total tracts loaded
        - api_calls: Total API calls made
        - tracts_updated: Total tracts updated
        - errors: Total errors encountered

    Example:
        >>> result = await load_climate_data(["13", "48"], session)
        >>> print(f"Updated {result['tracts_updated']} tracts with climate data")
    """
    stats = {
        "states_processed": 0,
        "total_tracts": 0,
        "api_calls": 0,
        "tracts_updated": 0,
        "errors": 0,
    }

    for state_fips in state_fips_codes:
        state_fips = state_fips.strip()

        try:
            logger.info(f"Processing state: {state_fips}")

            # Load tract centroids
            centroids = await load_tract_centroids(session, state_fips)
            stats["total_tracts"] += len(centroids)

            if not centroids:
                logger.info(f"No census tracts found for state {state_fips}")
                stats["states_processed"] += 1
                continue

            # Group into grid cells
            grid_cells = group_centroids_to_grid(centroids)

            # Fetch climate data for each grid cell and compute metrics
            climate_data = {}
            api_call_count = 0

            for (grid_lat, grid_lon), tracts_in_cell in grid_cells.items():
                # Fetch climate data for this grid cell
                parameter_data = await fetch_climate_for_point(grid_lat, grid_lon)
                api_call_count += 1
                stats["api_calls"] += 1

                # Rate limiting: wait between API calls
                await asyncio.sleep(RATE_LIMIT_DELAY)

                if not parameter_data:
                    logger.warning(
                        f"Skipping grid cell ({grid_lat:.4f}, {grid_lon:.4f}) - "
                        f"no data returned ({len(tracts_in_cell)} tracts affected)"
                    )
                    stats["errors"] += len(tracts_in_cell)
                    continue

                # Extract monthly data
                monthly_t2m_max = parameter_data.get("T2M_MAX", {})
                monthly_t2m_min = parameter_data.get("T2M_MIN", {})
                monthly_sw = parameter_data.get("ALLSKY_SFC_SW_DWN", {})
                monthly_precip = parameter_data.get("PRECTOTCORR", {})
                monthly_wind = parameter_data.get("WS10M", {})

                # Compute metrics
                freeze_thaw_days = compute_freeze_thaw_days(monthly_t2m_max, monthly_t2m_min)
                annual_solar_ghi = compute_annual_solar_ghi(monthly_sw)
                climate_score = compute_climate_weathering_score(
                    freeze_thaw_days,
                    annual_solar_ghi,
                    monthly_precip,
                    monthly_wind,
                )

                # Apply same metrics to all tracts in this grid cell
                for geoid, _, _ in tracts_in_cell:
                    climate_data[geoid] = {
                        "freeze_thaw_days": freeze_thaw_days,
                        "annual_solar_ghi": annual_solar_ghi,
                        "climate_weathering_score": climate_score,
                    }

                # Log progress every 10 grid cells
                if api_call_count % 10 == 0:
                    logger.info(
                        f"  Fetched {api_call_count}/{len(grid_cells)} grid cells "
                        f"({len(climate_data)} tracts computed)"
                    )

            logger.info(
                f"Completed {api_call_count} API calls for {len(climate_data)} tracts "
                f"(reduced from {len(centroids)} tracts by grid optimization)"
            )

            # Bulk update tracts
            update_result = await bulk_update_climate(session, climate_data)

            stats["tracts_updated"] += update_result["tracts_updated"]
            stats["errors"] += update_result["errors"]
            stats["states_processed"] += 1

        except Exception as e:
            logger.error(f"Error processing state {state_fips}: {e}", exc_info=True)
            stats["errors"] += 1

    logger.info(f"NASA POWER climate load complete: {stats}")
    return stats
