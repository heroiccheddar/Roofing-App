"""CDC/ATSDR Social Vulnerability Index (SVI) loader.

Downloads and loads tract-level SVI data for disaster vulnerability
assessment and lead scoring enrichment.

Data source: CDC/ATSDR SVI 2022
https://www.atsdr.cdc.gov/place-health/php/svi/index.html
"""

import csv
import io
import logging
from typing import Optional

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract

logger = logging.getLogger(__name__)

SVI_CSV_URL = "https://raw.githubusercontent.com/lpiep/cdc-svi/main/csv/tract/SVI_2022_US.csv"
SVI_TIMEOUT = 120.0  # Large file download


async def load_svi_data(
    session: AsyncSession,
    state_fips_codes: list[str],
) -> dict:
    """Download CDC SVI CSV and update census tracts.

    Args:
        session: SQLAlchemy async session
        state_fips_codes: List of 2-digit state FIPS codes to filter

    Returns:
        Stats dict with tracts_matched, tracts_updated, tracts_not_found, errors
    """
    stats = {"tracts_matched": 0, "tracts_updated": 0, "tracts_not_found": 0, "errors": 0}

    # Download CSV
    logger.info(f"Downloading CDC SVI data from {SVI_CSV_URL}")
    try:
        async with httpx.AsyncClient(timeout=SVI_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(SVI_CSV_URL)
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to download SVI CSV: {e}")
        stats["errors"] = 1
        return stats

    csv_text = response.text
    # Remove BOM if present
    if csv_text.startswith('\ufeff'):
        csv_text = csv_text[1:]

    logger.info(f"Downloaded SVI CSV ({len(csv_text)} bytes)")

    # Parse CSV and filter to requested states
    reader = csv.DictReader(io.StringIO(csv_text))

    # Build FIPS → SVI data mapping for requested states
    # State FIPS in CSV is "ST" column (e.g., "01", "13")
    state_fips_set = set(state_fips_codes)
    svi_data = {}  # FIPS → {svi_overall, svi_socioeconomic, svi_housing_type}

    for row in reader:
        # The ST column may have leading zeros stripped; the FIPS column is the full tract GEOID
        fips = row.get("FIPS", "").strip()
        if not fips:
            continue

        # Check if this tract is in a requested state
        # FIPS format: SSCCCTTTTTT (2-digit state + 3-digit county + 6-digit tract)
        tract_state_fips = fips[:2]
        if tract_state_fips not in state_fips_set:
            continue

        # Parse SVI values (-999 = null)
        def parse_svi(val_str):
            try:
                val = float(val_str)
                return val if val >= 0 else None  # -999 → None
            except (ValueError, TypeError):
                return None

        svi_overall = parse_svi(row.get("RPL_THEMES", ""))
        svi_socioeconomic = parse_svi(row.get("RPL_THEME1", ""))
        svi_housing_type = parse_svi(row.get("RPL_THEME4", ""))

        svi_data[fips] = {
            "svi_overall": svi_overall,
            "svi_socioeconomic": svi_socioeconomic,
            "svi_housing_type": svi_housing_type,
        }

    logger.info(f"Parsed {len(svi_data)} tracts for states {state_fips_codes}")
    stats["tracts_matched"] = len(svi_data)

    if not svi_data:
        return stats

    # Batch update census tracts
    batch_size = 500
    fips_list = list(svi_data.keys())

    for i in range(0, len(fips_list), batch_size):
        batch_fips = fips_list[i:i + batch_size]

        for fips in batch_fips:
            values = svi_data[fips]
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
        f"SVI load complete: {stats['tracts_updated']} updated, "
        f"{stats['tracts_not_found']} not found in DB, {stats['errors']} errors"
    )

    return stats
