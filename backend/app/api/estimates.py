"""Estimate endpoints for the Estimate Builder feature.

Roofers create itemized estimates against a lead pin, update them as
negotiations progress, and track lifecycle status (draft → sent →
accepted/declined). All queries are scoped to the authenticated user's
account — no cross-user data is exposed.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.estimate import Estimate
from app.models.lead_pin import LeadPin
from app.models.roofer_account import RooferAccount
from app.schemas.estimates import (
    EstimateCreate,
    EstimateListResponse,
    EstimateResponse,
    EstimateUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/estimates", tags=["estimates"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_totals(line_items: list, tax_rate: float) -> tuple[float, float]:
    """Compute subtotal and total from line items and tax rate.

    Args:
        line_items: List of LineItem objects (Pydantic) or dicts.
        tax_rate: Decimal tax rate (e.g. 0.0825 for 8.25%).

    Returns:
        (subtotal, total) where total = subtotal * (1 + tax_rate).
    """
    if line_items and hasattr(line_items[0], "total"):
        # Pydantic LineItem objects (create/update path)
        subtotal = sum(item.total for item in line_items)
    else:
        # Dicts (should not occur, but guard defensively)
        subtotal = sum(item.get("total", 0) for item in line_items)

    total = subtotal * (1 + tax_rate)
    return round(subtotal, 2), round(total, 2)


def _estimate_to_response(estimate: Estimate) -> EstimateResponse:
    """Convert an Estimate ORM object to an EstimateResponse schema.

    Casts Numeric columns to float so Pydantic receives plain Python numbers.
    JSONB line_items come back as a list of dicts — EstimateResponse accepts
    both dicts and LineItem objects via Pydantic's coercion.
    """
    return EstimateResponse(
        id=estimate.id,
        lead_pin_id=estimate.lead_pin_id,
        roofer_account_id=estimate.roofer_account_id,
        line_items=estimate.line_items,
        subtotal=float(estimate.subtotal),
        tax_rate=float(estimate.tax_rate),
        total=float(estimate.total),
        status=estimate.status,
        notes=estimate.notes,
        created_at=estimate.created_at,
        updated_at=estimate.updated_at,
    )


async def _get_owned_estimate(
    estimate_id: UUID,
    current_user: RooferAccount,
    db: AsyncSession,
) -> Estimate:
    """Fetch an estimate and verify it belongs to the current user.

    Args:
        estimate_id: UUID of the estimate to fetch.
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        The Estimate ORM object.

    Raises:
        404: Estimate not found or does not belong to the current user.
    """
    stmt = select(Estimate).where(
        Estimate.id == estimate_id,
        Estimate.roofer_account_id == current_user.id,
    )
    result = await db.execute(stmt)
    estimate = result.scalar_one_or_none()

    if estimate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Estimate not found",
        )
    return estimate


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=EstimateResponse, status_code=status.HTTP_201_CREATED)
async def create_estimate(
    body: EstimateCreate,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EstimateResponse:
    """Create a new estimate for a lead pin.

    Verifies the lead pin belongs to the current user, then creates the
    estimate with computed subtotal and total derived from the line items.

    Args:
        body: Estimate creation payload (lead_pin_id, line_items, tax_rate, …).
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        EstimateResponse for the newly created estimate (HTTP 201).

    Raises:
        404: Lead pin not found or does not belong to the current user.
    """
    # Verify the lead pin exists and belongs to the current user
    pin_stmt = select(LeadPin).where(
        LeadPin.id == body.lead_pin_id,
        LeadPin.roofer_account_id == current_user.id,
    )
    pin_result = await db.execute(pin_stmt)
    pin = pin_result.scalar_one_or_none()

    if pin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead pin not found",
        )

    subtotal, total = _compute_totals(body.line_items, body.tax_rate)

    # Serialize LineItem objects to dicts for JSONB storage
    line_items_data = [item.model_dump() for item in body.line_items]

    estimate = Estimate(
        lead_pin_id=body.lead_pin_id,
        roofer_account_id=current_user.id,
        line_items=line_items_data,
        subtotal=subtotal,
        tax_rate=body.tax_rate,
        total=total,
        status=body.status,
        notes=body.notes,
    )
    db.add(estimate)
    await db.commit()
    await db.refresh(estimate)

    return _estimate_to_response(estimate)


@router.get("", response_model=EstimateListResponse)
async def list_estimates(
    pin_id: UUID | None = Query(
        None,
        description="Filter estimates by lead pin UUID",
    ),
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EstimateListResponse:
    """List estimates for the current user, optionally filtered by pin.

    Args:
        pin_id: Optional UUID to restrict results to a single lead pin.
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        EstimateListResponse with estimates and total count.
    """
    stmt = (
        select(Estimate)
        .where(Estimate.roofer_account_id == current_user.id)
        .order_by(Estimate.created_at.desc())
    )

    if pin_id is not None:
        stmt = stmt.where(Estimate.lead_pin_id == pin_id)

    result = await db.execute(stmt)
    estimates = result.scalars().all()

    return EstimateListResponse(
        estimates=[_estimate_to_response(e) for e in estimates],
        total=len(estimates),
    )


@router.get("/{estimate_id}", response_model=EstimateResponse)
async def get_estimate(
    estimate_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EstimateResponse:
    """Get a single estimate by ID.

    Args:
        estimate_id: UUID of the estimate to retrieve.
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        EstimateResponse for the requested estimate.

    Raises:
        404: Estimate not found or does not belong to the current user.
    """
    estimate = await _get_owned_estimate(estimate_id, current_user, db)
    return _estimate_to_response(estimate)


@router.put("/{estimate_id}", response_model=EstimateResponse)
async def update_estimate(
    estimate_id: UUID,
    body: EstimateUpdate,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EstimateResponse:
    """Update an estimate's line items, tax rate, notes, or status.

    Recomputes subtotal and total whenever line_items or tax_rate change.
    Fields not included in the request body are left unchanged.

    Args:
        estimate_id: UUID of the estimate to update.
        body: Fields to update (all optional).
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        Updated EstimateResponse.

    Raises:
        404: Estimate not found or does not belong to the current user.
    """
    estimate = await _get_owned_estimate(estimate_id, current_user, db)

    needs_recompute = body.line_items is not None or body.tax_rate is not None

    if body.line_items is not None:
        estimate.line_items = [item.model_dump() for item in body.line_items]
    if body.tax_rate is not None:
        estimate.tax_rate = body.tax_rate
    if body.notes is not None:
        estimate.notes = body.notes
    if body.status is not None:
        estimate.status = body.status

    if needs_recompute:
        # Resolve current line items (may have just been replaced above)
        current_items = body.line_items if body.line_items is not None else estimate.line_items
        current_tax = float(estimate.tax_rate)

        if body.line_items is not None:
            # Use Pydantic objects for clean .total access
            subtotal, total = _compute_totals(body.line_items, current_tax)
        else:
            # line_items is a list of dicts from JSONB
            dict_items = current_items
            subtotal = sum(item.get("total", 0) for item in dict_items)
            total = subtotal * (1 + current_tax)
            subtotal = round(subtotal, 2)
            total = round(total, 2)

        estimate.subtotal = subtotal
        estimate.total = total

    await db.commit()
    await db.refresh(estimate)

    return _estimate_to_response(estimate)


@router.delete("/{estimate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_estimate(
    estimate_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an estimate.

    Args:
        estimate_id: UUID of the estimate to delete.
        current_user: Authenticated roofer account.
        db: Database session.

    Raises:
        404: Estimate not found or does not belong to the current user.
    """
    estimate = await _get_owned_estimate(estimate_id, current_user, db)
    await db.delete(estimate)
    await db.commit()
