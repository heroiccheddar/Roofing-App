"""Lead pin endpoints for address-level sales tracking.

Roofers drop pins on the map, assign a disposition (sales funnel status),
and build a full interaction history. All queries are scoped to the
authenticated user's account — no cross-user data is exposed.
"""

import csv
import io
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.lead_pin import LeadPin, PinActivity
from app.models.pin_photo import PinPhoto
from app.models.roofer_account import RooferAccount
from app.services.s3_photos import delete_photos_batch
from app.schemas.leads import (
    LeadPinCreate,
    LeadPinGeoJSONFeature,
    LeadPinGeoJSONProperties,
    LeadPinGeoJSONResponse,
    LeadPinListResponse,
    LeadPinResponse,
    LeadPinUpdate,
    PinActivityCreate,
    PinActivityListResponse,
    PinActivityResponse,
    VALID_DISPOSITIONS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leads", tags=["lead-pins"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pin_to_response(pin: LeadPin, roofer_name: str | None = None) -> LeadPinResponse:
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
        callback_date=pin.callback_date,
        contact_name=pin.contact_name,
        contact_phone=pin.contact_phone,
        contact_email=pin.contact_email,
        created_at=pin.created_at,
        updated_at=pin.updated_at,
        roofer_name=roofer_name,
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


async def _get_team_member_ids(
    current_user: RooferAccount, db: AsyncSession
) -> list[UUID] | None:
    """Return all org member IDs if user is in an org, else None."""
    if current_user.organization_id is None:
        return None
    stmt = select(RooferAccount.id).where(
        RooferAccount.organization_id == current_user.organization_id
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=LeadPinListResponse)
async def list_lead_pins(
    bbox: str | None = Query(
        None,
        description="Viewport bounding box as 'west,south,east,north'",
    ),
    team: bool = Query(False, description="Include team members' pins"),
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadPinListResponse:
    """List all lead pins for the current user with optional bbox filter.

    Args:
        bbox: Optional 'west,south,east,north' string to restrict results
              to a map viewport.
        team: If True and user is in an org, include all org members' pins.
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        LeadPinListResponse with pins and total count.
    """
    member_ids: list[UUID] | None = None
    if team:
        member_ids = await _get_team_member_ids(current_user, db)

    if team and member_ids is not None:
        stmt = (
            select(LeadPin, RooferAccount.company_name)
            .outerjoin(RooferAccount, LeadPin.roofer_account_id == RooferAccount.id)
            .where(LeadPin.roofer_account_id.in_(member_ids))
        )
    else:
        stmt = select(LeadPin, RooferAccount.company_name).outerjoin(
            RooferAccount, LeadPin.roofer_account_id == RooferAccount.id
        ).where(LeadPin.roofer_account_id == current_user.id)

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
    rows = result.all()

    pins_out = []
    for pin, company_name in rows:
        name = company_name if (team and pin.roofer_account_id != current_user.id) else None
        pins_out.append(_pin_to_response(pin, roofer_name=name))

    return LeadPinListResponse(
        pins=pins_out,
        total=len(pins_out),
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
    team: bool = Query(False),
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadPinGeoJSONResponse:
    """Return user's lead pins as a GeoJSON FeatureCollection for map rendering.

    Only fetches id, location, disposition, and roofer_account_id — no heavy columns.
    This endpoint is optimised for map tile rendering at any zoom level.

    Args:
        bbox: Optional 'west,south,east,north' viewport filter.
        disposition: Optional disposition filter.
        team: If True and user is in an org, include all org members' pins.
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        GeoJSON FeatureCollection with Point features.
    """
    member_ids: list[UUID] | None = None
    if team:
        member_ids = await _get_team_member_ids(current_user, db)

    # Lightweight: only select the columns we need for the map
    stmt = select(LeadPin.id, LeadPin.location, LeadPin.disposition, LeadPin.roofer_account_id)

    if team and member_ids is not None:
        stmt = stmt.where(LeadPin.roofer_account_id.in_(member_ids))
    else:
        stmt = stmt.where(LeadPin.roofer_account_id == current_user.id)

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
    for pin_id, location, disp, pin_owner_id in rows:
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
                is_own=(pin_owner_id == current_user.id),
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
        callback_date=body.callback_date,
        contact_name=body.contact_name,
        contact_phone=body.contact_phone,
        contact_email=body.contact_email,
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


@router.get("/callbacks", response_model=LeadPinListResponse)
async def get_lead_pin_callbacks(
    team: bool = Query(False),
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadPinListResponse:
    """Return all lead pins that need follow-up, sorted by urgency.

    Includes pins with disposition='callback' or any pin with a callback_date set.
    Sorted by callback_date ASC (overdue first) with nulls last.

    Args:
        team: If True and user is in an org, include all org members' callback pins.
        current_user: Authenticated roofer account.
        db: Database session.
    """
    member_ids: list[UUID] | None = None
    if team:
        member_ids = await _get_team_member_ids(current_user, db)

    if team and member_ids is not None:
        stmt = (
            select(LeadPin, RooferAccount.company_name)
            .outerjoin(RooferAccount, LeadPin.roofer_account_id == RooferAccount.id)
            .where(
                LeadPin.roofer_account_id.in_(member_ids),
                or_(
                    LeadPin.disposition == "callback",
                    LeadPin.callback_date.isnot(None),
                ),
            )
            .order_by(LeadPin.callback_date.asc().nullslast(), LeadPin.updated_at.desc())
        )
    else:
        stmt = (
            select(LeadPin, RooferAccount.company_name)
            .outerjoin(RooferAccount, LeadPin.roofer_account_id == RooferAccount.id)
            .where(
                LeadPin.roofer_account_id == current_user.id,
                or_(
                    LeadPin.disposition == "callback",
                    LeadPin.callback_date.isnot(None),
                ),
            )
            .order_by(LeadPin.callback_date.asc().nullslast(), LeadPin.updated_at.desc())
        )

    result = await db.execute(stmt)
    rows = result.all()

    pins_out = []
    for pin, company_name in rows:
        name = company_name if (team and pin.roofer_account_id != current_user.id) else None
        pins_out.append(_pin_to_response(pin, roofer_name=name))

    return LeadPinListResponse(
        pins=pins_out,
        total=len(pins_out),
    )


@router.get("/export")
async def export_leads_csv(
    team: bool = Query(False, description="Include team members' pins"),
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export all lead pins as a CSV file download.

    Args:
        team: If True and user is in an org, include all org members' pins.
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        StreamingResponse with CSV content.
    """
    member_ids: list[UUID] | None = None
    if team:
        member_ids = await _get_team_member_ids(current_user, db)

    if team and member_ids is not None:
        stmt = (
            select(LeadPin, RooferAccount.company_name)
            .outerjoin(RooferAccount, LeadPin.roofer_account_id == RooferAccount.id)
            .where(LeadPin.roofer_account_id.in_(member_ids))
        )
    else:
        stmt = select(LeadPin, RooferAccount.company_name).outerjoin(
            RooferAccount, LeadPin.roofer_account_id == RooferAccount.id
        ).where(LeadPin.roofer_account_id == current_user.id)

    stmt = stmt.order_by(LeadPin.created_at.desc())
    result = await db.execute(stmt)
    rows = result.all()

    # Build CSV in memory
    buf = io.StringIO()
    writer = csv.writer(buf)
    headers = [
        "id", "address", "disposition", "contact_name", "contact_phone",
        "contact_email", "notes", "callback_date", "lat", "lon",
        "created_at", "updated_at",
    ]
    if team:
        headers.append("roofer_name")
    writer.writerow(headers)

    for pin, company_name in rows:
        pt = to_shape(pin.location)
        row = [
            str(pin.id),
            pin.address or "",
            pin.disposition,
            pin.contact_name or "",
            pin.contact_phone or "",
            pin.contact_email or "",
            pin.notes or "",
            pin.callback_date.isoformat() if pin.callback_date else "",
            pt.y,
            pt.x,
            pin.created_at.isoformat() if pin.created_at else "",
            pin.updated_at.isoformat() if pin.updated_at else "",
        ]
        if team:
            name = company_name if pin.roofer_account_id != current_user.id else ""
            row.append(name or "")
        writer.writerow(row)

    buf.seek(0)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"roofiq_leads_{today}.csv"

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{pin_id}", response_model=LeadPinResponse)
async def get_lead_pin(
    pin_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeadPinResponse:
    """Get a single lead pin by ID."""
    member_ids = await _get_team_member_ids(current_user, db)
    owner_filter = (
        LeadPin.roofer_account_id.in_(member_ids)
        if member_ids
        else LeadPin.roofer_account_id == current_user.id
    )
    stmt = (
        select(LeadPin, RooferAccount.company_name)
        .outerjoin(RooferAccount, LeadPin.roofer_account_id == RooferAccount.id)
        .where(LeadPin.id == pin_id, owner_filter)
    )
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead pin not found")
    pin, company_name = row
    name = company_name if pin.roofer_account_id != current_user.id else None
    return _pin_to_response(pin, roofer_name=name)


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
    if body.callback_date is not None:
        pin.callback_date = body.callback_date
    # Clear callback_date if disposition changed away from callback
    if body.disposition is not None and body.disposition != "callback" and body.callback_date is None:
        pin.callback_date = None
    if body.contact_name is not None:
        pin.contact_name = body.contact_name
    if body.contact_phone is not None:
        pin.contact_phone = body.contact_phone
    if body.contact_email is not None:
        pin.contact_email = body.contact_email

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

    # Clean up S3 photos before deleting pin (DB rows cascade-delete via FK)
    photo_stmt = select(PinPhoto.s3_key).where(PinPhoto.lead_pin_id == pin_id)
    photo_result = await db.execute(photo_stmt)
    s3_keys = [row[0] for row in photo_result.all()]
    if s3_keys:
        try:
            delete_photos_batch(s3_keys)
        except Exception:
            logger.warning("Failed to delete S3 photos for pin %s", pin_id)

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


@router.post(
    "/{pin_id}/activities",
    response_model=PinActivityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_pin_activity(
    pin_id: UUID,
    body: PinActivityCreate,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PinActivityResponse:
    """Log a visit note on a lead pin without changing its disposition.

    Creates a PinActivity entry with the pin's current disposition and the
    provided notes. This lets reps record door-knock outcomes without
    needing to update the sales funnel status.

    Args:
        pin_id: UUID of the pin to log activity on.
        body: Activity data (notes field required).
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        The newly created PinActivityResponse.

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

    activity = PinActivity(
        lead_pin_id=pin.id,
        roofer_account_id=current_user.id,
        disposition=pin.disposition,
        notes=body.notes,
    )
    db.add(activity)
    await db.commit()
    await db.refresh(activity)

    return PinActivityResponse(
        id=activity.id,
        lead_pin_id=activity.lead_pin_id,
        disposition=activity.disposition,
        notes=activity.notes,
        created_at=activity.created_at,
    )
