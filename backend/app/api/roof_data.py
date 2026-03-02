"""Roof data endpoint — fetches Google Solar API measurements for a property.

POST /{property_id}/roof-data triggers an on-demand Solar API lookup (or
returns cached data if the property was fetched within CACHE_TTL_DAYS).
The result is stored on the property record for future requests.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.property import Property
from app.models.roofer_account import RooferAccount
from app.schemas.properties import RoofDataResponse
from app.services.google_solar import get_roof_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/properties", tags=["roof-data"])


@router.post("/{property_id}/roof-data", response_model=RoofDataResponse)
async def fetch_roof_data(
    property_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoofDataResponse:
    """Fetch or return cached roof geometry for a property.

    On the first call the Google Solar API is queried and results are stored
    on the property record. Subsequent calls within CACHE_TTL_DAYS return
    the stored values without hitting the API.

    Args:
        property_id: UUID of the property to look up.
        current_user: Authenticated roofer account (any authenticated user
                      may request roof data — properties are public records).
        db: Database session.

    Returns:
        RoofDataResponse with area, pitch, facet, and imagery metadata.

    Raises:
        503: GOOGLE_SOLAR_API_KEY is not configured.
        404: Property does not exist.
        400: No building found at the property's coordinates (ValueError from service).
        503: Google Solar API call failed (unexpected exception from service).
    """
    if not settings.GOOGLE_SOLAR_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Solar API is not configured",
        )

    stmt = select(Property).where(Property.id == property_id)
    result = await db.execute(stmt)
    prop = result.scalar_one_or_none()

    if prop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found",
        )

    try:
        data = await get_roof_data(db, prop)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception(
            "fetch_roof_data: Solar API error for property %s: %s", property_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Solar API request failed",
        ) from exc

    return RoofDataResponse(**data)
