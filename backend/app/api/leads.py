"""Lead pin endpoints for address-level sales tracking.

Roofers drop pins on the map, assign a disposition (sales funnel status),
and build a full interaction history. All queries are scoped to the
authenticated user's account — no cross-user data is exposed.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.lead_pin import LeadPin, PinActivity
from app.models.roofer_account import RooferAccount
from app.schemas.leads import (
    LeadPinCreate,
    LeadPinGeoJSONFeature,
    LeadPinGeoJSONProperties,
    LeadPinGeoJSONResponse,
    LeadPinListResponse,
    LeadPinResponse,
    LeadPinUpdate,
    PinActivityListResponse,
    PinActivityResponse,
    VALID_DISPOSITIONS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leads", tags=["lead-pins"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pin_to_response(pin: LeadPin) -> LeadPinResponse:
    """Convert a LeadPin ORM object to a LeadPinResponse schema.

    Extracts lat/lon from the PostGIS POINT geometry so the response
    never exposes raw WKB bytes to callers.
    """
    pt = to_shape(pin.location)
    return LeadPinResponse(
        id=pin.id,
        roofer_account_id=pin.roofer_account_id,
        property_id=pin.property_id,
        lead_zone_id=pin.lead_zone_id,
        lat=pt.y,
        lon=pt.x,
        address=pin.address,
        disposition=pin.disposition,
        notes=pin.notes,
        created_at=pin.created_at,
        updated_at=pin.updated_at,
    )


def _parse_bbox(bbox: str) -> tuple[float, float, float, float] | None:
    """Parse 'west,south,east,north' bbox string.

    Returns a (west, south, east, north) float tuple, or None if
    the string is malformed. Errors are surfaced to the caller as None
    so that the endpoint can fall back to returning all user pins.
    """
    try:
        parts = [float(x) for x in bbox.split(",")]
        if len(parts) != 4:
            return None
        return tuple(parts)  # type: ignore[return-value]
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=LeadPinListResponse)
async def list_lead_pins(
    bbox: str | None = Query(
        None,
        description="Viewport bounding box as 'west,south,east,north'",
    ),
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadPinListResponse:
    """List all lead pins for the current user with optional bbox filter.

    Args:
        bbox: Optional 'west,south,east,north' string to restrict results
              to a map viewport.
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        LeadPinListResponse with pins and total count.
    """
    stmt = select(LeadPin).where(
        LeadPin.roofer_account_id == current_user.id
    )

    if bbox:
        coords = _parse_bbox(bbox)
        if coords:
            west, south, east, north = coords
            bbox_wkt = (
                f"POLYGON(({west} {south},{east} {south},"
                f"{east} {north},{west} {north},{west} {south}))"
            )
            bbox_geom = WKTElement(bbox_wkt, srid=4326)
            stmt = stmt.where(func.ST_Within(LeadPin.location, bbox_geom))

    stmt = stmt.order_by(LeadPin.created_at.desc())

    result = await db.execute(stmt)
    pins = result.scalars().all()

    return LeadPinListResponse(
        pins=[_pin_to_response(p) for p in pins],
        total=len(pins),
    )


@router.get("/geojson", response_model=LeadPinGeoJSONResponse)
async def get_lead_pins_geojson(
    bbox: str | None = Query(
        None,
        description="Viewport bounding box as 'west,south,east,north'",
    ),
    disposition: str | None = Query(
        None,
        description="Filter by disposition value",
    ),
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadPinGeoJSONResponse:
    """Return user's lead pins as a GeoJSON FeatureCollection for map rendering.

    Only fetches id, location, and disposition — no joins, no heavy columns.
    This endpoint is optimised for map tile rendering at any zoom level.

    Args:
        bbox: Optional 'west,south,east,north' viewport filter.
        disposition: Optional disposition filter.
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        GeoJSON FeatureCollection with Point features.
    """
    # Lightweight: only select the columns we need for the map
    stmt = (
        select(LeadPin.id, LeadPin.location, LeadPin.disposition)
        .where(LeadPin.roofer_account_id == current_user.id)
    )

    if bbox:
        coords = _parse_bbox(bbox)
        if coords:
            west, south, east, north = coords
            bbox_wkt = (
                f"POLYGON(({west} {south},{east} {south},"
                f"{east} {north},{west} {north},{west} {south}))"
            )
            bbox_geom = WKTElement(bbox_wkt, srid=4326)
            stmt = stmt.where(func.ST_Within(LeadPin.location, bbox_geom))

    if disposition:
        if disposition not in VALID_DISPOSITIONS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid disposition filter. Valid values: {sorted(VALID_DISPOSITIONS)}",
            )
        stmt = stmt.where(LeadPin.disposition == disposition)

    result = await db.execute(stmt)
    rows = result.all()

    features = []
    for pin_id, location, disp in rows:
        pt = to_shape(location)
        feature = LeadPinGeoJSONFeature(
            type="Feature",
            geometry={
                "type": "Point",
                "coordinates": [pt.x, pt.y],
            },
            properties=LeadPinGeoJSONProperties(
                id=str(pin_id),
                disposition=disp,
            ),
        )
        features.append(feature)

    return LeadPinGeoJSONResponse(type="FeatureCollection", features=features)


@router.post("", response_model=LeadPinResponse, status_code=status.HTTP_201_CREATED)
async def create_lead_pin(
    body: LeadPinCreate,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadPinResponse:
    """Create a new lead pin at the given coordinates.

    Both the LeadPin row and its initial PinActivity row are created in
    a single transaction — the activity history always starts at creation.

    Args:
        body: Pin creation payload (lat, lon, disposition, …).
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        LeadPinResponse for the newly created pin (HTTP 201).
    """
    point_wkt = WKTElement(f"POINT({body.lon} {body.lat})", srid=4326)

    pin = LeadPin(
        roofer_account_id=current_user.id,
        property_id=body.property_id,
        lead_zone_id=body.lead_zone_id,
        location=point_wkt,
        address=body.address,
        disposition=body.disposition,
        notes=body.notes,
    )
    db.add(pin)
    await db.flush()  # populate pin.id before creating the activity

    activity = PinActivity(
        lead_pin_id=pin.id,
        roofer_account_id=current_user.id,
        disposition=body.disposition,
        notes=body.notes,
    )
    db.add(activity)

    await db.commit()
    await db.refresh(pin)

    return _pin_to_response(pin)


@router.put("/{pin_id}", response_model=LeadPinResponse)
async def update_lead_pin(
    pin_id: UUID,
    body: LeadPinUpdate,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadPinResponse:
    """Update the disposition and/or notes on a lead pin.

    A new PinActivity row is always recorded so the full history is
    preserved even if the disposition did not change.

    Args:
        pin_id: UUID of the pin to update.
        body: Fields to update (disposition and/or notes).
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        Updated LeadPinResponse.

    Raises:
        404: Pin not found or does not belong to the current user.
    """
    stmt = select(LeadPin).where(
        LeadPin.id == pin_id,
        LeadPin.roofer_account_id == current_user.id,
    )
    result = await db.execute(stmt)
    pin = result.scalar_one_or_none()

    if pin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead pin not found",
        )

    # Apply updates — only change fields that were provided
    if body.disposition is not None:
        pin.disposition = body.disposition
    if body.notes is not None:
        pin.notes = body.notes

    # Record the interaction in the activity log regardless of what changed
    activity = PinActivity(
        lead_pin_id=pin.id,
        roofer_account_id=current_user.id,
        disposition=pin.disposition,
        notes=body.notes,
    )
    db.add(activity)

    await db.commit()
    await db.refresh(pin)

    return _pin_to_response(pin)


@router.delete("/{pin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead_pin(
    pin_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a lead pin and all its activity history.

    The FK cascade on pin_activities.lead_pin_id handles activity deletion
    at the database level — no explicit activity deletion is required.

    Args:
        pin_id: UUID of the pin to delete.
        current_user: Authenticated roofer account.
        db: Database session.

    Raises:
        404: Pin not found or does not belong to the current user.
    """
    stmt = select(LeadPin).where(
        LeadPin.id == pin_id,
        LeadPin.roofer_account_id == current_user.id,
    )
    result = await db.execute(stmt)
    pin = result.scalar_one_or_none()

    if pin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead pin not found",
        )

    await db.delete(pin)
    await db.commit()


@router.get("/{pin_id}/activities", response_model=PinActivityListResponse)
async def get_pin_activities(
    pin_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PinActivityListResponse:
    """Return the full activity timeline for a lead pin ordered newest first.

    Args:
        pin_id: UUID of the pin whose history to retrieve.
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        PinActivityListResponse with activities and total count.

    Raises:
        404: Pin not found or does not belong to the current user.
    """
    # Verify the pin exists and belongs to the current user
    pin_stmt = select(LeadPin).where(
        LeadPin.id == pin_id,
        LeadPin.roofer_account_id == current_user.id,
    )
    pin_result = await db.execute(pin_stmt)
    pin = pin_result.scalar_one_or_none()

    if pin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead pin not found",
        )

    # Fetch activities ordered newest first
    activity_stmt = (
        select(PinActivity)
        .where(PinActivity.lead_pin_id == pin_id)
        .order_by(PinActivity.created_at.desc())
    )
    activity_result = await db.execute(activity_stmt)
    activities = activity_result.scalars().all()

    return PinActivityListResponse(
        activities=[
            PinActivityResponse(
                id=a.id,
                lead_pin_id=a.lead_pin_id,
                disposition=a.disposition,
                notes=a.notes,
                created_at=a.created_at,
            )
            for a in activities
        ],
        total=len(activities),
    )
