"""Redfin Housing Market Data loader.

Downloads ZIP-code-level housing market metrics from Redfin's public data repository
and allocates them to census tracts using the Census Bureau ZCTA-to-Tract relationship file.

Data sources:
- Redfin Market Tracker: https://redfin-public-data.s3.us-west-2.amazonaws.com/redfin_market_tracker/zip_code_market_tracker.tsv000.gz
- Census ZCTA-Tract Crosswalk: https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_tract20_natl.txt

Methodology:
1. Download Census ZCTA-Tract relationship file with land area overlap ratios
2. Stream Redfin's large TSV.gz file (200MB+ compressed)
3. Extract latest monthly metrics per ZIP for target states
4. Allocate ZIP-level metrics to census tracts using land area overlap ratios
5. Batch update census_tracts table with housing market data

Housing metrics loaded:
- Median sale price ($)
- Median days on market
- Active inventory count
- Price drop percentage
- Data month (YYYY-MM format)
"""

import asyncio
import csv
import gzip
import io
import logging
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.census_tract import CensusTract

logger = logging.getLogger(__name__)

# Census Bureau ZCTA-to-Tract relationship file (free, no login required)
CENSUS_ZCTA_TRACT_URL = "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_tract20_natl.txt"

# Redfin ZIP-code market tracker
REDFIN_TSV_URL = "https://redfin-public-data.s3.us-west-2.amazonaws.com/redfin_market_tracker/zip_code_market_tracker.tsv000.gz"

# HTTP client settings
HTTP_TIMEOUT = 600.0  # 10 minutes for large file downloads
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0

# Database batch size
BATCH_SIZE = 500

# State FIPS to abbreviation mapping
STATE_FIPS_TO_ABBR = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
    "56": "WY", "72": "PR",
}


class RedfinDataError(Exception):
    """Exception raised for Redfin data loading errors."""
    pass


async def download_zcta_crosswalk(max_retries: int = MAX_RETRIES) -> str:
    """Download Census Bureau ZCTA-to-Tract relationship file.

    Free, no login required. Pipe-delimited text file (~24MB).

    Args:
        max_retries: Number of retry attempts (default: 3)

    Returns:
        File content as text string

    Raises:
        RedfinDataError: If download fails
    """
    logger.info("Downloading Census ZCTA-Tract relationship file")

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        for attempt in range(max_retries):
            try:
                response = await client.get(CENSUS_ZCTA_TRACT_URL)
                response.raise_for_status()

                text = response.text
                logger.info(
                    f"  Downloaded ZCTA-Tract crosswalk: {len(text)} chars "
                    f"({len(text) / (1024 * 1024):.1f} MB)"
                )
                return text

            except httpx.HTTPError as e:
                if attempt == max_retries - 1:
                    raise RedfinDataError(f"Failed to download ZCTA crosswalk: {e}") from e
                wait_time = RETRY_BACKOFF ** attempt
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed, retrying in {wait_time:.1f}s: {e}")
                await asyncio.sleep(wait_time)

    raise RedfinDataError("Failed to download ZCTA crosswalk")


def parse_zcta_crosswalk(
    text: str,
    state_fips_codes: list[str],
) -> dict[str, list[tuple[str, float]]]:
    """Parse Census ZCTA-to-Tract relationship file.

    Uses land area overlap ratios (AREALAND_PART / AREALAND_ZCTA5_20) as
    allocation weights. This approximates residential ratios for ZIP-to-tract
    allocation of housing market data.

    File format: pipe-delimited with columns including:
    - GEOID_ZCTA5_20: 5-digit ZCTA (≈ZIP) code
    - GEOID_TRACT_20: 11-digit census tract GEOID
    - AREALAND_ZCTA5_20: total land area of the ZCTA
    - AREALAND_PART: land area of the ZCTA-tract intersection

    Args:
        text: File content as text
        state_fips_codes: List of 2-digit state FIPS codes to include

    Returns:
        Dict mapping ZIP code -> list of (tract_geoid, area_ratio) tuples
    """
    logger.info(f"Parsing ZCTA crosswalk for states: {', '.join(state_fips_codes)}")

    zip_to_tracts: dict[str, list[tuple[str, float]]] = {}
    rows_parsed = 0
    rows_skipped = 0

    reader = csv.DictReader(io.StringIO(text), delimiter="|")

    for row in reader:
        try:
            zcta = (row.get("\ufeffGEOID_ZCTA5_20") or row.get("GEOID_ZCTA5_20") or "").strip()
            tract_geoid = (row.get("GEOID_TRACT_20") or "").strip()
            area_zcta_str = (row.get("AREALAND_ZCTA5_20") or "").strip()
            area_part_str = (row.get("AREALAND_PART") or "").strip()

            # Skip rows with missing key fields
            if not zcta or not tract_geoid or not area_zcta_str or not area_part_str:
                rows_skipped += 1
                continue

            # Filter by state FIPS (first 2 digits of tract GEOID)
            tract_state = tract_geoid[:2]
            if tract_state not in state_fips_codes:
                rows_skipped += 1
                continue

            # Compute area-based allocation ratio
            area_zcta = int(area_zcta_str)
            area_part = int(area_part_str)

            if area_zcta <= 0:
                rows_skipped += 1
                continue

            ratio = area_part / area_zcta

            if ratio <= 0:
                rows_skipped += 1
                continue

            # Ensure ZIP is 5 digits
            zcta = zcta.zfill(5)

            if zcta not in zip_to_tracts:
                zip_to_tracts[zcta] = []

            zip_to_tracts[zcta].append((tract_geoid, ratio))
            rows_parsed += 1

        except (ValueError, TypeError, KeyError) as e:
            rows_skipped += 1
            logger.debug(f"Skipping row due to parsing error: {e}")
            continue

    logger.info(
        f"Parsed ZCTA crosswalk: {rows_parsed} ZCTA-tract mappings for {len(zip_to_tracts)} ZCTAs "
        f"({rows_skipped} rows skipped)"
    )

    return zip_to_tracts


async def stream_redfin_tsv(
    state_fips_codes: list[str],
    max_retries: int = MAX_RETRIES,
) -> dict[str, dict[str, Any]]:
    """Stream and parse Redfin ZIP-code market tracker TSV.gz file.

    Downloads and decompresses the large TSV.gz file (~200MB compressed) in streaming mode
    to avoid loading entire file into memory. Extracts latest monthly data per ZIP for
    target states only.

    Args:
        state_fips_codes: List of 2-digit state FIPS codes to include
        max_retries: Number of retry attempts (default: 3)

    Returns:
        Dict mapping ZIP code -> latest monthly metrics dict
        Example: {
            "30309": {
                "median_sale_price": 550000.0,
                "median_dom": 25.0,
                "inventory": 45,
                "price_drop_pct": 12.5,
                "data_month": "2025-12",
            }
        }

    Raises:
        RedfinDataError: If download or parsing fails
    """
    logger.info("Downloading and streaming Redfin ZIP-code market tracker")

    # Convert state FIPS to abbreviations for filtering
    target_states = {STATE_FIPS_TO_ABBR[fips] for fips in state_fips_codes if fips in STATE_FIPS_TO_ABBR}
    logger.info(f"  Filtering to states: {', '.join(sorted(target_states))}")

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        for attempt in range(max_retries):
            try:
                # Stream the response
                async with client.stream("GET", REDFIN_TSV_URL) as response:
                    response.raise_for_status()

                    logger.info(f"  Streaming TSV.gz file (this may take a few minutes)...")

                    # Read entire compressed content into memory for gzip decompression
                    # (httpx streaming + gzip streaming is complex, so we download first)
                    compressed_data = b""
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):  # 1MB chunks
                        compressed_data += chunk

                    logger.info(
                        f"  Downloaded {len(compressed_data)} bytes "
                        f"({len(compressed_data) / (1024 * 1024):.2f} MB compressed)"
                    )

                # Decompress and parse TSV
                logger.info("  Decompressing and parsing TSV...")
                return parse_redfin_tsv(compressed_data, target_states)

            except httpx.HTTPError as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to download Redfin TSV after {max_retries} attempts: {e}")
                    raise RedfinDataError(f"Failed to download Redfin TSV: {e}") from e

                wait_time = RETRY_BACKOFF ** attempt
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed, retrying in {wait_time:.1f}s: {e}")
                await asyncio.sleep(wait_time)

            except Exception as e:
                logger.error(f"Unexpected error streaming Redfin TSV: {e}", exc_info=True)
                raise RedfinDataError(f"Error processing Redfin TSV: {e}") from e

    # Should never reach here
    raise RedfinDataError("Unexpected error in stream_redfin_tsv")


def parse_redfin_tsv(
    compressed_data: bytes,
    target_states: set[str],
) -> dict[str, dict[str, Any]]:
    """Parse decompressed Redfin TSV data.

    Extracts latest monthly metrics per ZIP for target states.
    Keeps only the most recent month's data for each ZIP.

    Args:
        compressed_data: Gzip-compressed TSV bytes
        target_states: Set of state abbreviations to include (e.g., {"GA", "FL"})

    Returns:
        Dict mapping ZIP code -> latest monthly metrics
    """
    zip_data = {}
    rows_parsed = 0
    rows_skipped = 0

    try:
        # Decompress gzip data
        decompressed_data = gzip.decompress(compressed_data)
        logger.info(f"  Decompressed to {len(decompressed_data)} bytes ({len(decompressed_data) / (1024 * 1024):.2f} MB)")

        # Parse TSV
        tsv_text = decompressed_data.decode("utf-8")
        reader = csv.DictReader(io.StringIO(tsv_text), delimiter="\t")

        # Log available columns and build case-insensitive lookup
        if reader.fieldnames:
            logger.info(f"  TSV columns: {', '.join(reader.fieldnames[:15])}...")

        # Helper: case-insensitive row getter
        def get(row: dict, key: str) -> str:
            return (row.get(key) or row.get(key.upper()) or row.get(key.lower()) or "").strip()

        for row in reader:
            try:
                # Filter: target states only
                state_code = get(row, "state_code") or get(row, "state")
                if state_code not in target_states:
                    rows_skipped += 1
                    continue

                # Filter: "All Residential" property type for aggregate stats
                property_type = get(row, "property_type")
                if property_type != "All Residential":
                    rows_skipped += 1
                    continue

                # Extract ZIP code from REGION field (format: "Zip Code: 30309")
                region_raw = get(row, "region")
                zip_code = region_raw.replace("Zip Code: ", "").strip() if region_raw else ""
                if not zip_code or len(zip_code) != 5 or not zip_code.isdigit():
                    rows_skipped += 1
                    continue

                # Extract period_begin for data month
                period_begin = get(row, "period_begin")
                if not period_begin:
                    rows_skipped += 1
                    continue

                # Parse date to YYYY-MM format
                try:
                    data_month = datetime.strptime(period_begin, "%Y-%m-%d").strftime("%Y-%m")
                except ValueError:
                    rows_skipped += 1
                    continue

                # Extract metrics (handle missing/empty values)
                def parse_float(value: str) -> float | None:
                    if not value or value.strip() == "":
                        return None
                    try:
                        return float(value)
                    except ValueError:
                        return None

                def parse_int(value: str) -> int | None:
                    if not value or value.strip() == "":
                        return None
                    try:
                        return int(float(value))  # Handle "123.0" format
                    except ValueError:
                        return None

                median_sale_price = parse_float(get(row, "median_sale_price"))
                median_dom = parse_float(get(row, "median_dom"))
                inventory = parse_int(get(row, "inventory"))
                price_drops = parse_float(get(row, "price_drops"))  # Fraction 0-1

                # Convert price_drops from fraction to percentage
                price_drop_pct = (price_drops * 100.0) if price_drops is not None else None

                # Check if we already have data for this ZIP
                if zip_code in zip_data:
                    # Keep the most recent month
                    existing_month = zip_data[zip_code]["data_month"]
                    if data_month > existing_month:
                        # This month is more recent, replace
                        zip_data[zip_code] = {
                            "median_sale_price": median_sale_price,
                            "median_dom": median_dom,
                            "inventory": inventory,
                            "price_drop_pct": price_drop_pct,
                            "data_month": data_month,
                        }
                else:
                    # First entry for this ZIP
                    zip_data[zip_code] = {
                        "median_sale_price": median_sale_price,
                        "median_dom": median_dom,
                        "inventory": inventory,
                        "price_drop_pct": price_drop_pct,
                        "data_month": data_month,
                    }

                rows_parsed += 1

            except Exception as e:
                rows_skipped += 1
                logger.debug(f"Skipping row due to parsing error: {e}")
                continue

        logger.info(
            f"Parsed Redfin TSV: {len(zip_data)} ZIPs with market data "
            f"({rows_parsed} rows parsed, {rows_skipped} rows skipped)"
        )

        # Log data month range
        if zip_data:
            months = {data["data_month"] for data in zip_data.values()}
            logger.info(f"  Data months: {min(months)} to {max(months)}")

        return zip_data

    except Exception as e:
        raise RedfinDataError(f"Failed to parse Redfin TSV: {e}") from e


def allocate_zip_to_tracts(
    zip_data: dict[str, dict[str, Any]],
    zip_to_tracts: dict[str, list[tuple[str, float]]],
) -> dict[str, dict[str, Any]]:
    """Allocate ZIP-level metrics to census tracts using residential ratios.

    For each tract, computes weighted averages/sums of metrics from all ZIPs
    that map to it, using the HUD residential allocation ratios as weights.

    Methodology:
    - For inventory: sum weighted values (additive metric)
    - For median_sale_price, median_dom, price_drop_pct: weighted average

    Args:
        zip_data: Dict mapping ZIP -> metrics dict
        zip_to_tracts: Dict mapping ZIP -> list of (tract_geoid, res_ratio)

    Returns:
        Dict mapping tract GEOID -> allocated metrics dict
        Example: {
            "13121000100": {
                "redfin_median_sale_price": 525000.0,
                "redfin_median_dom": 28.5,
                "redfin_inventory": 12,
                "redfin_price_drop_pct": 10.2,
                "redfin_data_month": "2025-12",
            }
        }
    """
    logger.info("Allocating ZIP-level metrics to census tracts")

    # Accumulator for weighted contributions per tract
    tract_accumulator = {}

    for zip_code, metrics in zip_data.items():
        # Get all tracts mapped to this ZIP
        tract_mappings = zip_to_tracts.get(zip_code, [])

        if not tract_mappings:
            continue

        for tract_geoid, res_ratio in tract_mappings:
            if tract_geoid not in tract_accumulator:
                tract_accumulator[tract_geoid] = {
                    "median_sale_price_sum": 0.0,
                    "median_dom_sum": 0.0,
                    "inventory_sum": 0,
                    "price_drop_pct_sum": 0.0,
                    "total_weight": 0.0,
                    "data_months": set(),
                }

            acc = tract_accumulator[tract_geoid]

            # Add weighted contributions
            if metrics["median_sale_price"] is not None:
                acc["median_sale_price_sum"] += metrics["median_sale_price"] * res_ratio

            if metrics["median_dom"] is not None:
                acc["median_dom_sum"] += metrics["median_dom"] * res_ratio

            if metrics["inventory"] is not None:
                acc["inventory_sum"] += int(metrics["inventory"] * res_ratio)

            if metrics["price_drop_pct"] is not None:
                acc["price_drop_pct_sum"] += metrics["price_drop_pct"] * res_ratio

            acc["total_weight"] += res_ratio
            acc["data_months"].add(metrics["data_month"])

    # Compute final tract-level metrics
    tract_data = {}

    for tract_geoid, acc in tract_accumulator.items():
        weight = acc["total_weight"]

        if weight <= 0:
            continue

        # Compute weighted averages (divide by total weight)
        median_sale_price = acc["median_sale_price_sum"] / weight if acc["median_sale_price_sum"] > 0 else None
        median_dom = acc["median_dom_sum"] / weight if acc["median_dom_sum"] > 0 else None
        price_drop_pct = acc["price_drop_pct_sum"] / weight if acc["price_drop_pct_sum"] > 0 else None

        # Inventory is additive (sum)
        inventory = acc["inventory_sum"] if acc["inventory_sum"] > 0 else None

        # Use the most recent data month
        data_month = max(acc["data_months"]) if acc["data_months"] else None

        tract_data[tract_geoid] = {
            "redfin_median_sale_price": median_sale_price,
            "redfin_median_dom": median_dom,
            "redfin_inventory": inventory,
            "redfin_price_drop_pct": price_drop_pct,
            "redfin_data_month": data_month,
        }

    logger.info(f"Allocated Redfin data to {len(tract_data)} census tracts")

    return tract_data


async def bulk_update_tracts(
    session: AsyncSession,
    tract_data: dict[str, dict[str, Any]],
    batch_size: int = BATCH_SIZE,
) -> dict[str, int]:
    """Bulk update census tracts with Redfin housing market data.

    Issues batched UPDATE statements to set Redfin columns.
    Tracts not found in the database are skipped silently.

    Args:
        session: Async database session
        tract_data: Dict mapping tract GEOID -> Redfin metrics dict
        batch_size: Number of tracts to update per batch (default: 500)

    Returns:
        Dict with counts:
        - updated: Number of tracts successfully updated
        - errors: Number of errors encountered
    """
    if not tract_data:
        return {"updated": 0, "errors": 0}

    logger.info(f"Bulk updating {len(tract_data)} census tracts with Redfin data (batch_size={batch_size})")

    updated_count = 0
    error_count = 0

    # Convert to list for batching
    geoid_list = list(tract_data.keys())

    for batch_start in range(0, len(geoid_list), batch_size):
        batch_geoids = geoid_list[batch_start:batch_start + batch_size]

        try:
            # Update each tract in the batch
            for geoid in batch_geoids:
                metrics = tract_data[geoid]

                update_stmt = (
                    update(CensusTract)
                    .where(CensusTract.geoid == geoid)
                    .values(
                        redfin_median_sale_price=metrics["redfin_median_sale_price"],
                        redfin_median_dom=metrics["redfin_median_dom"],
                        redfin_inventory=metrics["redfin_inventory"],
                        redfin_price_drop_pct=metrics["redfin_price_drop_pct"],
                        redfin_data_month=metrics["redfin_data_month"],
                    )
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


async def load_redfin_data(
    session: AsyncSession,
    state_fips_codes: list[str],
) -> dict[str, Any]:
    """Load Redfin housing market data and update census tracts.

    Orchestrates the full process:
    1. Download HUD ZIP-Tract crosswalk
    2. Parse crosswalk to get ZIP-to-Tract mappings with residential ratios
    3. Stream and parse Redfin ZIP-code market tracker TSV.gz
    4. Allocate ZIP-level metrics to tracts using residential ratios
    5. Bulk update census_tracts table

    Args:
        session: Async database session
        state_fips_codes: List of 2-digit state FIPS codes (e.g., ["13", "12"])

    Returns:
        Dict with stats:
        - zips_matched: Number of ZIPs with Redfin data
        - tracts_matched: Number of tracts with allocated data
        - tracts_updated: Number of tracts successfully updated in DB
        - errors: Number of errors encountered

    Example:
        >>> result = await load_redfin_data(session, state_fips_codes=["13"])
        >>> print(f"Updated {result['tracts_updated']} Georgia tracts with Redfin data")
    """
    logger.info(f"Starting Redfin housing market data load for states: {', '.join(state_fips_codes)}")

    stats = {
        "zips_matched": 0,
        "tracts_matched": 0,
        "tracts_updated": 0,
        "errors": 0,
    }

    try:
        # Step 1 & 2: Download and parse Census ZCTA-Tract crosswalk
        crosswalk_text = await download_zcta_crosswalk()
        zip_to_tracts = parse_zcta_crosswalk(crosswalk_text, state_fips_codes)

        if not zip_to_tracts:
            logger.warning("No ZIP-Tract mappings found in HUD crosswalk")
            return stats

        # Step 3: Stream and parse Redfin TSV
        zip_data = await stream_redfin_tsv(state_fips_codes)
        stats["zips_matched"] = len(zip_data)

        if not zip_data:
            logger.warning("No Redfin ZIP data found for target states")
            return stats

        # Step 4: Allocate ZIP metrics to tracts
        tract_data = allocate_zip_to_tracts(zip_data, zip_to_tracts)
        stats["tracts_matched"] = len(tract_data)

        if not tract_data:
            logger.warning("No tracts received allocated Redfin data")
            return stats

        # Step 5: Bulk update database
        update_result = await bulk_update_tracts(session, tract_data)
        stats["tracts_updated"] = update_result["updated"]
        stats["errors"] = update_result["errors"]

    except Exception as e:
        logger.error(f"Error loading Redfin data: {e}", exc_info=True)
        stats["errors"] += 1
        raise

    logger.info(f"Redfin load complete: {stats}")
    return stats
