"""Backfill age clustering metrics for existing census tracts.

Fetches B25034 decade variables from Census API and computes:
- dominant_decade: Most common building age decade
- dominant_decade_pct: Percentage in dominant decade
- age_hhi: Herfindahl-Hirschman Index (concentration measure)
- age_clustering_score: Normalized 0-100 clustering score

Also fixes pct_built_before_1980 to include B25034_007E (1970-1979).

Usage:
    # Backfill all states in database
    python -m scripts.backfill_age_clustering

    # Backfill specific state
    python -m scripts.backfill_age_clustering --state 48
"""

import argparse
import asyncio
import logging

import httpx
from sqlalchemy import select, update, distinct

from app.config import settings
from app.database import AsyncSessionLocal
from app.ingestion.census_loader import (
    parse_acs_value,
    compute_age_clustering,
    compute_pct_built_before_1980,
    CENSUS_API_BASE,
)
from app.models.census_tract import CensusTract

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def fetch_b25034_data(state_fips: str, api_key: str, max_retries: int = 3) -> list[dict]:
    """Fetch B25034 decade variables from Census API for all tracts in state.

    Args:
        state_fips: Two-digit state FIPS code
        api_key: Census API key
        max_retries: Number of retry attempts

    Returns:
        List of dicts with state, county, tract, and B25034_001E through B25034_011E
    """
    # B25034_001E: Total
    # B25034_002E: Built 2020 or later
    # B25034_003E: Built 2010-2019
    # B25034_004E: Built 2000-2009
    # B25034_005E: Built 1990-1999
    # B25034_006E: Built 1980-1989
    # B25034_007E: Built 1970-1979
    # B25034_008E: Built 1960-1969
    # B25034_009E: Built 1950-1959
    # B25034_010E: Built 1940-1949
    # B25034_011E: Built before 1940
    variables = ",".join([f"B25034_{str(i).zfill(3)}E" for i in range(1, 12)])
    url = f"{CENSUS_API_BASE}?get={variables}&for=tract:*&in=state:{state_fips}&key={api_key}"

    logger.info(f"Fetching B25034 data for state {state_fips}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(max_retries):
            try:
                response = await client.get(url)
                response.raise_for_status()

                data = response.json()

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

                logger.info(f"Fetched B25034 data for {len(result)} tracts in state {state_fips}")
                return result

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Rate limit
                    wait_time = 2 ** attempt
                    logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                    await asyncio.sleep(wait_time)
                elif e.response.status_code >= 500 and attempt < max_retries - 1:
                    logger.warning(f"Server error, retrying (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error(f"Census API error for state {state_fips}: {e}")
                    return []

            except httpx.RequestError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Request error, retrying (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error(f"Request failed for state {state_fips}: {e}")
                    return []

    logger.error(f"Failed to fetch B25034 data for state {state_fips} after {max_retries} attempts")
    return []


async def backfill_state(state_fips: str, api_key: str, session) -> dict:
    """Backfill age clustering metrics for all tracts in a state.

    Args:
        state_fips: Two-digit state FIPS code
        api_key: Census API key
        session: Async database session

    Returns:
        Dict with updated_count and skipped_count
    """
    logger.info(f"Starting backfill for state {state_fips}")

    # Fetch B25034 data from Census API
    acs_data = await fetch_b25034_data(state_fips, api_key)

    if not acs_data:
        logger.warning(f"No data to backfill for state {state_fips}")
        return {"updated": 0, "skipped": 0}

    # Build dict keyed by GEOID
    acs_by_geoid = {}
    for row in acs_data:
        state = row.get("state", "").zfill(2)
        county = row.get("county", "").zfill(3)
        tract = row.get("tract", "").zfill(6)
        geoid = f"{state}{county}{tract}"
        acs_by_geoid[geoid] = row

    logger.info(f"State {state_fips}: fetched {len(acs_by_geoid)} tract records from Census API")

    # Get all tracts in this state from database
    result = await session.execute(
        select(CensusTract.geoid).where(CensusTract.state_fips == state_fips)
    )
    db_geoids = [row[0] for row in result.fetchall()]

    logger.info(f"State {state_fips}: found {len(db_geoids)} tracts in database")

    # Prepare updates
    updates = []
    updated_count = 0
    skipped_count = 0

    for geoid in db_geoids:
        acs_row = acs_by_geoid.get(geoid)

        if not acs_row:
            logger.debug(f"No Census data for tract {geoid}, skipping")
            skipped_count += 1
            continue

        # Compute age clustering metrics
        clustering = compute_age_clustering(acs_row)

        # Recompute pct_built_before_1980 with corrected formula (including B25034_007E)
        pct_pre1980 = compute_pct_built_before_1980(
            acs_row.get("B25034_001E"),  # total
            acs_row.get("B25034_007E"),  # 1970-1979 (was missing before)
            acs_row.get("B25034_008E"),  # 1960-1969
            acs_row.get("B25034_009E"),  # 1950-1959
            acs_row.get("B25034_010E"),  # 1940-1949
            acs_row.get("B25034_011E"),  # pre-1940
        )

        # Build update statement
        stmt = (
            update(CensusTract)
            .where(CensusTract.geoid == geoid)
            .values(
                dominant_decade=clustering["dominant_decade"],
                dominant_decade_pct=clustering["dominant_decade_pct"],
                age_hhi=clustering["age_hhi"],
                age_clustering_score=clustering["age_clustering_score"],
                pct_built_before_1980=pct_pre1980,
            )
        )

        updates.append((geoid, stmt))

    # Execute updates in batches
    batch_size = 500
    for i in range(0, len(updates), batch_size):
        batch = updates[i : i + batch_size]

        for geoid, stmt in batch:
            await session.execute(stmt)
            updated_count += 1

        # Commit each batch
        await session.commit()

        logger.info(
            f"State {state_fips}: updated batch {i // batch_size + 1} "
            f"({len(batch)} tracts, {updated_count}/{len(db_geoids)} total)"
        )

    logger.info(
        f"State {state_fips} complete: updated {updated_count} tracts, skipped {skipped_count}"
    )

    return {"updated": updated_count, "skipped": skipped_count}


async def main():
    """Main entry point for backfill script."""
    parser = argparse.ArgumentParser(
        description="Backfill age clustering metrics for census tracts"
    )
    parser.add_argument(
        "--state",
        type=str,
        help="State FIPS code (e.g., '48' for Texas). If omitted, backfill all states.",
    )
    args = parser.parse_args()

    if not settings.CENSUS_API_KEY:
        logger.error("Census API key not configured. Set CENSUS_API_KEY environment variable.")
        return

    async with AsyncSessionLocal() as session:
        # Determine which states to process
        if args.state:
            state_codes = [args.state.zfill(2)]
            logger.info(f"Backfilling state {args.state}")
        else:
            # Query all distinct state FIPS codes from database
            result = await session.execute(select(distinct(CensusTract.state_fips)))
            state_codes = sorted([row[0] for row in result.fetchall()])
            logger.info(f"Backfilling all states: {', '.join(state_codes)}")

        if not state_codes:
            logger.warning("No states found in database")
            return

        # Process each state
        total_updated = 0
        total_skipped = 0

        for state_fips in state_codes:
            try:
                result = await backfill_state(state_fips, settings.CENSUS_API_KEY, session)
                total_updated += result["updated"]
                total_skipped += result["skipped"]
            except Exception as e:
                logger.error(f"Failed to backfill state {state_fips}: {e}", exc_info=True)

        logger.info(
            f"Backfill complete: {total_updated} tracts updated, {total_skipped} skipped"
        )


if __name__ == "__main__":
    asyncio.run(main())
