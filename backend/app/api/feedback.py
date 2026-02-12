"""Zone feedback endpoints for POC field validation.

Allows roofers to submit simplified feedback after canvassing zones.
Replaces complex canvass_session model with basic rating + notes approach.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from uuid import UUID

from app.database import get_db
from app.api.deps import get_current_user
from app.models.roofer_account import RooferAccount
from app.models.lead_zone import LeadZone
from app.models.zone_feedback import ZoneFeedback
from app.schemas.feedback import (
    ZoneFeedbackCreate,
    ZoneFeedbackResponse,
    ZoneFeedbackListResponse,
)


router = APIRouter(prefix="", tags=["feedback"])


@router.post(
    "/zones/{zone_id}/feedback",
    response_model=ZoneFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_zone_feedback(
    zone_id: UUID,
    feedback_data: ZoneFeedbackCreate,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit feedback for a zone after canvassing.

    Args:
        zone_id: Zone UUID
        feedback_data: Feedback submission (rating, visible_damage, notes)
        current_user: Authenticated roofer account
        db: Database session

    Returns:
        ZoneFeedbackResponse with created feedback

    Raises:
        404: Zone not found
        403: Zone is not active
        409: Roofer already submitted feedback for this zone
    """
    # Verify zone exists and is active
    stmt = select(LeadZone).where(LeadZone.id == zone_id)
    result = await db.execute(stmt)
    zone = result.scalar_one_or_none()

    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")

    if not zone.active:
        raise HTTPException(
            status_code=403,
            detail="Cannot submit feedback for inactive zone"
        )

    # Create feedback record
    feedback = ZoneFeedback(
        lead_zone_id=zone_id,
        roofer_account_id=current_user.id,
        rating=feedback_data.rating,
        visible_damage=feedback_data.visible_damage,
        notes=feedback_data.notes,
        zone_score_at_feedback=zone.composite_score,
    )

    db.add(feedback)

    try:
        await db.commit()
        await db.refresh(feedback)
    except IntegrityError as e:
        await db.rollback()
        # Check if it's the unique constraint violation
        if "uq_zone_feedback_zone_roofer" in str(e.orig):
            raise HTTPException(
                status_code=409,
                detail="You have already submitted feedback for this zone"
            )
        # Re-raise if it's a different integrity error
        raise

    return feedback


@router.get("/feedback/my-history", response_model=ZoneFeedbackListResponse)
async def get_my_feedback_history(
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current roofer's feedback history.

    Args:
        current_user: Authenticated roofer account
        db: Database session

    Returns:
        ZoneFeedbackListResponse with paginated feedback list
    """
    # Query feedback for current user, ordered by newest first
    stmt = (
        select(ZoneFeedback)
        .where(ZoneFeedback.roofer_account_id == current_user.id)
        .order_by(ZoneFeedback.created_at.desc())
    )

    result = await db.execute(stmt)
    feedbacks = result.scalars().all()

    # Count total feedback entries
    count_stmt = (
        select(func.count())
        .select_from(ZoneFeedback)
        .where(ZoneFeedback.roofer_account_id == current_user.id)
    )
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    return ZoneFeedbackListResponse(
        feedbacks=feedbacks,
        total=total,
    )
