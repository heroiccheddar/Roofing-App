"""USDA Rural-Urban Commuting Area (RUCA) codes loader.

Downloads and loads tract-level RUCA codes for urban/rural
classification of census tracts.

Data source: USDA Economic Research Service, RUCA Codes 2020
https://www.ers.usda.gov/data-products/rural-urban-commuting-area-codes/
"""

import csv
import io
import logging

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract

logger = logging.getLogger(__name__)

RUCA_CSV_URL = "https://ers.usda.gov/sites/default/files/_laserfiche/DataFiles/53241/RUCA-codes-2020-tract.csv"
RUCA_TIMEOUT = 60.0

# Primary RUCA code → simplified category
RUCA_CATEGORIES = {
    1: "urban", 2: "urban", 3: "urban",
    4: "large_rural", 5: "large_rural", 6: "large_rural",
    7: "small_town", 8: "small_town", 9: "small_town",
    10: "isolated_rural",
    99: None,  # Not coded (zero-pop tracts)
}


async def load_ruca_data(
    session: AsyncSession,
    state_fips_codes: list[str],
) -> dict:
    """Download USDA RUCA CSV and update census tracts.

    Args:
        session: SQLAlchemy async session
        state_fips_codes: List of 2-digit state FIPS codes to filter

    Returns:
        Stats dict with tracts_matched, tracts_updated, tracts_not_found, errors
    """
    stats = {"tracts_matched": 0, "tracts_updated": 0, "tracts_not_found": 0, "errors": 0}

    logger.info(f"Downloading RUCA data from {RUCA_CSV_URL}")
    try:
        async with httpx.AsyncClient(timeout=RUCA_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(RUCA_CSV_URL)
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to download RUCA CSV: {e}")
        stats["errors"] = 1
        return stats

    csv_text = response.text
    if csv_text.startswith('\ufeff'):
        csv_text = csv_text[1:]

    logger.info(f"Downloaded RUCA CSV ({len(csv_text)} bytes)")

    reader = csv.DictReader(io.StringIO(csv_text))

    state_fips_set = set(state_fips_codes)
    ruca_data = {}  # geoid → {ruca_primary, ruca_category}

    for row in reader:
        # Use 2020-vintage tract FIPS (11-digit GEOID)
        fips = row.get("TractFIPS20", "").strip()
        if not fips or len(fips) < 5:
            continue

        # Filter by state FIPS (first 2 digits)
        if fips[:2] not in state_fips_set:
            continue

        # Parse primary RUCA code
        try:
            primary = int(float(row.get("PrimaryRUCA", "0")))
        except (ValueError, TypeError):
            continue

        category = RUCA_CATEGORIES.get(primary)

        ruca_data[fips] = {
            "ruca_primary": primary,
            "ruca_category": category,
        }

    logger.info(f"Parsed {len(ruca_data)} tracts for states {state_fips_codes}")
    stats["tracts_matched"] = len(ruca_data)

    if not ruca_data:
        return stats

    # Batch update census tracts
    batch_size = 500
    fips_list = list(ruca_data.keys())

    for i in range(0, len(fips_list), batch_size):
        batch_fips = fips_list[i:i + batch_size]

        for fips in batch_fips:
            values = ruca_data[fips]
            try:
                stmt = (
                    update(CensusTract)
                    .where(CensusTract.geoid == fips)
                    .values(**values)
                )
                result = await session.execute(stmt)
                if result.rowcount > 0:
                    stats["tracts_updated"] += 1
                else:
                    stats["tracts_not_found"] += 1
            except Exception as e:
                logger.error(f"Error updating tract {fips}: {e}")
                stats["errors"] += 1

        try:
            await session.commit()
            logger.info(f"  Updated batch {i // batch_size + 1} ({min(i + batch_size, len(fips_list))}/{len(fips_list)} tracts)")
        except Exception as e:
            logger.error(f"Error committing batch: {e}")
            await session.rollback()
            stats["errors"] += batch_size

    logger.info(
        f"RUCA load complete: {stats['tracts_updated']} updated, "
        f"{stats['tracts_not_found']} not found in DB, {stats['errors']} errors"
    )

    return stats
