"""Storm Prediction Center report scraper.

Scrapes preliminary storm reports from SPC's website for more recent
data than the NWS database provides (often 1-3 day lag vs 30+ days).

SPC Reports: https://www.spc.noaa.gov/climo/reports/
"""

import csv
import logging
from datetime import datetime, date, timedelta, timezone
from io import StringIO
from typing import Optional

import httpx
from shapely.geometry import Point
from geoalchemy2.shape import from_shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storm_event import StormEvent

logger = logging.getLogger(__name__)

# SPC base URL for reports
SPC_BASE_URL = "https://www.spc.noaa.gov/climo/reports"

# Report type configuration
REPORT_TYPES = {
    "hail": {
        "event_type": "hail",
        "value_column": "Size",
        "conversion": lambda x: float(x) if x and x != "UNK" else None,  # inches
        "field": "hail_diameter",
    },
    "wind": {
        "event_type": "wind",
        "value_column": "Speed",
        "conversion": lambda x: (
            float(x) * 1.15078 if x and x != "UNK" else None
        ),  # knots to mph
        "field": "wind_speed",
    },
    "torn": {
        "event_type": "tornado",
        "value_column": "Speed",
        "conversion": lambda x: None,  # F/EF scale, not storing as numeric
        "field": None,
    },
}


def _build_spc_url(report_type: str, report_date: date) -> str:
    """Build SPC report URL for a given date and report type.

    Args:
        report_type: One of 'hail', 'wind', 'torn'
        report_date: Date to fetch reports for

    Returns:
        Full URL to the CSV file
    """
    today = date.today()
    yesterday = today - timedelta(days=1)

    if report_date == today:
        filename = f"today_{report_type}.csv"
    elif report_date == yesterday:
        filename = f"yesterday_{report_type}.csv"
    else:
        # Format: YYMMDD_rpts_hail.csv
        date_str = report_date.strftime("%y%m%d")
        filename = f"{date_str}_rpts_{report_type}.csv"

    return f"{SPC_BASE_URL}/{filename}"


def _generate_spc_report_id(
    report_date: date,
    time_str: str,
    lat: float,
    lon: float,
    event_type: str,
) -> str:
    """Generate deterministic SPC report ID for deduplication.

    Args:
        report_date: Date of the report
        time_str: Time string in HHMM format
        lat: Latitude
        lon: Longitude
        event_type: Event type (hail, wind, tornado)

    Returns:
        Unique report ID string
    """
    # Round coordinates to 2 decimal places for consistent IDs
    lat_rounded = round(lat, 2)
    lon_rounded = round(lon, 2)
    date_str = report_date.strftime("%Y%m%d")

    return f"spc_{date_str}_{time_str}_{lat_rounded}_{lon_rounded}_{event_type}"


def _parse_time_to_datetime(time_str: str, report_date: date) -> datetime:
    """Convert SPC HHMM time string to UTC datetime.

    SPC reports use local time (Central Time for most US reports).
    This is a simplified conversion that assumes Central Time.
    For production use, would need proper timezone handling based on location.

    Args:
        time_str: Time in HHMM format (e.g., '1530')
        report_date: Date of the report

    Returns:
        Datetime object in UTC
    """
    # Parse HHMM to hours and minutes
    if not time_str or len(time_str) < 3:
        # Default to noon UTC if time is missing
        return datetime.combine(report_date, datetime.min.time()).replace(tzinfo=timezone.utc)

    # Pad with zeros if needed
    time_str = time_str.zfill(4)

    try:
        hour = int(time_str[:2])
        minute = int(time_str[2:4])

        # Create datetime in UTC (simplified - assumes already in UTC-like time)
        # For production, would convert from Central Time to UTC properly
        dt = datetime(
            report_date.year,
            report_date.month,
            report_date.day,
            hour,
            minute,
            tzinfo=timezone.utc,
        )

        return dt
    except (ValueError, IndexError) as e:
        logger.warning(f"Failed to parse time '{time_str}': {e}, using noon UTC")
        return datetime.combine(report_date, datetime.min.time()).replace(
            hour=12, tzinfo=timezone.utc
        )


def _is_valid_data_row(row: dict) -> bool:
    """Check if a CSV row contains valid storm report data.

    Args:
        row: Dictionary representing a CSV row

    Returns:
        True if row has required fields with valid data
    """
    # Must have Time field starting with a digit (not header or comment)
    if not row.get("Time") or not row["Time"][0].isdigit():
        return False

    # Must have lat/lon
    if not row.get("Lat") or not row.get("Lon"):
        return False

    # Must have at least one of the value columns
    has_value = any(
        row.get(config["value_column"]) for config in REPORT_TYPES.values()
    )

    return has_value


def _parse_spc_csv(
    csv_content: str,
    report_type: str,
    report_date: date,
) -> list[dict]:
    """Parse SPC CSV content into structured report dictionaries.

    Args:
        csv_content: Raw CSV file content
        report_type: One of 'hail', 'wind', 'torn'
        report_date: Date the report is for

    Returns:
        List of parsed report dictionaries
    """
    reports = []
    type_config = REPORT_TYPES[report_type]

    # Parse CSV
    reader = csv.DictReader(StringIO(csv_content))

    for row in reader:
        try:
            # Skip invalid rows (headers, comments, empty)
            if not _is_valid_data_row(row):
                continue

            # Extract coordinates
            try:
                lat = float(row["Lat"])
                lon = float(row["Lon"])
            except (ValueError, KeyError) as e:
                logger.warning(f"Invalid lat/lon in row: {row}, error: {e}")
                continue

            # Extract time
            time_str = row.get("Time", "").strip()
            event_timestamp = _parse_time_to_datetime(time_str, report_date)

            # Extract value (hail size, wind speed, etc.)
            value_str = row.get(type_config["value_column"], "").strip()
            converted_value = None
            if value_str and value_str != "UNK":
                try:
                    # Remove any non-numeric characters except decimal point and minus
                    cleaned = "".join(
                        c for c in value_str if c.isdigit() or c in ".-"
                    )
                    if cleaned and cleaned not in ["-", "."]:
                        converted_value = type_config["conversion"](cleaned)
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"Failed to convert value '{value_str}' for {report_type}: {e}"
                    )

            # Generate report ID
            spc_report_id = _generate_spc_report_id(
                report_date, time_str, lat, lon, type_config["event_type"]
            )

            # Create report dictionary
            report = {
                "spc_report_id": spc_report_id,
                "source": "spc",
                "event_type": type_config["event_type"],
                "latitude": lat,
                "longitude": lon,
                "event_timestamp": event_timestamp,
                "value": converted_value,
                "value_field": type_config["field"],
                "raw_data": dict(row),  # Store entire CSV row
            }

            reports.append(report)

        except Exception as e:
            logger.error(f"Error parsing SPC CSV row: {row}, error: {e}", exc_info=True)
            continue

    return reports


async def _fetch_spc_csv(
    client: httpx.AsyncClient,
    report_type: str,
    report_date: date,
) -> Optional[str]:
    """Fetch SPC CSV file for a given date and report type.

    Args:
        client: HTTPX async client
        report_type: One of 'hail', 'wind', 'torn'
        report_date: Date to fetch reports for

    Returns:
        CSV content as string, or None if fetch failed
    """
    url = _build_spc_url(report_type, report_date)

    try:
        response = await client.get(url, timeout=30.0)
        response.raise_for_status()
        return response.text
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            # No reports available for this date/type (common on quiet days)
            logger.info(f"No SPC {report_type} reports available for {report_date}")
            return None
        logger.error(f"HTTP error fetching {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}", exc_info=True)
        return None


async def _insert_storm_event(
    db_session: AsyncSession,
    report: dict,
) -> bool:
    """Insert a storm event into the database if it doesn't exist.

    Args:
        db_session: SQLAlchemy async session
        report: Parsed report dictionary

    Returns:
        True if inserted (new), False if already exists
    """
    # Check if report already exists
    result = await db_session.execute(
        select(StormEvent).where(
            StormEvent.spc_report_id == report["spc_report_id"]
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        return False

    # Create POINT geometry
    point = Point(report["longitude"], report["latitude"])
    location_wkt = from_shape(point, srid=4326)

    # Build event data
    event_data = {
        "source": report["source"],
        "event_type": report["event_type"],
        "location": location_wkt,
        "warning_polygon": None,  # SPC reports are point-based
        "event_timestamp": report["event_timestamp"],
        "spc_report_id": report["spc_report_id"],
        "raw_data": report["raw_data"],
        "scored": False,
    }

    # Add type-specific value field
    if report["value_field"] and report["value"] is not None:
        event_data[report["value_field"]] = report["value"]

    # Create and insert event
    event = StormEvent(**event_data)
    db_session.add(event)

    return True


async def scrape_spc_reports(
    db_session: AsyncSession,
    days_back: int = 1,
) -> dict:
    """Scrape SPC storm reports for today and optionally previous days.

    This function fetches CSV reports from the Storm Prediction Center for
    hail, wind, and tornado reports. Reports are parsed and inserted into
    the storm_events table with automatic deduplication.

    Args:
        db_session: SQLAlchemy async session
        days_back: Number of days to look back (0=today only, 1=today+yesterday)

    Returns:
        dict with counts: {"fetched": N, "new": N, "existing": N, "errors": N}
    """
    stats = {
        "fetched": 0,
        "new": 0,
        "existing": 0,
        "errors": 0,
    }

    # Determine date range
    today = date.today()
    dates_to_fetch = [today - timedelta(days=i) for i in range(days_back + 1)]

    logger.info(
        f"Starting SPC scraper for {len(dates_to_fetch)} day(s): "
        f"{', '.join(str(d) for d in dates_to_fetch)}"
    )

    async with httpx.AsyncClient() as client:
        for report_date in dates_to_fetch:
            for report_type in REPORT_TYPES.keys():
                # Fetch CSV
                csv_content = await _fetch_spc_csv(client, report_type, report_date)

                if not csv_content:
                    continue

                # Parse CSV
                try:
                    reports = _parse_spc_csv(csv_content, report_type, report_date)
                    stats["fetched"] += len(reports)

                    logger.info(
                        f"Parsed {len(reports)} {report_type} reports for {report_date}"
                    )

                    # Insert into database
                    for report in reports:
                        try:
                            is_new = await _insert_storm_event(db_session, report)
                            if is_new:
                                stats["new"] += 1
                            else:
                                stats["existing"] += 1
                        except Exception as e:
                            logger.error(
                                f"Error inserting report {report.get('spc_report_id')}: {e}",
                                exc_info=True,
                            )
                            stats["errors"] += 1

                    # Commit after each file
                    await db_session.commit()

                except Exception as e:
                    logger.error(
                        f"Error processing {report_type} reports for {report_date}: {e}",
                        exc_info=True,
                    )
                    stats["errors"] += 1
                    await db_session.rollback()

    logger.info(
        f"SPC scraper complete. Fetched: {stats['fetched']}, "
        f"New: {stats['new']}, Existing: {stats['existing']}, "
        f"Errors: {stats['errors']}"
    )

    return stats
