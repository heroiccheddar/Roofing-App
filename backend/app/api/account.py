"""Roofer account management endpoints.

Handles profile updates, service area configuration, and subscription management.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from geoalchemy2.shape import to_shape
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.api.deps import get_current_user
from app.database import get_db
from app.models.roofer_account import RooferAccount
from app.schemas.account import (
    AccountResponse,
    AlertPreferences,
    ServiceAreaUpdate,
)


def _account_response(user: RooferAccount) -> AccountResponse:
    """Build AccountResponse with computed service area centroid."""
    lat, lon = None, None
    if user.service_area is not None:
        try:
            centroid = to_shape(user.service_area).centroid
            lat, lon = centroid.y, centroid.x
        except Exception:
            pass
    resp = AccountResponse.model_validate(user)
    resp.service_area_lat = lat
    resp.service_area_lon = lon
    return resp

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/profile", response_model=AccountResponse)
async def get_profile(
    current_user: RooferAccount = Depends(get_current_user),
) -> AccountResponse:
    """Get the current user's account profile.

    Args:
        current_user: Authenticated user from JWT token

    Returns:
        AccountResponse: User account profile including preferences
    """
    return _account_response(current_user)


@router.put("/service-area", response_model=AccountResponse)
async def update_service_area(
    body: ServiceAreaUpdate,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountResponse:
    """Update the user's service area using a point and radius.

    Creates a circular polygon from the provided center point (lat/lon) and radius
    using PostGIS ST_Buffer on a geography type.

    Args:
        body: Service area parameters (lat, lon, radius_km)
        current_user: Authenticated user from JWT token
        db: Database session

    Returns:
        AccountResponse: Updated account profile

    Raises:
        HTTPException: 500 if database update fails
    """
    try:
        # Create a buffered polygon using PostGIS ST_Buffer on geography
        # ST_Buffer takes meters, so convert km to meters
        # Use ST_GeogFromText to create a geography point, buffer it, then cast back to geometry
        from geoalchemy2 import Geometry as GeoType
        service_area_expr = func.ST_SetSRID(
            func.ST_Buffer(
                func.ST_GeogFromText(f'POINT({body.lon} {body.lat})'),
                body.radius_km * 1000
            ).cast(GeoType(geometry_type='POLYGON', srid=4326)),
            4326
        )

        # Update the user's service area
        current_user.service_area = service_area_expr

        # Commit the change
        await db.commit()
        await db.refresh(current_user)

        return _account_response(current_user)

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update service area: {str(e)}",
        )


@router.put("/alert-preferences", response_model=AccountResponse)
async def update_alert_preferences(
    body: AlertPreferences,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountResponse:
    """Update the user's alert preferences.

    Configures thresholds, channels, and quiet hours for storm alerts.

    Args:
        body: Alert preferences configuration
        current_user: Authenticated user from JWT token
        db: Database session

    Returns:
        AccountResponse: Updated account profile

    Raises:
        HTTPException: 500 if database update fails
    """
    try:
        # Convert AlertPreferences to dict for JSONB storage
        current_user.alert_preferences = body.model_dump(mode='json')

        # Commit the change
        await db.commit()
        await db.refresh(current_user)

        return _account_response(current_user)

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update alert preferences: {str(e)}",
        )
