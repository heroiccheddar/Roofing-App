"""FHFA House Price Index (HPI) loader.

Downloads census tract-level HPI data from FHFA and computes 5-year home price
appreciation for each tract. Updates census_tracts table with percentage change
in HPI over the most recent 5-year period available.

Data source: https://www.fhfa.gov/sites/default/files/2024-11/HPI_AT_BDL_tract.csv
Format: CSV with tract-level annual HPI values
"""

import asyncio
import csv
import io
import logging
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract

logger = logging.getLogger(__name__)

FHFA_HPI_URL = "https://www.fhfa.gov/sites/default/files/2024-11/HPI_AT_BDL_tract.csv"
FHFA_TIMEOUT = 120.0
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0


async def download_fhfa_csv(max_retries: int = MAX_RETRIES) -> str:
    """Download FHFA census tract-level HPI CSV.

    Uses httpx AsyncClient with timeout, redirects, and exponential backoff retry.

    Args:
        max_retries: Number of retry attempts (default: 3)

    Returns:
        CSV content as string

    Raises:
        httpx.HTTPError: If download fails after all retries
    """
    logger.info(f"Downloading FHFA HPI CSV from {FHFA_HPI_URL}")

    async with httpx.AsyncClient(timeout=FHFA_TIMEOUT, follow_redirects=True) as client:
        for attempt in range(max_retries):
            try:
                response = await client.get(FHFA_HPI_URL)
                response.raise_for_status()

                csv_content = response.text
                logger.info(
                    f"Downloaded FHFA HPI CSV: {len(csv_content)} characters "
                    f"({len(csv_content) / (1024 * 1024):.2f} MB)"
                )
                return csv_content

            except httpx.HTTPError as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to download FHFA HPI CSV after {max_retries} attempts: {e}")
                    raise

                wait_time = RETRY_BACKOFF ** attempt
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed, retrying in {wait_time:.1f}s: {e}"
                )
                await asyncio.sleep(wait_time)

    # Should never reach here due to raise in loop
    raise RuntimeError("Unexpected error in download_fhfa_csv")


def parse_fhfa_csv(csv_content: str) -> dict[str, dict[int, float]]:
    """Parse FHFA HPI CSV into a dict mapping GEOID to yearly HPI values.

    The CSV structure varies but typically has:
    - State FIPS (2 digits)
    - County FIPS (3 digits)
    - Tract code (6 digits)
    - Year
    - HPI value

    Builds 11-digit GEOID as: state(2) + county(3) + tract(6), all zero-padded.

    Args:
        csv_content: Raw CSV content as string

    Returns:
        Dict mapping GEOID -> {year: hpi_value}
        Example: {"13121000100": {2017: 100.5, 2018: 105.2, ...}}
    """
    logger.info("Parsing FHFA HPI CSV")

    reader = csv.DictReader(io.StringIO(csv_content))
    hpi_data = {}
    rows_parsed = 0
    rows_skipped = 0

    for row in reader:
        try:
            # Try common column name variations
            # FHFA uses different naming conventions across releases
            state_fips = None
            county_fips = None
            tract_code = None
            year = None
            hpi_value = None

            # Try to find state FIPS
            for key in ["state", "State", "STATE", "state_fips", "StateFIPS"]:
                if key in row and row[key]:
                    state_fips = row[key].strip().zfill(2)
                    break

            # Try to find county FIPS
            for key in ["county", "County", "COUNTY", "county_fips", "CountyFIPS"]:
                if key in row and row[key]:
                    county_fips = row[key].strip().zfill(3)
                    break

            # Try to find tract code
            for key in ["tract", "Tract", "TRACT", "tract_code", "TractCode"]:
                if key in row and row[key]:
                    tract_code = row[key].strip().zfill(6)
                    break

            # Try to find year
            for key in ["year", "Year", "YEAR", "yr"]:
                if key in row and row[key]:
                    year = int(row[key])
                    break

            # Try to find HPI value
            for key in ["hpi", "HPI", "index_nsa", "IndexNSA", "index", "Index"]:
                if key in row and row[key]:
                    hpi_value = float(row[key])
                    break

            # Validate we found all required fields
            if not all([state_fips, county_fips, tract_code, year, hpi_value]):
                rows_skipped += 1
                continue

            # Build 11-digit GEOID
            geoid = f"{state_fips}{county_fips}{tract_code}"

            # Initialize dict for this GEOID if needed
            if geoid not in hpi_data:
                hpi_data[geoid] = {}

            # Store year -> HPI mapping
            hpi_data[geoid][year] = hpi_value
            rows_parsed += 1

        except (ValueError, KeyError) as e:
            rows_skipped += 1
            logger.debug(f"Skipping row due to parsing error: {e}")
            continue

    logger.info(
        f"Parsed {rows_parsed} HPI records for {len(hpi_data)} census tracts "
        f"({rows_skipped} rows skipped)"
    )

    # Log year range
    if hpi_data:
        all_years = set()
        for yearly_data in hpi_data.values():
            all_years.update(yearly_data.keys())
        if all_years:
            logger.info(f"  Year range: {min(all_years)} - {max(all_years)}")

    return hpi_data


def compute_5yr_change(
    yearly_hpi: dict[int, float],
    current_year: int = 2022,
) -> float | None:
    """Compute 5-year HPI percentage change.

    Calculates: ((hpi_recent - hpi_past) / hpi_past) * 100

    Uses the most recent available year and the value from 5 years prior.
    If current_year data is not available, uses the most recent year in the data.

    Args:
        yearly_hpi: Dict mapping year to HPI value for a single tract
        current_year: Most recent year to use (default: 2022)

    Returns:
        5-year percentage change, or None if insufficient data

    Example:
        >>> compute_5yr_change({2017: 100.0, 2022: 115.0})
        15.0
    """
    if not yearly_hpi or len(yearly_hpi) < 2:
        return None

    # Find the most recent year available (use current_year if present, else max year)
    recent_year = current_year if current_year in yearly_hpi else max(yearly_hpi.keys())
    past_year = recent_year - 5

    # Check if we have data for both years
    if recent_year not in yearly_hpi or past_year not in yearly_hpi:
        return None

    hpi_recent = yearly_hpi[recent_year]
    hpi_past = yearly_hpi[past_year]

    # Validate HPI values are positive
    if hpi_past <= 0 or hpi_recent <= 0:
        return None

    # Compute percentage change
    pct_change = ((hpi_recent - hpi_past) / hpi_past) * 100.0

    return pct_change


async def bulk_update_hpi(
    session: AsyncSession,
    hpi_changes: dict[str, float],
    batch_size: int = 500,
) -> dict[str, int]:
    """Bulk update census tracts with 5-year HPI change values.

    Issues batched UPDATE statements to set hpi_5yr_change column.
    Tracts not found in the database are skipped silently.

    Args:
        session: Async database session
        hpi_changes: Dict mapping GEOID -> 5-year percentage change
        batch_size: Number of tracts to update per batch (default: 500)

    Returns:
        Dict with counts:
        - updated: Number of tracts successfully updated
        - errors: Number of errors encountered
    """
    if not hpi_changes:
        return {"updated": 0, "errors": 0}

    logger.info(f"Bulk updating {len(hpi_changes)} census tracts with HPI data (batch_size={batch_size})")

    updated_count = 0
    error_count = 0

    # Convert to list for batching
    geoid_list = list(hpi_changes.keys())

    for batch_start in range(0, len(geoid_list), batch_size):
        batch_geoids = geoid_list[batch_start:batch_start + batch_size]

        try:
            # Build batch update values
            # We'll update each tract individually in the batch for clarity
            for geoid in batch_geoids:
                hpi_change = hpi_changes[geoid]

                update_stmt = (
                    update(CensusTract)
                    .where(CensusTract.geoid == geoid)
                    .values(hpi_5yr_change=hpi_change)
                )

                result = await session.execute(update_stmt)
                if result.rowcount > 0:
                    updated_count += result.rowcount

            await session.commit()

            if (batch_start // batch_size) % 10 == 0:
                logger.info(f"  Updated {updated_count} tracts so far...")

        except Exception as e:
            logger.error(f"Error updating batch starting at {batch_start}: {e}", exc_info=True)
            await session.rollback()
            error_count += len(batch_geoids)

    logger.info(f"Bulk update complete: {updated_count} tracts updated, {error_count} errors")

    return {"updated": updated_count, "errors": error_count}


async def load_fhfa_hpi(
    session: AsyncSession,
    state_fips: str | None = None,
) -> dict[str, Any]:
    """Load FHFA House Price Index data and compute 5-year changes.

    Orchestrates the full process:
    1. Download FHFA HPI CSV
    2. Parse CSV into yearly HPI values per tract
    3. Compute 5-year percentage change for each tract
    4. Bulk update census_tracts table

    Args:
        session: Async database session
        state_fips: Optional 2-digit state FIPS to filter updates (default: None = all states)

    Returns:
        Dict with stats:
        - tracts_with_data: Number of tracts found in FHFA data
        - tracts_computed: Number of tracts with sufficient data for 5yr change
        - tracts_updated: Number of tracts successfully updated in DB
        - errors: Number of errors encountered

    Example:
        >>> result = await load_fhfa_hpi(session, state_fips="13")
        >>> print(f"Updated {result['tracts_updated']} Georgia tracts with HPI data")
    """
    logger.info("Starting FHFA HPI data load")
    if state_fips:
        logger.info(f"  Filtering to state FIPS: {state_fips}")

    stats = {
        "tracts_with_data": 0,
        "tracts_computed": 0,
        "tracts_updated": 0,
        "errors": 0,
    }

    try:
        # Step 1: Download CSV
        csv_content = await download_fhfa_csv()

        # Step 2: Parse CSV
        hpi_data = parse_fhfa_csv(csv_content)
        stats["tracts_with_data"] = len(hpi_data)

        if not hpi_data:
            logger.warning("No HPI data parsed from CSV")
            return stats

        # Step 3: Compute 5-year changes
        hpi_changes = {}

        for geoid, yearly_hpi in hpi_data.items():
            # Filter by state if specified
            if state_fips and not geoid.startswith(state_fips):
                continue

            pct_change = compute_5yr_change(yearly_hpi)

            if pct_change is not None:
                hpi_changes[geoid] = pct_change
                stats["tracts_computed"] += 1

        logger.info(
            f"Computed 5-year HPI change for {stats['tracts_computed']} tracts "
            f"(out of {stats['tracts_with_data']} with data)"
        )

        if not hpi_changes:
            logger.warning("No tracts had sufficient data for 5-year HPI computation")
            return stats

        # Step 4: Bulk update database
        update_result = await bulk_update_hpi(session, hpi_changes)
        stats["tracts_updated"] = update_result["updated"]
        stats["errors"] = update_result["errors"]

    except Exception as e:
        logger.error(f"Error loading FHFA HPI data: {e}", exc_info=True)
        stats["errors"] += 1
        raise

    logger.info(f"FHFA HPI load complete: {stats}")
    return stats
