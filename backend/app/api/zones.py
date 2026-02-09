"""Lead zone endpoints.

Retrieves scored lead zones filtered by location, score threshold, and date range.
Supports map viewport queries and list views.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping

from app.api.deps import get_current_user
from app.database import get_db
from app.models.lead_zone import LeadZone
from app.models.roofer_account import RooferAccount
from app.models.storm_event import StormEvent
from app.schemas.zones import (
    ZoneListParams,
    ZoneResponse,
    ZoneDetailResponse,
    ZoneListResponse,
    ZoneGeoJSONResponse,
    ZoneGeoJSONFeature,
    GeoJSONGeometry,
    StormEventBrief,
)
from app.scoring.decay import calculate_decay


router = APIRouter(prefix="/zones", tags=["lead-zones"])


@router.get("/geojson", response_model=ZoneGeoJSONResponse)
async def get_zones_geojson(
    min_score: float | None = None,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return active zones as GeoJSON FeatureCollection for map rendering.

    Args:
        min_score: Optional minimum composite score filter
        current_user: Authenticated roofer account
        db: Database session

    Returns:
        GeoJSON FeatureCollection with zone polygons and properties
    """
    # Build query for active zones in user's service area
    stmt = select(LeadZone).where(
        LeadZone.active == True,
        func.ST_Intersects(LeadZone.boundary, current_user.service_area),
    )

    # Apply optional min_score filter
    if min_score is not None:
        stmt = stmt.where(LeadZone.composite_score >= min_score)

    # Execute query
    result = await db.execute(stmt)
    zones = result.scalars().all()

    # Convert zones to GeoJSON features
    features = []
    for zone in zones:
        # Convert PostGIS geometry to GeoJSON
        boundary_shape = to_shape(zone.boundary)
        geom = mapping(boundary_shape)

        # Create feature with zone properties
        feature = ZoneGeoJSONFeature(
            type="Feature",
            geometry=GeoJSONGeometry(
                type=geom["type"],
                coordinates=geom["coordinates"],
            ),
            properties={
                "id": str(zone.id),
                "h3_index": zone.h3_index,
                "composite_score": zone.composite_score,
                "score_band": zone.score_band,
                "max_hail_diameter": zone.max_hail_diameter,
                "max_wind_speed": zone.max_wind_speed,
                "event_count": zone.event_count,
            },
        )
        features.append(feature)

    return ZoneGeoJSONResponse(
        type="FeatureCollection",
        features=features,
    )


@router.get("", response_model=ZoneListResponse)
async def list_zones(
    params: ZoneListParams = Depends(),
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List active lead zones with filtering and pagination.

    Args:
        params: Query parameters (min_score, hail_min, sort_by, page, page_size)
        current_user: Authenticated roofer account
        db: Database session

    Returns:
        Paginated list of zones with total count
    """
    # Build base query for active zones in user's service area
    stmt = select(LeadZone).where(
        LeadZone.active == True,
        func.ST_Intersects(LeadZone.boundary, current_user.service_area),
    )

    # Apply optional filters
    if params.min_score is not None:
        stmt = stmt.where(LeadZone.composite_score >= params.min_score)

    if params.hail_min is not None:
        stmt = stmt.where(LeadZone.max_hail_diameter >= params.hail_min)

    # Apply sorting
    if params.sort_by == "score":
        stmt = stmt.order_by(LeadZone.composite_score.desc())
    elif params.sort_by == "time":
        stmt = stmt.order_by(LeadZone.primary_event_timestamp.desc())
    elif params.sort_by == "hail":
        stmt = stmt.order_by(LeadZone.max_hail_diameter.desc())

    # Count total matching zones before pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Apply pagination
    offset = (params.page - 1) * params.page_size
    stmt = stmt.offset(offset).limit(params.page_size)

    # Execute query
    result = await db.execute(stmt)
    zones = result.scalars().all()

    # Convert zones to response schema
    zone_responses = []
    for zone in zones:
        # Extract centroid coordinates from PostGIS POINT
        centroid_shape = to_shape(zone.centroid)
        centroid_lat = centroid_shape.y
        centroid_lon = centroid_shape.x

        # Map zone to response schema
        zone_response = ZoneResponse(
            id=zone.id,
            h3_index=zone.h3_index,
            composite_score=zone.composite_score,
            damage_prob=zone.damage_prob,
            lead_quality=zone.lead_quality,
            density_bonus=zone.density_bonus,
            predicted_conversion_rate=zone.predicted_conversion_rate,
            score_band=zone.score_band,
            model_version=zone.model_version,
            event_count=zone.event_count,
            max_hail_diameter=zone.max_hail_diameter,
            max_wind_speed=zone.max_wind_speed,
            primary_event_timestamp=zone.primary_event_timestamp,
            expires_at=zone.expires_at,
            centroid_lat=centroid_lat,
            centroid_lon=centroid_lon,
            created_at=zone.created_at,
        )
        zone_responses.append(zone_response)

    return ZoneListResponse(
        zones=zone_responses,
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{zone_id}", response_model=ZoneDetailResponse)
async def get_zone(
    zone_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed information for a specific lead zone.

    Args:
        zone_id: Zone UUID
        current_user: Authenticated roofer account
        db: Database session

    Returns:
        Zone detail with decay-adjusted score and contributing events

    Raises:
        404: Zone not found
        403: Zone outside user's service area
    """
    # Query zone by ID
    stmt = select(LeadZone).where(LeadZone.id == zone_id)
    result = await db.execute(stmt)
    zone = result.scalar_one_or_none()

    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")

    # Verify zone is within user's service area
    intersects_stmt = select(
        func.ST_Intersects(LeadZone.boundary, current_user.service_area)
    ).where(LeadZone.id == zone_id)
    intersects_result = await db.execute(intersects_stmt)
    intersects = intersects_result.scalar_one()

    if not intersects:
        raise HTTPException(
            status_code=403,
            detail="Zone is outside your service area"
        )

    # Extract centroid coordinates
    centroid_shape = to_shape(zone.centroid)
    centroid_lat = centroid_shape.y
    centroid_lon = centroid_shape.x

    # Recalculate decay-adjusted score from raw sub-scores
    raw_composite = (
        zone.damage_prob * 0.50 +
        zone.lead_quality * 0.30 +
        zone.density_bonus * 0.20
    )
    decay_factor = calculate_decay(zone.primary_event_timestamp)
    decay_adjusted_score = max(0, min(raw_composite * decay_factor, 100))

    # Calculate hours since storm
    hours_since = (
        datetime.now(timezone.utc) - zone.primary_event_timestamp
    ).total_seconds() / 3600

    # Fetch contributing events within zone boundary
    events_stmt = select(StormEvent).where(
        StormEvent.scored == True,
        func.ST_Within(StormEvent.location, zone.boundary)
    ).order_by(StormEvent.event_timestamp.desc())

    events_result = await db.execute(events_stmt)
    events = events_result.scalars().all()

    # Convert events to StormEventBrief
    event_briefs = [
        StormEventBrief(
            id=event.id,
            source=event.source,
            event_type=event.event_type,
            hail_diameter=event.hail_diameter,
            wind_speed=event.wind_speed,
            event_timestamp=event.event_timestamp,
            radar_confidence=event.radar_confidence,
        )
        for event in events
    ]

    # Build detail response
    return ZoneDetailResponse(
        id=zone.id,
        h3_index=zone.h3_index,
        composite_score=zone.composite_score,
        damage_prob=zone.damage_prob,
        lead_quality=zone.lead_quality,
        density_bonus=zone.density_bonus,
        predicted_conversion_rate=zone.predicted_conversion_rate,
        score_band=zone.score_band,
        model_version=zone.model_version,
        event_count=zone.event_count,
        max_hail_diameter=zone.max_hail_diameter,
        max_wind_speed=zone.max_wind_speed,
        primary_event_timestamp=zone.primary_event_timestamp,
        expires_at=zone.expires_at,
        centroid_lat=centroid_lat,
        centroid_lon=centroid_lon,
        created_at=zone.created_at,
        decay_adjusted_score=decay_adjusted_score,
        hours_since_storm=hours_since,
        events=event_briefs,
    )


@router.get("/{zone_id}/events", response_model=list[StormEventBrief])
async def get_zone_events(
    zone_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all storm events contributing to a specific zone.

    Args:
        zone_id: Zone UUID
        current_user: Authenticated roofer account
        db: Database session

    Returns:
        List of storm events within zone boundary

    Raises:
        404: Zone not found
        403: Zone outside user's service area
    """
    # Query zone by ID
    stmt = select(LeadZone).where(LeadZone.id == zone_id)
    result = await db.execute(stmt)
    zone = result.scalar_one_or_none()

    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")

    # Verify zone is within user's service area
    intersects_stmt = select(
        func.ST_Intersects(LeadZone.boundary, current_user.service_area)
    ).where(LeadZone.id == zone_id)
    intersects_result = await db.execute(intersects_stmt)
    intersects = intersects_result.scalar_one()

    if not intersects:
        raise HTTPException(
            status_code=403,
            detail="Zone is outside your service area"
        )

    # Fetch events within zone boundary
    events_stmt = select(StormEvent).where(
        func.ST_Within(StormEvent.location, zone.boundary)
    ).order_by(StormEvent.event_timestamp.desc())

    events_result = await db.execute(events_stmt)
    events = events_result.scalars().all()

    # Convert to StormEventBrief
    return [
        StormEventBrief(
            id=event.id,
            source=event.source,
            event_type=event.event_type,
            hail_diameter=event.hail_diameter,
            wind_speed=event.wind_speed,
            event_timestamp=event.event_timestamp,
            radar_confidence=event.radar_confidence,
        )
        for event in events
    ]
