"""Canvass session endpoints for door knock tracking.

Allows roofers to start, update, and review canvassing sessions per zone.
Multiple sessions per zone are allowed (different visits on different days).
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.canvass_session import CanvassSession
from app.models.lead_zone import LeadZone
from app.models.roofer_account import RooferAccount
from app.schemas.canvass_session import (
    CanvassSessionCreate,
    CanvassSessionUpdate,
    CanvassSessionResponse,
    CanvassSessionListResponse,
)

router = APIRouter(tags=["canvass-sessions"])


@router.post(
    "/zones/{zone_id}/canvass",
    response_model=CanvassSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_canvass_session(
    zone_id: UUID,
    data: CanvassSessionCreate,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvassSessionResponse:
    """Start a new canvassing session in a zone."""
    stmt = select(LeadZone).where(LeadZone.id == zone_id)
    result = await db.execute(stmt)
    zone = result.scalar_one_or_none()
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")

    session = CanvassSession(
        lead_zone_id=zone_id,
        roofer_account_id=current_user.id,
        notes=data.notes,
        zone_score_at_time=zone.composite_score,
        doors_knocked=0,
        doors_answered=0,
        visible_damage_count=0,
        homeowner_interested=0,
    )
    db.add(session)
    await db.commit()
    # Update zone staleness tracking
    zone.last_canvassed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)
    return session


@router.put(
    "/canvass/{session_id}",
    response_model=CanvassSessionResponse,
)
async def update_canvass_session(
    session_id: UUID,
    data: CanvassSessionUpdate,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvassSessionResponse:
    """Update counters on an active canvass session."""
    stmt = select(CanvassSession).where(
        CanvassSession.id == session_id,
        CanvassSession.roofer_account_id == current_user.id,
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(session, field, value)

    await db.commit()
    # Update zone staleness tracking
    zone_stmt = select(LeadZone).where(LeadZone.id == session.lead_zone_id)
    zone_result = await db.execute(zone_stmt)
    zone = zone_result.scalar_one_or_none()
    if zone:
        zone.last_canvassed_at = datetime.now(timezone.utc)
        await db.commit()
    await db.refresh(session)
    return session


@router.get(
    "/zones/{zone_id}/canvass",
    response_model=CanvassSessionListResponse,
)
async def get_zone_canvass_history(
    zone_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvassSessionListResponse:
    """Get canvass session history for a zone (current user only)."""
    stmt = (
        select(CanvassSession)
        .where(
            CanvassSession.lead_zone_id == zone_id,
            CanvassSession.roofer_account_id == current_user.id,
        )
        .order_by(CanvassSession.created_at.desc())
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    count_stmt = (
        select(func.count())
        .select_from(CanvassSession)
        .where(
            CanvassSession.lead_zone_id == zone_id,
            CanvassSession.roofer_account_id == current_user.id,
        )
    )
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    return CanvassSessionListResponse(sessions=sessions, total=total)


@router.get(
    "/canvass/my-history",
    response_model=CanvassSessionListResponse,
)
async def get_my_canvass_history(
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CanvassSessionListResponse:
    """Get all canvass sessions for the current roofer."""
    stmt = (
        select(CanvassSession)
        .where(CanvassSession.roofer_account_id == current_user.id)
        .order_by(CanvassSession.created_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    count_stmt = (
        select(func.count())
        .select_from(CanvassSession)
        .where(CanvassSession.roofer_account_id == current_user.id)
    )
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    return CanvassSessionListResponse(sessions=sessions, total=total)
