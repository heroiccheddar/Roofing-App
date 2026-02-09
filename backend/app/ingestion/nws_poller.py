"""NWS Active Alerts API poller.

Polls the National Weather Service API for active severe weather alerts
(Severe Thunderstorm Warnings, Tornado Warnings) every 5 minutes.
Extracts hail/wind parameters and warning polygons, then upserts them
into the storm_events PostGIS table.

API Documentation: https://www.weather.gov/documentation/services-web-api
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx
from shapely.geometry import MultiPolygon, Point, Polygon, shape
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storm_event import StormEvent

logger = logging.getLogger(__name__)

# NWS API configuration
NWS_API_BASE = "https://api.weather.gov/alerts/active"
NWS_USER_AGENT = "(StormLeads, contact@stormleads.com)"

# Alert event types to monitor
SEVERE_THUNDERSTORM_WARNING = "Severe Thunderstorm Warning"
TORNADO_WARNING = "Tornado Warning"

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds


async def poll_nws_alerts(
    db_session: AsyncSession,
    target_states: list[str] | None = None,
) -> dict:
    """Poll NWS API for active severe weather alerts.

    Fetches active Severe Thunderstorm Warnings and Tornado Warnings from the
    NWS API, extracts hail size, wind speed, and warning polygons, then upserts
    them into the storm_events table. Handles API retries, malformed data, and
    deduplication based on nws_event_id.

    Args:
        db_session: SQLAlchemy async session
        target_states: Optional list of state abbreviations to filter by (e.g., ['TX', 'OK'])

    Returns:
        dict with counts: {"fetched": N, "new": N, "existing": N, "errors": N}
    """
    stats = {"fetched": 0, "new": 0, "existing": 0, "errors": 0}

    # Fetch both severe thunderstorm and tornado warnings
    event_types = [SEVERE_THUNDERSTORM_WARNING, TORNADO_WARNING]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for event_type in event_types:
            try:
                features = await _fetch_alerts_with_retry(
                    client, event_type, target_states
                )
                stats["fetched"] += len(features)

                for feature in features:
                    try:
                        result = await _process_alert(db_session, feature, event_type)
                        if result == "new":
                            stats["new"] += 1
                        elif result == "existing":
                            stats["existing"] += 1
                    except Exception as e:
                        logger.error(
                            f"Error processing alert {feature.get('id', 'unknown')}: {e}",
                            exc_info=True,
                        )
                        stats["errors"] += 1

            except Exception as e:
                logger.error(f"Error fetching {event_type} alerts: {e}", exc_info=True)
                stats["errors"] += 1

    # Commit all changes
    try:
        await db_session.commit()
        logger.info(
            f"NWS poll complete: {stats['fetched']} fetched, "
            f"{stats['new']} new, {stats['existing']} existing, "
            f"{stats['errors']} errors"
        )
    except Exception as e:
        logger.error(f"Error committing NWS alerts to database: {e}", exc_info=True)
        await db_session.rollback()
        stats["errors"] += stats["new"]  # Count uncommitted records as errors
        stats["new"] = 0

    return stats


async def _fetch_alerts_with_retry(
    client: httpx.AsyncClient,
    event_type: str,
    target_states: list[str] | None = None,
) -> list[dict]:
    """Fetch alerts from NWS API with exponential backoff retry.

    Args:
        client: httpx async client
        event_type: The event type to filter for
        target_states: Optional list of state abbreviations

    Returns:
        List of GeoJSON feature dictionaries

    Raises:
        Exception: If all retries fail
    """
    params = {
        "status": "actual",
        "message_type": "alert",
        "event": event_type,
    }

    # Add state filter if specified
    if target_states:
        params["area"] = ",".join(target_states)

    headers = {"User-Agent": NWS_USER_AGENT}

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Fetching {event_type} alerts (attempt {attempt + 1})")
            response = await client.get(
                NWS_API_BASE,
                params=params,
                headers=headers,
            )
            response.raise_for_status()

            data = response.json()
            features = data.get("features", [])

            logger.info(f"Fetched {len(features)} {event_type} alerts from NWS")
            return features

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 503:
                # Service unavailable - retry with backoff
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BACKOFF_BASE ** attempt
                    logger.warning(
                        f"NWS API returned 503, retrying in {wait_time}s "
                        f"(attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(wait_time)
                    continue
            raise

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = RETRY_BACKOFF_BASE ** attempt
                logger.warning(
                    f"Error fetching NWS alerts: {e}, retrying in {wait_time}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES})"
                )
                await asyncio.sleep(wait_time)
                continue
            raise

    raise Exception(f"Failed to fetch NWS alerts after {MAX_RETRIES} attempts")


async def _process_alert(
    db_session: AsyncSession,
    feature: dict,
    event_type: str,
) -> str:
    """Process a single NWS alert feature and upsert to database.

    Args:
        db_session: SQLAlchemy async session
        feature: GeoJSON feature from NWS API
        event_type: The alert event type (Severe Thunderstorm Warning, etc.)

    Returns:
        "new" if inserted, "existing" if already in database
    """
    properties = feature.get("properties", {})

    # Extract NWS event ID for deduplication
    nws_event_id = properties.get("id") or feature.get("id")
    if not nws_event_id:
        logger.warning("Alert missing ID, skipping")
        raise ValueError("Alert missing ID")

    # Check if already exists
    existing = await db_session.execute(
        select(StormEvent).where(StormEvent.nws_event_id == nws_event_id)
    )
    if existing.scalar_one_or_none():
        logger.debug(f"Alert {nws_event_id} already exists, skipping")
        return "existing"

    # Extract geometry
    geometry = feature.get("geometry")
    if not geometry:
        logger.warning(f"Alert {nws_event_id} has no geometry, skipping")
        raise ValueError("Alert missing geometry")

    # Parse polygon and compute centroid
    try:
        geom = shape(geometry)

        # NWS may return MultiPolygon; extract the largest component
        if isinstance(geom, MultiPolygon):
            polygon_shape = max(geom.geoms, key=lambda g: g.area)
        elif isinstance(geom, Polygon):
            polygon_shape = geom
        else:
            raise ValueError(f"Unexpected geometry type: {geom.geom_type}")

        centroid = polygon_shape.centroid

        # Convert to WKT for PostGIS
        warning_polygon_wkt = WKTElement(polygon_shape.wkt, srid=4326)
        location_wkt = WKTElement(f"POINT({centroid.x} {centroid.y})", srid=4326)

    except Exception as e:
        logger.error(f"Error parsing geometry for {nws_event_id}: {e}")
        raise

    # Extract parameters
    parameters = properties.get("parameters", {})

    # Extract hail size (inches)
    hail_diameter = _extract_hail_size(parameters)

    # Extract wind speed (convert knots to mph)
    wind_speed = _extract_wind_speed(parameters)

    # Determine event type
    storm_event_type = _determine_event_type(event_type, hail_diameter, wind_speed)

    # Extract timestamp
    event_timestamp = _extract_timestamp(properties)

    # Create storm event record
    storm_event = StormEvent(
        source="nws",
        event_type=storm_event_type,
        location=location_wkt,
        warning_polygon=warning_polygon_wkt,
        hail_diameter=hail_diameter,
        wind_speed=wind_speed,
        event_timestamp=event_timestamp,
        nws_event_id=nws_event_id,
        raw_data=properties,  # Store full properties as JSONB
        scored=False,
    )

    db_session.add(storm_event)

    logger.debug(
        f"Inserted new {storm_event_type} alert {nws_event_id} "
        f"(hail: {hail_diameter}, wind: {wind_speed})"
    )

    return "new"


def _extract_hail_size(parameters: dict) -> float | None:
    """Extract hail size from NWS alert parameters.

    NWS provides hail size in parameters.maxHailSize or parameters.hailSize
    as a list of strings like ["2.00"].

    Args:
        parameters: Alert parameters dictionary

    Returns:
        Hail diameter in inches, or None if not present
    """
    # Try maxHailSize first, then hailSize
    for key in ["maxHailSize", "hailSize"]:
        value = parameters.get(key)
        if value and isinstance(value, list) and len(value) > 0:
            try:
                return float(value[0])
            except (ValueError, TypeError):
                logger.warning(f"Could not parse hail size from {value}")

    return None


def _extract_wind_speed(parameters: dict) -> float | None:
    """Extract wind speed from NWS alert parameters.

    NWS provides wind speed in parameters.maxWindGust or parameters.windGust
    as a list of strings. Values may be in knots and need conversion to mph.

    Args:
        parameters: Alert parameters dictionary

    Returns:
        Wind speed in mph, or None if not present
    """
    # Try maxWindGust first, then windGust
    for key in ["maxWindGust", "windGust"]:
        value = parameters.get(key)
        if value and isinstance(value, list) and len(value) > 0:
            try:
                # Parse the value
                wind_value = float(value[0])

                # NWS wind speeds are typically in knots for alerts
                # Convert knots to mph: knots × 1.15078
                # However, some alerts may already be in mph
                # Check if the value is reasonable (severe wind is typically 50-100+ mph)
                # If value is < 50, assume it's in knots
                if wind_value < 50:
                    wind_value = wind_value * 1.15078

                return wind_value

            except (ValueError, TypeError):
                logger.warning(f"Could not parse wind speed from {value}")

    return None


def _determine_event_type(
    nws_event_type: str,
    hail_diameter: float | None,
    wind_speed: float | None,
) -> str:
    """Determine the storm event type based on NWS alert and parameters.

    Args:
        nws_event_type: The NWS event type (Severe Thunderstorm Warning, etc.)
        hail_diameter: Hail size in inches
        wind_speed: Wind speed in mph

    Returns:
        Event type: 'tornado', 'hail', or 'wind'
    """
    if nws_event_type == TORNADO_WARNING:
        return "tornado"

    # For severe thunderstorm warnings, prioritize hail if present
    if hail_diameter is not None and hail_diameter > 0:
        return "hail"

    # Otherwise default to wind
    return "wind"


def _extract_timestamp(properties: dict) -> datetime:
    """Extract event timestamp from NWS alert properties.

    Uses properties.sent or properties.effective as the event timestamp.
    NWS provides ISO 8601 timestamps with timezone offset.

    Args:
        properties: Alert properties dictionary

    Returns:
        Timezone-aware datetime

    Raises:
        ValueError: If no valid timestamp found
    """
    # Try 'sent' first, then 'effective'
    for key in ["sent", "effective"]:
        timestamp_str = properties.get(key)
        if timestamp_str:
            try:
                # Parse ISO 8601 with timezone
                return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError) as e:
                logger.warning(f"Could not parse timestamp from {key}: {e}")

    # If no valid timestamp, raise error
    raise ValueError("No valid timestamp found in alert properties")
