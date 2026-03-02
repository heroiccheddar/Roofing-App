"""Google Solar API client for roof geometry and imagery data.

Fetches building-level roof measurements from the Google Solar API's
findClosest endpoint. Results are cached on the Property record for
CACHE_TTL_DAYS to avoid redundant API calls.

Rate limits: Google Solar API is billed per request; no burst limit is
documented, but best practice is to call on-demand only, never in bulk.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from geoalchemy2.shape import to_shape
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

SOLAR_API_URL = "https://solar.googleapis.com/v1/buildingInsights:findClosest"
CACHE_TTL_DAYS = 30
SQ_METERS_TO_SQ_FEET = 10.7639


def classify_pitch(avg_pitch_deg: float) -> str:
    """Classify a roof pitch into a named category.

    Args:
        avg_pitch_deg: Area-weighted average pitch across all roof facets.

    Returns:
        "standard" for pitches below 30 degrees,
        "steep" for 30–36 degrees,
        "very_steep" for 37 degrees and above.
    """
    if avg_pitch_deg < 30:
        return "standard"
    if avg_pitch_deg < 37:
        return "steep"
    return "very_steep"


async def fetch_solar_insights(lat: float, lon: float) -> dict[str, Any]:
    """Call the Google Solar API buildingInsights:findClosest endpoint.

    Args:
        lat: Latitude of the property (WGS84).
        lon: Longitude of the property (WGS84).

    Returns:
        Raw JSON response dict from the Solar API.

    Raises:
        ValueError: If the API returns a 404 (no building found at location).
        httpx.HTTPStatusError: On non-404 HTTP errors (caller handles as 503).
        Exception: On network or timeout failures.
    """
    params = {
        "location.latitude": lat,
        "location.longitude": lon,
        "requiredQuality": "LOW",
        "key": settings.GOOGLE_SOLAR_API_KEY,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(SOLAR_API_URL, params=params)

    if response.status_code == 404:
        raise ValueError(
            f"Google Solar API found no building at ({lat:.6f}, {lon:.6f})"
        )

    if response.status_code != 200:
        # Extract Google's error message for better debugging
        try:
            error_body = response.json()
            error_msg = error_body.get("error", {}).get("message", response.text)
        except Exception:
            error_msg = response.text
        raise RuntimeError(
            f"Google Solar API returned {response.status_code}: {error_msg}"
        )

    return response.json()


def parse_solar_response(data: dict[str, Any]) -> dict[str, Any]:
    """Extract and normalise roof geometry from a Solar API response.

    Reads solarPotential.wholeRoofStats for total area, iterates
    solarPotential.roofSegmentStats[] for per-facet data, and computes
    an area-weighted average pitch. All areas are converted from m² to sqft.

    Args:
        data: Raw JSON dict from fetch_solar_insights.

    Returns:
        Dict with keys:
            roof_area_sqft, roof_ground_area_sqft, roof_facet_count,
            roof_avg_pitch_deg, roof_max_pitch_deg, roof_facets (list of dicts),
            solar_imagery_date (date or None), solar_imagery_quality (str or None).

    Raises:
        ValueError: If solarPotential is absent or the response is malformed.
    """
    solar = data.get("solarPotential")
    if not solar:
        raise ValueError("Solar API response missing solarPotential block")

    # Total roof area from wholeRoofStats
    whole_stats = solar.get("wholeRoofStats", {})
    roof_area_m2 = whole_stats.get("areaMeters2")
    if roof_area_m2 is None:
        raise ValueError("Solar API response missing wholeRoofStats.areaMeters2")
    roof_area_sqft = roof_area_m2 * SQ_METERS_TO_SQ_FEET

    # Ground-projected area is available at the top-level solarPotential object
    # (roofSegmentStats ground area is per-facet; whole-building ground area is
    # exposed via the building footprint field if present).
    # Fall back to None if the field is absent — it is not critical.
    ground_area_m2 = solar.get("groundAreaMeters2")
    roof_ground_area_sqft = (
        ground_area_m2 * SQ_METERS_TO_SQ_FEET if ground_area_m2 is not None else None
    )

    # Per-facet data from roofSegmentStats
    segment_stats = solar.get("roofSegmentStats", [])
    facets = []
    total_weighted_pitch = 0.0
    total_facet_area = 0.0
    max_pitch = 0.0

    for seg in segment_stats:
        seg_stats = seg.get("stats", {})
        area_m2 = seg_stats.get("areaMeters2", 0.0)
        area_sqft = area_m2 * SQ_METERS_TO_SQ_FEET
        pitch_deg = seg.get("pitchDegrees", 0.0)
        azimuth_deg = seg.get("azimuthDegrees", 0.0)

        facets.append(
            {
                "area_sqft": round(area_sqft, 2),
                "pitch_deg": round(pitch_deg, 2),
                "azimuth_deg": round(azimuth_deg, 2),
            }
        )

        total_weighted_pitch += pitch_deg * area_sqft
        total_facet_area += area_sqft
        if pitch_deg > max_pitch:
            max_pitch = pitch_deg

    # Area-weighted average pitch; default 0 if no facets were returned
    avg_pitch = (total_weighted_pitch / total_facet_area) if total_facet_area > 0 else 0.0

    # Imagery date — Solar API returns {year, month, day} object
    imagery_date: date | None = None
    raw_date = data.get("imageryDate")
    if raw_date and isinstance(raw_date, dict):
        try:
            imagery_date = date(
                int(raw_date["year"]),
                int(raw_date["month"]),
                int(raw_date["day"]),
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Could not parse Solar API imageryDate %r: %s", raw_date, exc)

    imagery_quality: str | None = data.get("imageryQuality")

    return {
        "roof_area_sqft": round(roof_area_sqft, 2),
        "roof_ground_area_sqft": round(roof_ground_area_sqft, 2) if roof_ground_area_sqft is not None else None,
        "roof_facet_count": len(facets),
        "roof_avg_pitch_deg": round(avg_pitch, 2),
        "roof_max_pitch_deg": round(max_pitch, 2),
        "roof_facets": facets,
        "solar_imagery_date": imagery_date,
        "solar_imagery_quality": imagery_quality,
    }


async def get_roof_data(db: AsyncSession, prop: Any) -> dict[str, Any]:
    """Return roof data for a property, using cached values when fresh.

    Checks whether solar_fetched_at is within CACHE_TTL_DAYS. On a cache hit
    the stored columns are returned directly without calling the Solar API.
    On a cache miss the API is called, the property record is updated, and
    the enriched data is returned.

    Args:
        db: Async SQLAlchemy session (used to commit the cache update).
        prop: Property ORM instance. Must have a non-null location column.

    Returns:
        Dict with all RoofDataResponse fields plus convenience fields:
            roof_squares (area / 100), steep_pitch (avg >= 30), pitch_category.

    Raises:
        ValueError: If the property has no location, or Solar API finds no
                    building at the coordinates.
        Exception: Propagated from httpx on network failures (caller logs as 503).
    """
    # --- Cache check ---
    if prop.solar_fetched_at is not None:
        age = datetime.now(timezone.utc) - prop.solar_fetched_at
        if age <= timedelta(days=CACHE_TTL_DAYS):
            logger.debug(
                "get_roof_data: cache hit for property %s (age %s days)",
                prop.id,
                age.days,
            )
            return _build_response_dict(prop)

    # --- Resolve coordinates from PostGIS POINT ---
    if prop.location is None:
        raise ValueError(f"Property {prop.id} has no location geometry")

    point = to_shape(prop.location)
    lat, lon = point.y, point.x

    # --- Fetch from Solar API ---
    logger.info("get_roof_data: fetching Solar API for property %s (%.6f, %.6f)", prop.id, lat, lon)
    raw = await fetch_solar_insights(lat, lon)
    parsed = parse_solar_response(raw)

    # --- Persist to property record ---
    prop.roof_area_sqft = parsed["roof_area_sqft"]
    prop.roof_ground_area_sqft = parsed["roof_ground_area_sqft"]
    prop.roof_facet_count = parsed["roof_facet_count"]
    prop.roof_avg_pitch_deg = parsed["roof_avg_pitch_deg"]
    prop.roof_max_pitch_deg = parsed["roof_max_pitch_deg"]
    prop.roof_facets = parsed["roof_facets"]
    prop.solar_imagery_date = parsed["solar_imagery_date"]
    prop.solar_imagery_quality = parsed["solar_imagery_quality"]
    prop.solar_fetched_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(prop)

    logger.info(
        "get_roof_data: stored roof data for property %s — %.0f sqft, %d facets, avg pitch %.1f°",
        prop.id,
        prop.roof_area_sqft,
        prop.roof_facet_count,
        prop.roof_avg_pitch_deg,
    )

    return _build_response_dict(prop)


def _build_response_dict(prop: Any) -> dict[str, Any]:
    """Assemble the response dict from a property's stored roof columns.

    Includes convenience fields used by the frontend:
        roof_squares: roofing industry unit (1 square = 100 sqft).
        steep_pitch: True when avg pitch >= 30 degrees (affects labour cost).
        pitch_category: Human-readable pitch classification.

    Args:
        prop: Property ORM instance with populated roof columns.

    Returns:
        Dict matching the RoofDataResponse schema.
    """
    facets = prop.roof_facets or []
    avg_pitch = prop.roof_avg_pitch_deg or 0.0

    return {
        "roof_area_sqft": prop.roof_area_sqft,
        "roof_ground_area_sqft": prop.roof_ground_area_sqft,
        "roof_facet_count": prop.roof_facet_count or len(facets),
        "roof_avg_pitch_deg": avg_pitch,
        "roof_max_pitch_deg": prop.roof_max_pitch_deg or 0.0,
        "roof_facets": facets,
        "imagery_date": str(prop.solar_imagery_date) if prop.solar_imagery_date else None,
        "imagery_quality": prop.solar_imagery_quality,
        "roof_squares": round((prop.roof_area_sqft or 0.0) / 100, 2),
        "steep_pitch": avg_pitch >= 30,
        "pitch_category": classify_pitch(avg_pitch),
    }
