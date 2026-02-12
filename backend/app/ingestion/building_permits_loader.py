"""Census Building Permits Survey (BPS) loader.

Downloads annual county-level building permits data and maps it to census tracts.
All tracts in the same county inherit the county's permit data.

Data source: US Census Bureau Building Permits Survey
https://www.census.gov/construction/bps/
Download: https://www2.census.gov/econ/bps/County/co{year}a.txt
"""

import csv
import io
import logging

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract

logger = logging.getLogger(__name__)

BPS_URL_PATTERN = "https://www2.census.gov/econ/bps/County/co{year}a.txt"
BPS_TIMEOUT = 60.0


def _safe_int(value: str) -> int:
    """Parse a string to int, handling empty/invalid values."""
    if not value or not value.strip():
        return 0
    try:
        return int(value.strip())
    except (ValueError, TypeError):
        return 0


def _safe_float(value: str) -> float:
    """Parse a string to float, handling empty/invalid values."""
    if not value or not value.strip():
        return 0.0
    try:
        return float(value.strip())
    except (ValueError, TypeError):
        return 0.0


async def load_building_permits(
    session: AsyncSession,
    state_fips_codes: list[str],
    year: int = 2024,
) -> dict:
    """Download Census BPS annual county data and update census tracts.

    Args:
        session: SQLAlchemy async session
        state_fips_codes: List of 2-digit state FIPS codes to filter
        year: BPS survey year (default: 2024, most recent annual)

    Returns:
        Stats dict with counties_matched, tracts_updated, errors
    """
    stats = {
        "counties_matched": 0,
        "tracts_updated": 0,
        "counties_not_found": 0,
        "errors": 0,
    }

    url = BPS_URL_PATTERN.format(year=year)
    logger.info(f"Downloading BPS data from {url}")

    try:
        async with httpx.AsyncClient(timeout=BPS_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to download BPS CSV: {e}")
        stats["errors"] = 1
        return stats

    csv_text = response.text
    if csv_text.startswith('\ufeff'):
        csv_text = csv_text[1:]

    logger.info(f"Downloaded BPS CSV ({len(csv_text)} bytes)")

    # Parse CSV — columns are:
    # Survey Date, FIPS State, FIPS County, Region Code, Division Code, County Name,
    # 1-unit Bldgs, 1-unit Units, 1-unit Value,
    # 2-units Bldgs, 2-units Units, 2-units Value,
    # 3-4 units Bldgs, 3-4 units Units, 3-4 units Value,
    # 5+ units Bldgs, 5+ units Units, 5+ units Value,
    # (then "rep" reported versions of the same)
    reader = csv.reader(io.StringIO(csv_text))

    state_fips_set = set(state_fips_codes)
    county_data = {}  # county_fips_3digit -> {metrics}

    for row in reader:
        if len(row) < 18:
            continue

        # Skip header row
        survey_date = row[0].strip()
        if not survey_date.isdigit():
            continue

        state_fips = row[1].strip().zfill(2)
        county_fips = row[2].strip().zfill(3)

        # Filter by state
        if state_fips not in state_fips_set:
            continue

        # Parse building permit counts
        sf_buildings = _safe_int(row[6])    # 1-unit buildings
        sf_units = _safe_int(row[7])        # 1-unit units
        sf_value = _safe_float(row[8])      # 1-unit value ($)

        two_unit_bldgs = _safe_int(row[9])
        three_four_bldgs = _safe_int(row[12])
        five_plus_bldgs = _safe_int(row[15])

        two_unit_value = _safe_float(row[11])
        three_four_value = _safe_float(row[14])
        five_plus_value = _safe_float(row[17])

        all_permits = sf_buildings + two_unit_bldgs + three_four_bldgs + five_plus_bldgs
        total_value = sf_value + two_unit_value + three_four_value + five_plus_value

        county_name = row[5].strip()

        county_data[county_fips] = {
            "state_fips": state_fips,
            "county_name": county_name,
            "bps_single_family_permits": sf_buildings,
            "bps_all_permits": all_permits,
            "bps_total_value": total_value,
            "bps_survey_year": int(survey_date),
        }

    logger.info(f"Parsed {len(county_data)} counties for states {state_fips_codes}")

    if not county_data:
        return stats

    # Update all tracts in each county
    for county_fips, metrics in county_data.items():
        state_fips = metrics["state_fips"]
        county_name = metrics["county_name"]

        try:
            # Find all tracts in this county
            stmt = select(CensusTract.geoid).where(
                CensusTract.state_fips == state_fips,
                CensusTract.county_fips == county_fips,
            )
            result = await session.execute(stmt)
            tract_geoids = [row[0] for row in result.fetchall()]

            if not tract_geoids:
                logger.debug(f"No tracts found for county {state_fips}{county_fips} ({county_name})")
                stats["counties_not_found"] += 1
                continue

            # Update all tracts in this county with the same permit data
            update_values = {
                "bps_single_family_permits": metrics["bps_single_family_permits"],
                "bps_all_permits": metrics["bps_all_permits"],
                "bps_total_value": metrics["bps_total_value"],
                "bps_survey_year": metrics["bps_survey_year"],
            }

            update_stmt = (
                update(CensusTract)
                .where(CensusTract.geoid.in_(tract_geoids))
                .values(**update_values)
            )
            result = await session.execute(update_stmt)
            stats["tracts_updated"] += result.rowcount
            stats["counties_matched"] += 1

        except Exception as e:
            logger.error(f"Error updating county {state_fips}{county_fips}: {e}")
            stats["errors"] += 1

    try:
        await session.commit()
    except Exception as e:
        logger.error(f"Error committing: {e}")
        await session.rollback()
        stats["errors"] += 1

    logger.info(
        f"BPS load complete: {stats['counties_matched']} counties, "
        f"{stats['tracts_updated']} tracts updated, "
        f"{stats['counties_not_found']} counties not in DB, "
        f"{stats['errors']} errors"
    )

    return stats
