"""FEMA Disaster Declarations loader.

Fetches federal disaster declarations from the OpenFEMA API and maps them to census tracts.
Focuses on roofing-relevant incident types (storms, tornadoes, hurricanes, ice storms).

Data source: https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract

logger = logging.getLogger(__name__)

# OpenFEMA API configuration
FEMA_API_URL = "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
FEMA_TIMEOUT = 60.0
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0

# Incident types relevant to roofing damage
ROOFING_INCIDENT_TYPES = {
    "Severe Storm(s)",
    "Tornado",
    "Hurricane",
    "Severe Ice Storm",
}

# State abbreviation to FIPS code mapping
STATE_ABBR_TO_FIPS = {
    "TX": "48",
    "OK": "40",
    "KS": "20",
    "CO": "08",
    "NE": "31",
    "GA": "13",
    "AL": "01",
    "AR": "05",
    "FL": "12",
    "LA": "22",
    "MS": "28",
    "MO": "29",
    "NC": "37",
    "SC": "45",
    "TN": "47",
    "VA": "51",
}


def _parse_fema_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse FEMA API date string to datetime.

    FEMA dates come as ISO strings like "2023-05-15T00:00:00.000Z".

    Args:
        date_str: ISO format date string from FEMA API

    Returns:
        Parsed datetime with UTC timezone, or None if input is empty
    """
    if not date_str:
        return None
    # Handle "2023-05-15T00:00:00.000Z" format
    date_str = date_str.replace("Z", "+00:00")
    return datetime.fromisoformat(date_str)


async def fetch_fema_declarations(
    state_abbr: str,
    years_back: int = 10,
) -> list[dict]:
    """Fetch FEMA disaster declarations for a state via OpenFEMA API.

    Retrieves declarations from the last N years, filtered to roofing-relevant
    incident types. Handles pagination and retries.

    Args:
        state_abbr: Two-letter state abbreviation (e.g., "GA", "TX")
        years_back: Number of years to look back (default: 10)

    Returns:
        List of declaration dicts with fields:
        - disasterNumber
        - state
        - fipsStateCode
        - fipsCountyCode
        - incidentType
        - declarationDate
        - incidentBeginDate
        - incidentEndDate
        - designatedArea
        - declarationTitle

    Raises:
        httpx.HTTPError: If API request fails after retries
    """
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=years_back * 365)).strftime("%Y-%m-%d")

    # Build OData filter
    odata_filter = f"state eq '{state_abbr}' and incidentBeginDate ge '{cutoff_date}'"

    # Select specific fields
    select_fields = (
        "disasterNumber,state,fipsStateCode,fipsCountyCode,incidentType,"
        "declarationDate,incidentBeginDate,incidentEndDate,designatedArea,declarationTitle"
    )

    params = {
        "$filter": odata_filter,
        "$select": select_fields,
        "$top": 1000,
        "$skip": 0,
    }

    all_declarations = []

    logger.info(f"Fetching FEMA declarations for {state_abbr} since {cutoff_date}")

    async with httpx.AsyncClient(timeout=FEMA_TIMEOUT, follow_redirects=True) as client:
        while True:
            # Retry logic for API calls
            for attempt in range(MAX_RETRIES):
                try:
                    response = await client.get(FEMA_API_URL, params=params)
                    response.raise_for_status()
                    break
                except httpx.HTTPError as e:
                    if attempt == MAX_RETRIES - 1:
                        logger.error(f"Failed to fetch FEMA data after {MAX_RETRIES} attempts: {e}")
                        raise
                    logger.warning(f"Attempt {attempt + 1} failed, retrying in {RETRY_BACKOFF ** attempt}s: {e}")
                    await asyncio.sleep(RETRY_BACKOFF ** attempt)

            data = response.json()
            declarations = data.get("DisasterDeclarationsSummaries", [])

            if not declarations:
                break

            all_declarations.extend(declarations)

            # Check if there are more results to paginate
            if len(declarations) < params["$top"]:
                break

            params["$skip"] += params["$top"]
            logger.info(f"  Fetched {len(all_declarations)} declarations so far...")

    # Filter to roofing-relevant incident types
    filtered_declarations = [
        d for d in all_declarations
        if d.get("incidentType") in ROOFING_INCIDENT_TYPES
    ]

    # Log count per incident type
    incident_type_counts = {}
    for d in filtered_declarations:
        incident_type = d.get("incidentType")
        incident_type_counts[incident_type] = incident_type_counts.get(incident_type, 0) + 1

    logger.info(
        f"Fetched {len(filtered_declarations)} roofing-relevant declarations for {state_abbr} "
        f"(filtered from {len(all_declarations)} total)"
    )
    for incident_type, count in sorted(incident_type_counts.items()):
        logger.info(f"  {incident_type}: {count}")

    return filtered_declarations


def group_by_county(declarations: list[dict]) -> dict[str, list[dict]]:
    """Group disaster declarations by county FIPS code.

    FEMA API provides separate state and county FIPS codes:
    - fipsStateCode: 2 digits (e.g., "13" for GA)
    - fipsCountyCode: 3 digits (e.g., "067" for Forsyth County)
    - Full FIPS: concatenation "13067"

    Args:
        declarations: List of declaration dicts from FEMA API

    Returns:
        Dict mapping full county FIPS (5 digits) to list of declarations
    """
    county_groups = {}

    for decl in declarations:
        state_fips = decl.get("fipsStateCode", "").strip()
        county_fips = decl.get("fipsCountyCode", "").strip()

        if not state_fips or not county_fips:
            continue

        # Ensure county FIPS is 3 digits with leading zeros
        county_fips = county_fips.zfill(3)

        # Create full 5-digit county FIPS
        full_county_fips = f"{state_fips}{county_fips}"

        if full_county_fips not in county_groups:
            county_groups[full_county_fips] = []

        county_groups[full_county_fips].append(decl)

    logger.info(f"Grouped declarations into {len(county_groups)} counties")

    return county_groups


def compute_county_metrics(declarations: list[dict]) -> dict:
    """Compute disaster metrics for a single county.

    Calculates:
    - disaster_count: Count of unique disaster declarations
    - last_disaster_date: Most recent incident begin date
    - disaster_types: Sorted, deduplicated list of incident types
    - disaster_score: Recency-weighted score (0-100)
      Each disaster starts at 20 points and decays by 2 points per year
      Total capped at 100

    Args:
        declarations: List of declaration dicts for a single county

    Returns:
        Dict with keys: disaster_count, last_disaster_date, disaster_types, disaster_score
    """
    if not declarations:
        return {
            "disaster_count": 0,
            "last_disaster_date": None,
            "disaster_types": [],
            "disaster_score": 0.0,
        }

    # Deduplicate by disaster number (same disaster can span multiple counties)
    unique_disasters = {}
    for decl in declarations:
        disaster_num = decl.get("disasterNumber")
        if disaster_num and disaster_num not in unique_disasters:
            unique_disasters[disaster_num] = decl

    # Count unique disasters
    disaster_count = len(unique_disasters)

    # Find most recent incident date
    last_disaster_date = None
    for decl in declarations:
        begin_date = _parse_fema_date(decl.get("incidentBeginDate"))
        if begin_date and (last_disaster_date is None or begin_date > last_disaster_date):
            last_disaster_date = begin_date

    # Collect unique incident types
    disaster_types = sorted(set(
        decl.get("incidentType")
        for decl in declarations
        if decl.get("incidentType")
    ))

    # Compute disaster score (recency-weighted)
    now = datetime.now(timezone.utc)
    score = 0.0

    for decl in unique_disasters.values():
        begin_date = _parse_fema_date(decl.get("incidentBeginDate"))
        if not begin_date:
            continue

        years_ago = (now - begin_date).days / 365.25
        # 20 points for recent disaster, decays by 2 points per year over 10 years
        score += max(0, 20 - years_ago * 2)

    disaster_score = min(score, 100.0)

    return {
        "disaster_count": disaster_count,
        "last_disaster_date": last_disaster_date,
        "disaster_types": disaster_types,
        "disaster_score": disaster_score,
    }


async def bulk_update_fema_data(
    session: AsyncSession,
    state_fips: str,
    county_metrics: dict[str, dict],
    batch_size: int = 500,
) -> dict:
    """Bulk update census tracts with FEMA disaster data.

    For each county, finds all census tracts in that county and updates them
    with the county's disaster metrics. All tracts in the same county get
    the same values.

    Args:
        session: Async database session
        state_fips: 2-digit state FIPS code
        county_metrics: Dict mapping county FIPS (5 digits) to computed metrics
        batch_size: Number of tracts to update per batch

    Returns:
        Dict with counts:
        - counties_updated: Number of counties processed
        - tracts_updated: Number of tracts updated
        - errors: Number of errors encountered
    """
    if not county_metrics:
        return {"counties_updated": 0, "tracts_updated": 0, "errors": 0}

    logger.info(f"Updating census tracts for {len(county_metrics)} counties in state {state_fips}")

    counties_updated = 0
    tracts_updated = 0
    errors = 0

    for full_county_fips, metrics in county_metrics.items():
        try:
            # Extract county FIPS (last 3 digits of full FIPS)
            county_fips = full_county_fips[-3:]

            # Find all tracts in this county
            stmt = select(CensusTract.geoid).where(
                CensusTract.state_fips == state_fips,
                CensusTract.county_fips == county_fips,
            )
            result = await session.execute(stmt)
            tract_geoids = [row[0] for row in result.fetchall()]

            if not tract_geoids:
                logger.warning(f"No tracts found for county {full_county_fips}")
                continue

            # Update all tracts in this county with the same metrics
            update_values = {
                "fema_disaster_count": metrics["disaster_count"],
                "fema_last_disaster_date": metrics["last_disaster_date"],
                "fema_disaster_types": metrics["disaster_types"],
                "fema_disaster_score": metrics["disaster_score"],
            }

            # Process in batches to avoid huge queries
            for batch_start in range(0, len(tract_geoids), batch_size):
                batch_geoids = tract_geoids[batch_start:batch_start + batch_size]

                update_stmt = (
                    update(CensusTract)
                    .where(CensusTract.geoid.in_(batch_geoids))
                    .values(**update_values)
                )

                result = await session.execute(update_stmt)
                tracts_updated += result.rowcount

            await session.commit()
            counties_updated += 1

            logger.info(
                f"  Updated {len(tract_geoids)} tracts for county {full_county_fips} "
                f"(score: {metrics['disaster_score']:.1f}, count: {metrics['disaster_count']})"
            )

        except Exception as e:
            logger.error(f"Error updating county {full_county_fips}: {e}", exc_info=True)
            await session.rollback()
            errors += 1

    logger.info(
        f"Bulk update complete: {counties_updated} counties, "
        f"{tracts_updated} tracts updated, {errors} errors"
    )

    return {
        "counties_updated": counties_updated,
        "tracts_updated": tracts_updated,
        "errors": errors,
    }


async def load_fema_disasters(
    state_abbrevs: list[str],
    session: AsyncSession,
    years_back: int = 10,
) -> dict:
    """Load FEMA disaster declarations for multiple states.

    Orchestrates the full process:
    1. Fetch declarations from OpenFEMA API for each state
    2. Group by county
    3. Compute disaster metrics per county
    4. Bulk update census tracts with county-level metrics

    Args:
        state_abbrevs: List of 2-letter state abbreviations (e.g., ["GA", "TX"])
        session: Async database session
        years_back: Number of years to look back for disasters (default: 10)

    Returns:
        Dict with aggregate stats:
        - states_processed: Number of states processed
        - total_declarations: Total declarations fetched
        - total_counties: Total counties with disasters
        - tracts_updated: Total tracts updated
        - errors: Total errors encountered

    Example:
        >>> result = await load_fema_disasters(["GA", "TX"], session)
        >>> print(f"Updated {result['tracts_updated']} tracts with FEMA data")
    """
    stats = {
        "states_processed": 0,
        "total_declarations": 0,
        "total_counties": 0,
        "tracts_updated": 0,
        "errors": 0,
    }

    for state_abbr in state_abbrevs:
        state_abbr = state_abbr.upper().strip()

        if state_abbr not in STATE_ABBR_TO_FIPS:
            logger.warning(f"Unknown state abbreviation: {state_abbr}, skipping")
            stats["errors"] += 1
            continue

        state_fips = STATE_ABBR_TO_FIPS[state_abbr]

        try:
            logger.info(f"Processing state: {state_abbr} (FIPS: {state_fips})")

            # Fetch declarations for this state
            declarations = await fetch_fema_declarations(state_abbr, years_back)
            stats["total_declarations"] += len(declarations)

            if not declarations:
                logger.info(f"No roofing-relevant disasters found for {state_abbr}")
                stats["states_processed"] += 1
                continue

            # Group by county
            county_groups = group_by_county(declarations)
            stats["total_counties"] += len(county_groups)

            # Compute metrics for each county
            county_metrics = {}
            for county_fips, county_declarations in county_groups.items():
                county_metrics[county_fips] = compute_county_metrics(county_declarations)

            # Bulk update tracts
            update_result = await bulk_update_fema_data(
                session,
                state_fips,
                county_metrics,
            )

            stats["tracts_updated"] += update_result["tracts_updated"]
            stats["errors"] += update_result["errors"]
            stats["states_processed"] += 1

        except Exception as e:
            logger.error(f"Error processing state {state_abbr}: {e}", exc_info=True)
            stats["errors"] += 1

    logger.info(f"FEMA disaster load complete: {stats}")
    return stats


# Import asyncio for sleep in retry logic
import asyncio
