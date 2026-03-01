"""Property parcel GeoJSON endpoint for the canvass tracking map layer.

Returns property locations as a GeoJSON FeatureCollection, joined with the
authenticated user's lead pin dispositions. Results are bbox-filtered and
capped at 2000 rows to stay within Fly.io's 256MB memory limit.
"""

import logging

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.lead_pin import LeadPin
from app.models.property import Property
from app.models.roofer_account import RooferAccount
from app.schemas.properties import (
    PropertyGeoJSONFeature,
    PropertyGeoJSONProperties,
    PropertyGeoJSONResponse,
    PropertyResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/properties", tags=["properties"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_bbox(bbox: str) -> tuple[float, float, float, float] | None:
    """Parse 'west,south,east,north' bbox string.

    Returns a (west, south, east, north) float tuple, or None if the string
    is malformed. None causes the endpoint to return an empty FeatureCollection
    rather than a 422 — the frontend should always send a valid viewport bbox.
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


@router.get("/geojson", response_model=PropertyGeoJSONResponse)
async def get_properties_geojson(
    bbox: str = Query(
        ...,
        description="Viewport bounding box as 'west,south,east,north' (required)",
    ),
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PropertyGeoJSONResponse:
    """Return property parcels as a GeoJSON FeatureCollection for map rendering.

    Joins each property with the authenticated user's lead pin disposition so
    the frontend can colour-code canvassed vs uncanvassed parcels in a single
    request. The LEFT JOIN condition includes roofer_account_id so a property
    with a pin from a different user appears with disposition=None.

    Args:
        bbox: Required 'west,south,east,north' viewport bounding box string.
              Returns empty FeatureCollection if the value cannot be parsed.
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        GeoJSON FeatureCollection — at most 2000 Point features.
    """
    coords = _parse_bbox(bbox)
    if coords is None:
        logger.warning("get_properties_geojson: unparseable bbox=%r — returning empty", bbox)
        return PropertyGeoJSONResponse(type="FeatureCollection", features=[])

    west, south, east, north = coords
    bbox_wkt = (
        f"POLYGON(({west} {south},{east} {south},"
        f"{east} {north},{west} {north},{west} {south}))"
    )
    bbox_geom = WKTElement(bbox_wkt, srid=4326)

    # LEFT JOIN lead_pins scoped to this user so disposition is None for
    # properties the current user has not yet pinned.
    stmt = (
        select(
            Property.id,
            Property.location,
            Property.address,
            Property.estimated_roof_age,
            Property.year_built,
            LeadPin.disposition,
        )
        .outerjoin(
            LeadPin,
            (LeadPin.property_id == Property.id)
            & (LeadPin.roofer_account_id == current_user.id),
        )
        .where(Property.location.isnot(None))
        .where(Property.location.ST_Within(bbox_geom))
        .limit(2000)
    )

    result = await db.execute(stmt)
    rows = result.all()

    features = []
    for prop_id, location, address, est_roof_age, year_built, disposition in rows:
        pt = to_shape(location)
        feature = PropertyGeoJSONFeature(
            type="Feature",
            geometry={
                "type": "Point",
                "coordinates": [pt.x, pt.y],
            },
            properties=PropertyGeoJSONProperties(
                id=str(prop_id),
                address=address,
                disposition=disposition,
                estimated_roof_age=est_roof_age,
                year_built=year_built,
            ),
        )
        features.append(feature)

    return PropertyGeoJSONResponse(type="FeatureCollection", features=features)


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PropertyResponse:
    """Get a single property by ID.

    Properties are public parcel records — any authenticated user can view them.
    """
    stmt = select(Property).where(Property.id == property_id)
    result = await db.execute(stmt)
    prop = result.scalar_one_or_none()

    if prop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found",
        )

    # Extract lat/lon from PostGIS geometry
    lat, lon = None, None
    if prop.location:
        pt = to_shape(prop.location)
        lat, lon = pt.y, pt.x

    return PropertyResponse(
        id=prop.id,
        parcel_id=prop.parcel_id,
        address=prop.address,
        owner_name=prop.owner_name,
        year_built=prop.year_built,
        estimated_roof_age=prop.estimated_roof_age,
        assessed_value=prop.assessed_value,
        land_value=prop.land_value,
        improvement_value=prop.improvement_value,
        square_footage=prop.square_footage,
        lot_size_acres=prop.lot_size_acres,
        property_type=prop.property_type,
        zoning=prop.zoning,
        bedrooms=prop.bedrooms,
        bathrooms=prop.bathrooms,
        stories=prop.stories,
        last_sale_date=str(prop.last_sale_date) if prop.last_sale_date else None,
        last_sale_price=prop.last_sale_price,
        latitude=lat,
        longitude=lon,
    )
