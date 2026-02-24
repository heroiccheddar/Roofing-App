"""Pydantic schemas for the route optimization endpoint.

RouteRequest accepts a list of zone UUIDs and a starting coordinate.
RouteResponse returns the optimized visit order, road geometry, and
estimated distance/duration.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    """Request body for POST /route.

    zone_ids must contain between 2 and 10 zone UUIDs — the minimum needed
    for a meaningful optimization and the maximum supported by the fallback
    nearest-neighbor TSP implementation within a reasonable response time.
    """

    zone_ids: list[UUID] = Field(..., min_length=2, max_length=10)
    start_lat: float = Field(..., ge=-90, le=90)
    start_lon: float = Field(..., ge=-180, le=180)


class RouteWaypoint(BaseModel):
    """One stop in the optimized route."""

    zone_id: UUID
    display_name: str | None = None
    lat: float
    lon: float
    order: int


class RouteResponse(BaseModel):
    """Optimized route returned by POST /route.

    geometry is a GeoJSON LineString (or straight-line fallback) covering
    the full route from start through all waypoints in visit order.
    """

    waypoints: list[RouteWaypoint] = Field(default_factory=list)
    geometry: dict
    total_distance_km: float
    total_duration_minutes: float
    generated_at: datetime
