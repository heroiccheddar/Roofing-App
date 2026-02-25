"""Route optimization endpoint.

Accepts an ordered list of zone UUIDs plus a starting coordinate and
returns an optimized visit sequence with road-network geometry.

Primary path (when OPENROUTESERVICE_API_KEY is set):
  1. POST to ORS /optimization to solve the vehicle routing problem (VRP)
     and obtain the optimal job visit order.
  2. GET ORS /v2/directions/driving-car/geojson to obtain the full
     road-network polyline for the optimized route.

Fallback path (no API key or ORS request failure):
  - Nearest-neighbour TSP heuristic on Euclidean coordinates.
  - Straight-line GeoJSON LineString geometry.
  - Distance/duration estimated from haversine (assuming 50 km/h average).

Both paths return a RouteResponse with identical schema so the client
does not need to handle the difference.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.shape import to_shape

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.lead_zone import LeadZone
from app.models.roofer_account import RooferAccount
from app.schemas.route import RouteRequest, RouteResponse, RouteWaypoint
from app.utils.geo import haversine_km

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/route", tags=["route"])

# OpenRouteService base URL
_ORS_BASE = "https://api.openrouteservice.org"
_ORS_TIMEOUT_S = 10.0

# Assumed average driving speed for fallback duration estimates (km/h)
_FALLBACK_SPEED_KMH = 50.0


def _total_route_distance_km(
    start_lat: float,
    start_lon: float,
    ordered_stops: list[tuple[float, float]],
) -> float:
    """Sum haversine distances along the full route (start -> stops)."""
    points = [(start_lat, start_lon)] + list(ordered_stops)
    total = 0.0
    for i in range(len(points) - 1):
        total += haversine_km(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
    return total


# ---------------------------------------------------------------------------
# Fallback: nearest-neighbour TSP
# ---------------------------------------------------------------------------

def _nearest_neighbour_order(
    start_lat: float,
    start_lon: float,
    stops: list[tuple[UUID, float, float, str | None]],
) -> list[tuple[UUID, float, float, str | None]]:
    """Return stops re-ordered by a greedy nearest-neighbour heuristic.

    Args:
        start_lat: Starting latitude
        start_lon: Starting longitude
        stops: List of (zone_id, lat, lon, display_name) tuples

    Returns:
        Same tuples in greedy visit order (not necessarily globally optimal
        but deterministic and O(n^2), acceptable for n <= 10)
    """
    remaining = list(stops)
    ordered: list[tuple[UUID, float, float, str | None]] = []
    cur_lat, cur_lon = start_lat, start_lon

    while remaining:
        nearest_idx = min(
            range(len(remaining)),
            key=lambda i: haversine_km(cur_lat, cur_lon, remaining[i][1], remaining[i][2]),
        )
        nearest = remaining.pop(nearest_idx)
        ordered.append(nearest)
        cur_lat, cur_lon = nearest[1], nearest[2]

    return ordered


def _straight_line_geometry(
    start_lat: float,
    start_lon: float,
    ordered_stops: list[tuple[UUID, float, float, str | None]],
) -> dict:
    """Build a GeoJSON LineString connecting start -> stops in order.

    Coordinates are [lon, lat] per GeoJSON spec (RFC 7946 §3.1.1).
    """
    coords = [[start_lon, start_lat]]
    for _, lat, lon, _ in ordered_stops:
        coords.append([lon, lat])
    return {"type": "LineString", "coordinates": coords}


# ---------------------------------------------------------------------------
# ORS integration
# ---------------------------------------------------------------------------

async def _ors_optimize(
    api_key: str,
    start_lat: float,
    start_lon: float,
    stops: list[tuple[UUID, float, float, str | None]],
) -> list[int] | None:
    """Call ORS /optimization and return the job visit order as indices into stops.

    Returns None on any ORS error so the caller can fall back gracefully.
    The ORS Optimization API expects coordinates as [lon, lat].
    """
    jobs = [
        {
            "id": idx + 1,  # ORS job IDs must be positive integers
            "location": [lon, lat],
        }
        for idx, (_, lat, lon, _) in enumerate(stops)
    ]

    payload = {
        "vehicles": [
            {
                "id": 1,
                "profile": "driving-car",
                "start": [start_lon, start_lat],
                "end": [start_lon, start_lat],
            }
        ],
        "jobs": jobs,
    }

    try:
        async with httpx.AsyncClient(timeout=_ORS_TIMEOUT_S) as client:
            response = await client.post(
                f"{_ORS_BASE}/optimization",
                json=payload,
                headers={"Authorization": api_key, "Content-Type": "application/json"},
            )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("ORS /optimization request failed: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Unexpected error calling ORS /optimization: %s", exc)
        return None

    # Parse the ordered job IDs from the first (and only) vehicle route
    try:
        routes = data.get("routes", [])
        if not routes:
            logger.warning("ORS /optimization returned no routes")
            return None
        steps = routes[0].get("steps", [])
        # steps includes start/end depot steps (type='start'/'end'); filter to jobs only
        job_ids_in_order = [
            step["job"] - 1  # convert back to 0-based index into stops
            for step in steps
            if step.get("type") == "job"
        ]
        return job_ids_in_order if job_ids_in_order else None
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("Failed to parse ORS /optimization response: %s", exc)
        return None


async def _ors_directions_geojson(
    api_key: str,
    start_lat: float,
    start_lon: float,
    ordered_stops: list[tuple[UUID, float, float, str | None]],
) -> tuple[dict, float, float] | None:
    """Call ORS /v2/directions/driving-car/geojson for the road polyline.

    Returns (geojson_geometry, distance_km, duration_minutes) or None on failure.
    Coordinates for ORS are [lon, lat].
    """
    waypoint_coords = [[start_lon, start_lat]]
    for _, lat, lon, _ in ordered_stops:
        waypoint_coords.append([lon, lat])

    payload = {"coordinates": waypoint_coords}

    try:
        async with httpx.AsyncClient(timeout=_ORS_TIMEOUT_S) as client:
            response = await client.post(
                f"{_ORS_BASE}/v2/directions/driving-car/geojson",
                json=payload,
                headers={"Authorization": api_key, "Content-Type": "application/json"},
            )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("ORS /directions request failed: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Unexpected error calling ORS /directions: %s", exc)
        return None

    try:
        feature = data["features"][0]
        geometry = feature["geometry"]
        summary = feature["properties"]["summary"]
        distance_km = summary["distance"] / 1000.0
        duration_minutes = summary["duration"] / 60.0
        return geometry, distance_km, duration_minutes
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("Failed to parse ORS /directions response: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("", response_model=RouteResponse)
async def optimize_route(
    body: RouteRequest,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RouteResponse:
    """Return an optimized driving route visiting the requested zones.

    Validates that all zone_ids exist, then attempts to call OpenRouteService
    for VRP optimization and road-network geometry. Falls back to nearest-
    neighbour TSP with straight-line geometry if ORS is unavailable.

    Args:
        body: RouteRequest with 2-10 zone UUIDs and starting coordinates
        current_user: Authenticated roofer account (injected)
        db: Async database session (injected)

    Returns:
        RouteResponse with ordered waypoints, GeoJSON geometry, and
        estimated distance and duration

    Raises:
        400: Fewer than 2 or more than 10 zone_ids provided
        404: One or more zone_ids not found
    """
    now = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # 1. Validate zone count (Pydantic min_length/max_length handles this,
    #    but an explicit check gives a cleaner error message).
    # ------------------------------------------------------------------
    if len(body.zone_ids) < 2 or len(body.zone_ids) > 10:
        raise HTTPException(
            status_code=400,
            detail=f"zone_ids must contain 2-10 entries, got {len(body.zone_ids)}",
        )

    # ------------------------------------------------------------------
    # 2. Fetch zones from DB, verify all IDs exist.
    # ------------------------------------------------------------------
    stmt = select(LeadZone).where(LeadZone.id.in_(body.zone_ids))
    result = await db.execute(stmt)
    zones = result.scalars().all()

    fetched_ids = {zone.id for zone in zones}
    missing_ids = [str(zid) for zid in body.zone_ids if zid not in fetched_ids]
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Zone(s) not found: {', '.join(missing_ids)}",
        )

    # ------------------------------------------------------------------
    # 3. Build stop list preserving the zone_id order from the request
    #    so the optimization starts from a deterministic input.
    # ------------------------------------------------------------------
    zone_map = {zone.id: zone for zone in zones}
    stops: list[tuple[UUID, float, float, str | None]] = []
    for zid in body.zone_ids:
        zone = zone_map[zid]
        centroid_shape = to_shape(zone.centroid)
        stops.append((zone.id, centroid_shape.y, centroid_shape.x, zone.display_name))

    # ------------------------------------------------------------------
    # 4. Determine optimized visit order.
    # ------------------------------------------------------------------
    api_key = settings.OPENROUTESERVICE_API_KEY
    ordered_stops: list[tuple[UUID, float, float, str | None]]
    geometry: dict
    total_distance_km: float
    total_duration_minutes: float
    used_ors = False

    if api_key:
        logger.debug("Attempting ORS optimization for %d zones", len(stops))
        job_order = await _ors_optimize(api_key, body.start_lat, body.start_lon, stops)
        if job_order is not None:
            ordered_stops = [stops[i] for i in job_order]
            # Fetch road geometry for the optimized sequence
            ors_result = await _ors_directions_geojson(
                api_key, body.start_lat, body.start_lon, ordered_stops
            )
            if ors_result is not None:
                geometry, total_distance_km, total_duration_minutes = ors_result
                used_ors = True
                logger.info(
                    "ORS route: %d waypoints, %.1f km, %.0f min",
                    len(ordered_stops),
                    total_distance_km,
                    total_duration_minutes,
                )

    if not used_ors:
        # Nearest-neighbour fallback
        logger.info(
            "Using nearest-neighbour fallback for route optimization (%d zones)",
            len(stops),
        )
        ordered_stops = _nearest_neighbour_order(body.start_lat, body.start_lon, stops)
        geometry = _straight_line_geometry(body.start_lat, body.start_lon, ordered_stops)
        total_distance_km = _total_route_distance_km(
            body.start_lat,
            body.start_lon,
            [(lat, lon) for _, lat, lon, _ in ordered_stops],
        )
        total_duration_minutes = (total_distance_km / _FALLBACK_SPEED_KMH) * 60.0

    # ------------------------------------------------------------------
    # 5. Build response waypoints in visit order.
    # ------------------------------------------------------------------
    waypoints = [
        RouteWaypoint(
            zone_id=zone_id,
            display_name=display_name,
            lat=lat,
            lon=lon,
            order=idx,
        )
        for idx, (zone_id, lat, lon, display_name) in enumerate(ordered_stops)
    ]

    return RouteResponse(
        waypoints=waypoints,
        geometry=geometry,
        total_distance_km=round(total_distance_km, 2),
        total_duration_minutes=round(total_duration_minutes, 1),
        generated_at=now,
    )
