"""FEMA Flood Hazard data loader.

Loads flood risk data from the FEMA National Risk Index (NRI) CSV.
Uses the same NRI dataset as nri_loader.py but extracts riverine flooding columns.

Data source: https://hazards.fema.gov/nri/data-resources
"""

import csv
import io
import logging
import tempfile
import zipfile
from pathlib import Path

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract

logger = logging.getLogger(__name__)

NRI_CSV_URL = "https://www.fema.gov/about/reports-and-data/openfema/nri/v120/NRI_Table_CensusTracts.zip"

# NRI risk rating → simplified category
FLOOD_RISK_MAP = {
    "Very High": "high",
    "Relatively High": "high",
    "Relatively Moderate": "moderate",
    "Relatively Low": "low",
    "Very Low": "minimal",
    "No Rating": None,
    "Not Applicable": None,
}

# Whether flood insurance is typically required
INSURANCE_REQUIRED = {
    "high": True,
    "moderate": False,
    "low": False,
    "minimal": False,
}


async def load_flood_hazard_data(
    session: AsyncSession,
    state_fips_codes: list[str],
) -> dict:
    """Download NRI data and extract flood risk for census tracts.

    Args:
        session: SQLAlchemy async session
        state_fips_codes: List of 2-digit state FIPS codes to filter

    Returns:
        Stats dict with tracts_matched, tracts_updated, errors
    """
    stats = {
        "tracts_matched": 0,
        "tracts_updated": 0,
        "tracts_not_found": 0,
        "errors": 0,
    }

    state_fips_set = set(state_fips_codes)

    # Download NRI ZIP
    logger.info(f"Downloading NRI ZIP from {NRI_CSV_URL}")
    tmpdir = tempfile.mkdtemp(prefix="nri_flood_")
    tmpdir_path = Path(tmpdir)
    zip_path = tmpdir_path / "NRI_Table_CensusTracts.zip"

    try:
        async with httpx.AsyncClient(timeout=600.0, follow_redirects=True) as client:
            async with client.stream("GET", NRI_CSV_URL) as response:
                response.raise_for_status()
                total_bytes = 0
                with open(zip_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
                        total_bytes += len(chunk)
                        if total_bytes % (10 * 1024 * 1024) < 1024 * 1024:
                            logger.info(f"  Downloaded {total_bytes / (1024 * 1024):.1f} MB")

        logger.info(f"Download complete: {total_bytes / (1024 * 1024):.1f} MB")

        # Extract ZIP
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmpdir_path)
        zip_path.unlink()

        # Find the CSV
        csv_files = list(tmpdir_path.glob("*.csv"))
        csv_path = None
        for f in csv_files:
            if "CensusTracts" in f.name or "Table" in f.name:
                csv_path = f
                break
        if csv_path is None:
            csv_path = max(csv_files, key=lambda f: f.stat().st_size)

        logger.info(f"Parsing flood data from {csv_path.name}")

        # Parse CSV and extract flood columns
        flood_data = {}  # geoid -> {flood_zone_code, flood_risk_category, flood_insurance_required}

        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                tract_fips = row.get("TRACTFIPS", "").strip()
                if not tract_fips or len(tract_fips) < 5:
                    continue

                # Filter by state FIPS
                if tract_fips[:2] not in state_fips_set:
                    continue

                # Get flood risk ratings — NRI has CFLD (coastal) and IFLD (inland)
                # Use the higher-risk of the two for each tract
                cfld_riskr = row.get("CFLD_RISKR", "").strip()
                ifld_riskr = row.get("IFLD_RISKR", "").strip()

                # Pick the higher-risk rating between coastal and inland
                risk_order = {"Very High": 5, "Relatively High": 4, "Relatively Moderate": 3,
                              "Relatively Low": 2, "Very Low": 1}
                best_rating = None
                best_score = 0
                for rating in (cfld_riskr, ifld_riskr):
                    if rating and rating in risk_order and risk_order[rating] > best_score:
                        best_rating = rating
                        best_score = risk_order[rating]

                if not best_rating:
                    continue

                risk_category = FLOOD_RISK_MAP.get(best_rating)
                if risk_category is None:
                    continue

                flood_data[tract_fips] = {
                    "flood_zone_code": best_rating,
                    "flood_risk_category": risk_category,
                    "flood_insurance_required": INSURANCE_REQUIRED.get(risk_category, False),
                }

        logger.info(f"Parsed {len(flood_data)} tracts with flood risk data for states {state_fips_codes}")
        stats["tracts_matched"] = len(flood_data)

        if not flood_data:
            return stats

        # Batch update census tracts
        batch_size = 500
        fips_list = list(flood_data.keys())

        for i in range(0, len(fips_list), batch_size):
            batch_fips = fips_list[i:i + batch_size]

            for fips in batch_fips:
                values = flood_data[fips]
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
            f"Flood hazard load complete: {stats['tracts_updated']} updated, "
            f"{stats['tracts_not_found']} not found in DB, {stats['errors']} errors"
        )

    except Exception as e:
        logger.error(f"Error loading flood hazard data: {e}", exc_info=True)
        stats["errors"] += 1
    finally:
        # Clean up temp directory
        import shutil
        if tmpdir_path.exists():
            shutil.rmtree(tmpdir_path, ignore_errors=True)

    return stats
