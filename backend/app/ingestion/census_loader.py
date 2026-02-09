"""US Census data loader.

Fetches census tract boundaries and demographic data from Census Bureau API.
Loads ACS 5-year estimates for income, housing, and occupancy data.

Census API: https://www.census.gov/data/developers/data-sets.html
TIGER/Line Shapefiles: https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html
"""

import asyncio
import logging
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import geopandas as gpd
import httpx
from geoalchemy2 import WKTElement
from shapely.geometry import MultiPolygon, Polygon
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract

logger = logging.getLogger(__name__)

# ACS 5-Year 2022 variables we need
ACS_VARIABLES = {
    "B25003_001E": "total_housing_tenure",  # Total housing units for tenure
    "B25003_002E": "owner_occupied",  # Owner-occupied housing units
    "B25035_001E": "median_year_built",  # Median year structure built
    "B25077_001E": "median_home_value",  # Median home value
    "B01003_001E": "population",  # Total population
    "B25001_001E": "housing_units",  # Total housing units
}

# Census API base URL
CENSUS_API_BASE = "https://api.census.gov/data/2022/acs/acs5"

# TIGER/Line shapefile URL pattern
TIGER_URL_PATTERN = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_{state_fips}_tract.zip"


class CensusAPIError(Exception):
    """Exception raised for Census API errors."""
    pass


async def fetch_acs_data(
    state_fips: str,
    api_key: str,
    max_retries: int = 3,
) -> list[dict[str, Any]]:
    """Fetch ACS 5-Year demographic data for all tracts in a state.

    Args:
        state_fips: Two-digit state FIPS code (e.g., '48' for Texas)
        api_key: Census API key
        max_retries: Maximum number of retry attempts for HTTP errors

    Returns:
        List of dicts with tract data, each containing:
        - state, county, tract (FIPS codes)
        - ACS variable values

    Raises:
        CensusAPIError: If API request fails after retries
    """
    # Build the API request
    variables = ",".join(ACS_VARIABLES.keys())
    url = f"{CENSUS_API_BASE}?get={variables}&for=tract:*&in=state:{state_fips}&key={api_key}"

    logger.info(f"Fetching ACS data for state {state_fips}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(max_retries):
            try:
                response = await client.get(url)
                response.raise_for_status()

                data = response.json()

                # First row is headers, rest is data
                if len(data) < 2:
                    logger.warning(f"No data returned for state {state_fips}")
                    return []

                headers = data[0]
                rows = data[1:]

                # Convert to list of dicts
                result = []
                for row in rows:
                    row_dict = dict(zip(headers, row))
                    result.append(row_dict)

                logger.info(f"Fetched {len(result)} tracts for state {state_fips}")
                return result

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Rate limit
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                    await asyncio.sleep(wait_time)
                elif e.response.status_code >= 500:  # Server error
                    if attempt < max_retries - 1:
                        logger.warning(f"Server error, retrying (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(2 ** attempt)
                    else:
                        raise CensusAPIError(f"Census API error: {e}") from e
                else:
                    raise CensusAPIError(f"Census API error: {e}") from e

            except httpx.RequestError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Request error, retrying (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise CensusAPIError(f"Census API request failed: {e}") from e

    raise CensusAPIError(f"Failed to fetch ACS data after {max_retries} attempts")


async def fetch_tiger_shapefile(
    state_fips: str,
    max_retries: int = 3,
) -> gpd.GeoDataFrame:
    """Fetch TIGER/Line tract boundary shapefile for a state.

    Args:
        state_fips: Two-digit state FIPS code (e.g., '48' for Texas)
        max_retries: Maximum number of retry attempts for HTTP errors

    Returns:
        GeoDataFrame with tract boundaries and GEOID

    Raises:
        CensusAPIError: If shapefile download fails after retries
    """
    url = TIGER_URL_PATTERN.format(state_fips=state_fips)

    logger.info(f"Downloading TIGER/Line shapefile for state {state_fips}")

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        for attempt in range(max_retries):
            try:
                response = await client.get(url)
                response.raise_for_status()

                # Extract shapefile from zip
                with tempfile.TemporaryDirectory() as tmpdir:
                    zip_data = BytesIO(response.content)
                    with zipfile.ZipFile(zip_data) as z:
                        z.extractall(tmpdir)

                    # Find the .shp file
                    shp_files = list(Path(tmpdir).glob("*.shp"))
                    if not shp_files:
                        raise CensusAPIError(f"No .shp file found in downloaded zip for state {state_fips}")

                    # Read shapefile with geopandas
                    gdf = gpd.read_file(shp_files[0])

                logger.info(f"Loaded {len(gdf)} tract boundaries for state {state_fips}")
                return gdf

            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < max_retries - 1:
                    logger.warning(f"Server error downloading shapefile, retrying (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise CensusAPIError(f"Failed to download shapefile: {e}") from e

            except httpx.RequestError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Request error downloading shapefile, retrying (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise CensusAPIError(f"Failed to download shapefile: {e}") from e

            except Exception as e:
                raise CensusAPIError(f"Failed to process shapefile: {e}") from e

    raise CensusAPIError(f"Failed to fetch shapefile after {max_retries} attempts")


def ensure_multipolygon(geometry) -> MultiPolygon:
    """Convert Polygon to MultiPolygon if needed.

    Args:
        geometry: Shapely Polygon or MultiPolygon

    Returns:
        MultiPolygon geometry
    """
    if isinstance(geometry, Polygon):
        return MultiPolygon([geometry])
    elif isinstance(geometry, MultiPolygon):
        return geometry
    else:
        raise ValueError(f"Unexpected geometry type: {type(geometry)}")


def compute_owner_occupied_pct(total: str | None, owner_occupied: str | None) -> float | None:
    """Compute owner-occupied percentage from ACS variables.

    Args:
        total: B25003_001E (total housing units for tenure)
        owner_occupied: B25003_002E (owner-occupied units)

    Returns:
        Percentage (0-100) or None if data missing
    """
    try:
        total_val = float(total) if total else None
        owner_val = float(owner_occupied) if owner_occupied else None

        if total_val and owner_val and total_val > 0:
            return (owner_val / total_val) * 100.0
        return None
    except (ValueError, TypeError):
        return None


def parse_acs_value(value: str | None) -> int | float | None:
    """Parse ACS variable value, handling missing data codes.

    Census uses negative values for missing data:
    - -666666666: Missing/not available
    - -888888888: Not applicable
    - -999999999: No data

    Args:
        value: String value from Census API

    Returns:
        Parsed numeric value or None if missing
    """
    if value is None or value == "":
        return None

    try:
        num_val = float(value)
        # Negative values indicate missing data
        if num_val < 0:
            return None
        return num_val
    except (ValueError, TypeError):
        return None


async def bulk_upsert_tracts(
    session: AsyncSession,
    tracts: list[dict[str, Any]],
    batch_size: int = 500,
) -> tuple[int, int]:
    """Bulk upsert census tracts into database.

    Uses PostgreSQL's INSERT ... ON CONFLICT DO UPDATE for efficient upserts.
    Batches inserts to stay within asyncpg's 32,767 parameter limit.

    Args:
        session: Async database session
        tracts: List of tract dicts with all required fields
        batch_size: Number of rows per INSERT batch

    Returns:
        Tuple of (inserted_count, updated_count)
    """
    if not tracts:
        return 0, 0

    # Get existing GEOIDs to track inserts vs updates
    geoids = [t["geoid"] for t in tracts]
    existing_geoids: set[str] = set()
    # Batch the IN query too (large IN lists can also be slow)
    for i in range(0, len(geoids), 2000):
        chunk = geoids[i : i + 2000]
        result = await session.execute(
            select(CensusTract.geoid).where(CensusTract.geoid.in_(chunk))
        )
        existing_geoids.update(row[0] for row in result.fetchall())

    # Insert in batches to avoid asyncpg parameter limit (32,767)
    for i in range(0, len(tracts), batch_size):
        batch = tracts[i : i + batch_size]

        stmt = insert(CensusTract).values(batch)

        # On conflict, update all fields except id and created_at
        update_dict = {
            c.name: stmt.excluded[c.name]
            for c in CensusTract.__table__.columns
            if c.name not in ("id", "created_at")
        }

        stmt = stmt.on_conflict_do_update(
            index_elements=["geoid"],
            set_=update_dict,
        )

        await session.execute(stmt)
        logger.info(f"  Upserted batch {i // batch_size + 1} ({len(batch)} tracts)")

    await session.commit()

    inserted = len(tracts) - len(existing_geoids)
    updated = len(existing_geoids)

    return inserted, updated


async def load_census_data(
    state_fips_codes: list[str],
    api_key: str,
    db_session: AsyncSession,
) -> dict[str, int]:
    """Load ACS demographics + TIGER/Line boundaries for given states.

    Fetches ACS 5-Year demographic data and TIGER/Line tract boundaries,
    joins them on GEOID, and bulk loads into the census_tracts table.

    Args:
        state_fips_codes: List of 2-digit state FIPS codes (e.g., ['48', '40'])
        api_key: Census API key
        db_session: Async database session

    Returns:
        Dict with counts:
        - loaded: Number of tracts successfully inserted
        - updated: Number of tracts updated
        - errors: Number of states that failed to load

    Example:
        >>> result = await load_census_data(['48', '40'], api_key, session)
        >>> print(f"Loaded {result['loaded']} new tracts, updated {result['updated']}")
    """
    total_loaded = 0
    total_updated = 0
    total_errors = 0

    logger.info(f"Starting census data load for {len(state_fips_codes)} states")

    for state_fips in state_fips_codes:
        try:
            logger.info(f"Processing state {state_fips}")

            # Fetch ACS data and TIGER/Line boundaries in parallel
            acs_task = fetch_acs_data(state_fips, api_key)
            tiger_task = fetch_tiger_shapefile(state_fips)

            acs_data, tiger_gdf = await asyncio.gather(acs_task, tiger_task)

            if not acs_data:
                logger.warning(f"No ACS data for state {state_fips}, skipping")
                total_errors += 1
                continue

            # Convert ACS data to dict keyed by GEOID
            acs_by_geoid = {}
            for row in acs_data:
                # GEOID = state + county + tract
                state = row.get("state", "").zfill(2)
                county = row.get("county", "").zfill(3)
                tract = row.get("tract", "").zfill(6)
                geoid = f"{state}{county}{tract}"
                acs_by_geoid[geoid] = row

            # Ensure TIGER/Line data has correct CRS (should be EPSG:4326)
            if tiger_gdf.crs is None:
                logger.warning(f"TIGER/Line data missing CRS, assuming EPSG:4326")
                tiger_gdf = tiger_gdf.set_crs("EPSG:4326")
            elif tiger_gdf.crs.to_epsg() != 4326:
                logger.info(f"Reprojecting TIGER/Line data from {tiger_gdf.crs} to EPSG:4326")
                tiger_gdf = tiger_gdf.to_crs("EPSG:4326")

            # Join ACS data with TIGER/Line boundaries
            tracts_to_insert = []

            for _, row in tiger_gdf.iterrows():
                geoid = row["GEOID"]
                acs_row = acs_by_geoid.get(geoid)

                if not acs_row:
                    logger.debug(f"No ACS data for tract {geoid}, skipping")
                    continue

                # Parse FIPS codes
                state_fips_val = geoid[:2]
                county_fips_val = geoid[2:5]
                tract_code_val = geoid[5:]

                # Convert geometry to MultiPolygon
                geometry = ensure_multipolygon(row["geometry"])

                # Convert to WKT for database insert
                wkt_geom = WKTElement(geometry.wkt, srid=4326)

                # Compute area in sq km (convert from sq degrees using geography cast)
                # We'll compute this in the database during insert
                area_sq_km = geometry.area * 12364.0  # Rough conversion at mid-latitudes

                # Parse ACS values
                total_tenure = acs_row.get("B25003_001E")
                owner_occ = acs_row.get("B25003_002E")
                owner_occupied_pct = compute_owner_occupied_pct(total_tenure, owner_occ)

                median_year_built = parse_acs_value(acs_row.get("B25035_001E"))
                median_home_value = parse_acs_value(acs_row.get("B25077_001E"))
                population = parse_acs_value(acs_row.get("B01003_001E"))
                housing_units = parse_acs_value(acs_row.get("B25001_001E"))

                tract_dict = {
                    "geoid": geoid,
                    "state_fips": state_fips_val,
                    "county_fips": county_fips_val,
                    "tract_code": tract_code_val,
                    "geometry": wkt_geom,
                    "owner_occupied_pct": owner_occupied_pct,
                    "median_year_built": int(median_year_built) if median_year_built else None,
                    "median_home_value": median_home_value,
                    "population": int(population) if population else None,
                    "housing_units": int(housing_units) if housing_units else None,
                    "area_sq_km": area_sq_km,
                }

                tracts_to_insert.append(tract_dict)

            # Bulk insert/update
            if tracts_to_insert:
                inserted, updated = await bulk_upsert_tracts(db_session, tracts_to_insert)
                total_loaded += inserted
                total_updated += updated
                logger.info(
                    f"State {state_fips}: inserted {inserted} tracts, "
                    f"updated {updated} tracts"
                )
            else:
                logger.warning(f"No tracts to insert for state {state_fips}")
                total_errors += 1

        except CensusAPIError as e:
            logger.error(f"Failed to load state {state_fips}: {e}")
            total_errors += 1
        except Exception as e:
            logger.error(f"Unexpected error loading state {state_fips}: {e}", exc_info=True)
            total_errors += 1

    logger.info(
        f"Census data load complete: {total_loaded} inserted, "
        f"{total_updated} updated, {total_errors} errors"
    )

    return {
        "loaded": total_loaded,
        "updated": total_updated,
        "errors": total_errors,
    }
