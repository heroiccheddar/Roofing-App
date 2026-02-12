"""NCEI Storm Events Database Loader.

Downloads and aggregates NWS-verified storm events with property damage
estimates to census tracts for verified storm damage risk assessment.

This loader:
1. Downloads per-year CSV.gz files from NCEI Storm Events database
2. Filters to severe weather events: Hail, Thunderstorm Wind, Tornado
3. Parses property damage estimates with K/M/B suffixes
4. Spatially joins events to census tracts using point-in-polygon
5. Aggregates total damage and event counts per tract
6. Bulk updates census_tracts table with verified damage metrics

NCEI Storm Events data provides official NWS-verified storm reports with
property damage estimates, complementing radar-derived SWDI data.
"""

import asyncio
import csv
import gzip
import logging
import re
from collections import defaultdict
from io import StringIO
from typing import Optional

import httpx
from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from shapely.strtree import STRtree
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract

logger = logging.getLogger(__name__)

# NCEI Storm Events FTP directory base URL
NCEI_BASE_URL = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"

# Event types to include (severe weather with roof damage potential)
SEVERE_EVENT_TYPES = {"Hail", "Thunderstorm Wind", "Tornado"}


def parse_damage_value(damage_str: str | None) -> float:
    """Parse NCEI damage value string to USD float.

    NCEI damage values use K/M/B suffixes:
    - "2.50K" = $2,500 (thousands)
    - "1.20M" = $1,200,000 (millions)
    - "3.00B" = $3,000,000,000 (billions)
    - "0.00K" = $0
    - None or empty = $0

    Args:
        damage_str: Damage value string from NCEI CSV (e.g., "2.50K")

    Returns:
        Damage value in USD (float)

    Examples:
        >>> parse_damage_value("2.50K")
        2500.0
        >>> parse_damage_value("1.20M")
        1200000.0
        >>> parse_damage_value("0.00K")
        0.0
        >>> parse_damage_value(None)
        0.0
    """
    if not damage_str or not isinstance(damage_str, str):
        return 0.0

    damage_str = damage_str.strip().upper()

    if not damage_str:
        return 0.0

    # Match pattern: number followed by K, M, or B
    match = re.match(r'^([\d.]+)([KMB])$', damage_str)

    if not match:
        # Try to parse as plain number
        try:
            return float(damage_str)
        except ValueError:
            logger.warning(f"Could not parse damage value: {damage_str}")
            return 0.0

    value_str, suffix = match.groups()

    try:
        value = float(value_str)
    except ValueError:
        logger.warning(f"Could not parse numeric part of damage value: {damage_str}")
        return 0.0

    # Apply multiplier
    multipliers = {
        'K': 1_000,
        'M': 1_000_000,
        'B': 1_000_000_000,
    }

    return value * multipliers[suffix]


async def list_detail_files(years: list[int]) -> list[str]:
    """List available Storm Events detail CSV.gz files for given years.

    Fetches the NCEI directory index HTML and parses for links matching
    the pattern: StormEvents_details-ftp_v1.0_dYYYY_cYYYYMMDD.csv.gz

    Args:
        years: List of years to fetch (e.g., [2020, 2021, 2022])

    Returns:
        List of full URLs to detail CSV.gz files

    Raises:
        httpx.HTTPError: If directory index fetch fails
    """
    logger.info(f"Listing NCEI Storm Events files for years: {years}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(NCEI_BASE_URL)
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch NCEI directory index: {e}")
            raise

    html = response.text

    # Parse HTML for detail file links
    # Pattern: StormEvents_details-ftp_v1.0_dYYYY_cYYYYMMDD.csv.gz
    pattern = re.compile(r'StormEvents_details-ftp_v1\.0_d(\d{4})_c\d{8}\.csv\.gz')

    file_urls = []

    for match in pattern.finditer(html):
        file_year = int(match.group(1))

        if file_year in years:
            filename = match.group(0)
            url = f"{NCEI_BASE_URL}{filename}"
            file_urls.append(url)

    logger.info(f"Found {len(file_urls)} Storm Events detail files")

    return file_urls


async def download_and_parse_events(
    url: str,
    state_fips: str | None = None,
) -> list[dict]:
    """Download and parse Storm Events CSV.gz file.

    Downloads compressed CSV, decompresses, and parses event records.
    Filters to severe event types and optionally by state FIPS.

    Args:
        url: Full URL to CSV.gz file
        state_fips: Optional 2-digit state FIPS code to filter events

    Returns:
        List of event dicts with keys:
        - lat: float (decimal degrees)
        - lon: float (decimal degrees)
        - event_type: str
        - damage_usd: float (parsed from DAMAGE_PROPERTY)
        - state_fips: str
        - magnitude: float | None
        - magnitude_type: str | None

    Raises:
        httpx.HTTPError: If download fails
        gzip.BadGzipFile: If decompression fails
    """
    logger.info(f"Downloading Storm Events file: {url}")

    # Download with retry and exponential backoff
    max_retries = 3
    retry_delay = 2.0

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                break
        except httpx.HTTPError as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"Download attempt {attempt + 1} failed: {e}, "
                    f"retrying in {retry_delay}s"
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                logger.error(f"Failed to download after {max_retries} attempts: {e}")
                raise

    # Decompress gzip
    try:
        csv_content = gzip.decompress(response.content).decode('utf-8', errors='replace')
    except gzip.BadGzipFile as e:
        logger.error(f"Failed to decompress gzip file: {e}")
        raise

    # Parse CSV
    csv_file = StringIO(csv_content)
    reader = csv.DictReader(csv_file)

    events = []
    skipped_no_coords = 0
    skipped_event_type = 0
    skipped_state = 0

    for row in reader:
        # Filter by event type
        event_type = row.get('EVENT_TYPE', '').strip()

        if event_type not in SEVERE_EVENT_TYPES:
            skipped_event_type += 1
            continue

        # Filter by state if specified
        if state_fips:
            row_state_fips = row.get('STATE_FIPS', '').strip()
            if row_state_fips != state_fips:
                skipped_state += 1
                continue

        # Extract coordinates
        lat_str = row.get('BEGIN_LAT', '').strip()
        lon_str = row.get('BEGIN_LON', '').strip()

        if not lat_str or not lon_str:
            skipped_no_coords += 1
            continue

        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except ValueError:
            skipped_no_coords += 1
            continue

        # Validate coordinate ranges
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            skipped_no_coords += 1
            continue

        # Parse damage values
        damage_property = parse_damage_value(row.get('DAMAGE_PROPERTY'))
        damage_crops = parse_damage_value(row.get('DAMAGE_CROPS'))
        total_damage = damage_property + damage_crops

        # Extract magnitude (for hail size, wind speed, tornado rating)
        magnitude_str = row.get('MAGNITUDE', '').strip()
        magnitude = None
        if magnitude_str:
            try:
                magnitude = float(magnitude_str)
            except ValueError:
                pass

        magnitude_type = row.get('MAGNITUDE_TYPE', '').strip() or None

        events.append({
            'lat': lat,
            'lon': lon,
            'event_type': event_type,
            'damage_usd': total_damage,
            'state_fips': row.get('STATE_FIPS', '').strip(),
            'magnitude': magnitude,
            'magnitude_type': magnitude_type,
        })

    logger.info(
        f"Parsed {len(events)} severe weather events from {url.split('/')[-1]} "
        f"(skipped: {skipped_event_type} wrong type, {skipped_state} wrong state, "
        f"{skipped_no_coords} no coords)"
    )

    return events


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


def aggregate_events_to_tracts(
    events: list[dict],
    geoids: list[str],
    tree: STRtree,
    geometries: list,
) -> dict[str, dict]:
    """Aggregate storm events to census tracts using spatial join.

    Uses spatial indexing (STRtree) to efficiently assign each event point
    to its containing census tract and accumulate damage and event counts.

    Args:
        events: List of event dicts with 'lat', 'lon', 'damage_usd'
        geoids: List of census tract GEOIDs (parallel to geometries)
        tree: STRtree spatial index for tracts
        geometries: List of census tract Shapely geometries (parallel to geoids)

    Returns:
        Dict mapping GEOID to aggregated stats:
        {
            "geoid": {
                "total_damage_usd": float,
                "event_count": int,
            }
        }
    """
    logger.info(f"Aggregating {len(events)} storm events to census tracts")

    # Accumulator: geoid -> {total_damage_usd, event_count}
    aggregates = defaultdict(lambda: {"total_damage_usd": 0.0, "event_count": 0})

    matched = 0
    unmatched = 0

    for event in events:
        point = Point(event['lon'], event['lat'])

        # Find containing tract via spatial index
        candidate_indices = tree.query(point)

        tract_geoid = None
        for idx in candidate_indices:
            if geometries[idx].contains(point):
                tract_geoid = geoids[idx]
                break

        if tract_geoid:
            aggregates[tract_geoid]["total_damage_usd"] += event['damage_usd']
            aggregates[tract_geoid]["event_count"] += 1
            matched += 1
        else:
            unmatched += 1

    logger.info(
        f"Aggregation complete: {matched} events matched to "
        f"{len(aggregates)} tracts ({unmatched} unmatched)"
    )

    return dict(aggregates)


async def bulk_update_ncei_data(
    session: AsyncSession,
    aggregates: dict[str, dict],
    batch_size: int = 500,
) -> dict[str, int]:
    """Bulk update census tracts with verified NCEI storm damage data.

    Updates verified_damage_5yr_usd and verified_events_5yr columns
    in batches for efficiency.

    Args:
        session: Async database session
        aggregates: Dict mapping GEOID to {total_damage_usd, event_count}
        batch_size: Number of updates per batch (default 500)

    Returns:
        Stats dict with "updated" and "errors" counts
    """
    if not aggregates:
        logger.warning("No aggregates to update")
        return {"updated": 0, "errors": 0}

    logger.info(f"Updating {len(aggregates)} census tracts with NCEI storm data")

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

                stmt = (
                    update(CensusTract)
                    .where(CensusTract.geoid == geoid)
                    .values(
                        verified_damage_5yr_usd=stats["total_damage_usd"],
                        verified_events_5yr=stats["event_count"],
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


async def load_ncei_storm_events(
    state_fips_codes: list[str],
    session: AsyncSession,
    years_back: int = 5,
) -> dict[str, any]:
    """Load NCEI Storm Events data for given states.

    Orchestrates the full pipeline:
    1. For each state:
       a. Determine years to fetch (current year - years_back to current year)
       b. List available CSV.gz files from NCEI for those years
       c. Download and parse each file (with retry and decompression)
       d. Load census tract geometries and build spatial index
       e. Aggregate events to census tracts via point-in-polygon
       f. Bulk update census_tracts table with verified damage metrics
    2. Rate limit downloads (2 second delay between files)
    3. Return aggregate statistics

    Args:
        state_fips_codes: List of 2-digit state FIPS codes (e.g., ['13', '48'])
        session: Async database session
        years_back: Number of years of historical data to fetch (default 5)

    Returns:
        Dict with aggregate stats:
        - states_processed: Number of states successfully processed
        - total_events: Total number of severe weather events fetched
        - total_tracts_updated: Total number of tracts updated
        - errors: Number of states that failed

    Example:
        >>> result = await load_ncei_storm_events(['13'], session, years_back=5)
        >>> print(f"Processed {result['total_events']:,} storm events")
    """
    from datetime import datetime

    total_states_processed = 0
    total_events = 0
    total_tracts_updated = 0
    total_errors = 0

    logger.info(
        f"Starting NCEI Storm Events load for {len(state_fips_codes)} states "
        f"({years_back} years back)"
    )

    # Determine years to fetch
    current_year = datetime.now().year
    years = list(range(current_year - years_back, current_year + 1))

    logger.info(f"Fetching data for years: {years}")

    # List available files
    try:
        file_urls = await list_detail_files(years)
    except Exception as e:
        logger.error(f"Failed to list NCEI files: {e}", exc_info=True)
        return {
            "states_processed": 0,
            "total_events": 0,
            "total_tracts_updated": 0,
            "errors": len(state_fips_codes),
        }

    if not file_urls:
        logger.warning("No NCEI Storm Events files found for specified years")
        return {
            "states_processed": 0,
            "total_events": 0,
            "total_tracts_updated": 0,
            "errors": 0,
        }

    for state_fips in state_fips_codes:
        try:
            logger.info(f"Processing state {state_fips}")

            # Load tract geometries and build spatial index
            geoids, tree, geometries = await load_tract_geometries(session, state_fips)

            # Accumulate all events across years
            all_events = []

            for url_idx, url in enumerate(file_urls, 1):
                logger.info(f"  File {url_idx}/{len(file_urls)}: {url.split('/')[-1]}")

                try:
                    # Download and parse events (filtered to this state)
                    events = await download_and_parse_events(url, state_fips=state_fips)

                    if events:
                        all_events.extend(events)
                        logger.info(f"    Found {len(events)} events for state {state_fips}")
                    else:
                        logger.info(f"    No events for state {state_fips}")

                except Exception as e:
                    logger.error(
                        f"Error downloading/parsing {url}: {e}",
                        exc_info=True,
                    )
                    # Continue with other files

                # Rate limit: 2 second delay between downloads
                if url_idx < len(file_urls):
                    await asyncio.sleep(2)

            logger.info(
                f"Fetched {len(all_events)} total events for state {state_fips} "
                f"across {len(file_urls)} files"
            )

            if not all_events:
                logger.warning(
                    f"No events found for state {state_fips}, skipping update"
                )
                continue

            # Aggregate events to census tracts
            aggregates = aggregate_events_to_tracts(all_events, geoids, tree, geometries)

            # Bulk update tracts with verified damage metrics
            update_stats = await bulk_update_ncei_data(session, aggregates, batch_size=500)

            # Accumulate stats
            total_states_processed += 1
            total_events += len(all_events)
            total_tracts_updated += update_stats["updated"]

            logger.info(
                f"State {state_fips} complete: {len(aggregates)} tracts updated "
                f"with {len(all_events)} verified events"
            )

        except ValueError as e:
            logger.error(f"Failed to load NCEI data for state {state_fips}: {e}")
            total_errors += 1
        except Exception as e:
            logger.error(
                f"Unexpected error loading NCEI data for state {state_fips}: {e}",
                exc_info=True,
            )
            total_errors += 1

    logger.info(
        f"NCEI Storm Events load complete: {total_states_processed} states processed, "
        f"{total_events:,} events fetched, "
        f"{total_tracts_updated} tracts updated, "
        f"{total_errors} errors"
    )

    return {
        "states_processed": total_states_processed,
        "total_events": total_events,
        "total_tracts_updated": total_tracts_updated,
        "errors": total_errors,
    }
