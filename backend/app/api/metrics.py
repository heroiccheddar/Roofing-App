"""Leaderboard and metrics endpoints.

Provides aggregated performance data across a user's organization (or just
themselves for solo accounts). All queries are bounded by the authenticated
user's visibility scope — solo users only see their own stats, org members
see all teammates.
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.lead_pin import LeadPin
from app.models.roofer_account import RooferAccount
from app.schemas.metrics import LeaderboardMember, LeaderboardPeriod, LeaderboardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _period_start(period: LeaderboardPeriod) -> datetime | None:
    """Return the UTC start datetime for the requested period.

    Returns:
        this_week  — Monday 00:00 UTC of the current ISO week.
        this_month — First day of current month at 00:00 UTC.
        all_time   — None (no lower-bound filter applied).
    """
    now = datetime.now(tz=timezone.utc)

    if period == LeaderboardPeriod.this_week:
        # weekday() returns 0 for Monday, so subtract to reach this Monday
        monday = now - timedelta(days=now.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == LeaderboardPeriod.this_month:
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # all_time
    return None


async def _get_org_member_ids(
    current_user: RooferAccount, db: AsyncSession
) -> list[UUID] | None:
    """Return all org member IDs if the user belongs to an org, else None.

    This helper intentionally duplicates the equivalent in leads.py to
    maintain zero file overlap between parallel implementation agents.

    Args:
        current_user: The authenticated roofer account.
        db: Active database session.

    Returns:
        List of UUIDs for all accounts in the same organization, or None
        if the user is not part of any organization.
    """
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


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    period: LeaderboardPeriod = Query(LeaderboardPeriod.this_week),
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardResponse:
    """Return a performance leaderboard for the current period.

    For org members: ranks all teammates by contracts signed. For solo
    accounts: returns a single-entry leaderboard with their own stats.
    Members with zero pins in the period are still included (all zeros).

    Args:
        period: Time window — this_week, this_month, or all_time.
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        LeaderboardResponse with members sorted by contract_signed desc,
        then total_pins desc as a tiebreaker.
    """
    start = _period_start(period)

    # Determine which account IDs are in scope
    org_ids = await _get_org_member_ids(current_user, db)
    target_ids: list[UUID] = org_ids if org_ids is not None else [current_user.id]

    # ------------------------------------------------------------------
    # Aggregate pin counts per roofer in a single query
    # ------------------------------------------------------------------
    agg_stmt = select(
        LeadPin.roofer_account_id,
        func.count(LeadPin.id).label("total_pins"),
        func.count(case((LeadPin.disposition == "not_home", 1))).label("not_home"),
        func.count(case((LeadPin.disposition == "callback", 1))).label("callback"),
        func.count(case((LeadPin.disposition == "interested", 1))).label("interested"),
        func.count(case((LeadPin.disposition == "inspection_set", 1))).label("inspection_set"),
        func.count(case((LeadPin.disposition == "contract_signed", 1))).label("contract_signed"),
        func.count(case((LeadPin.disposition == "not_interested", 1))).label("not_interested"),
    ).where(
        LeadPin.roofer_account_id.in_(target_ids)
    ).group_by(
        LeadPin.roofer_account_id
    )

    if start is not None:
        agg_stmt = agg_stmt.where(LeadPin.created_at >= start)

    agg_result = await db.execute(agg_stmt)
    agg_rows = agg_result.all()

    # Index aggregated rows by account ID for O(1) lookup below
    stats_by_id: dict[UUID, dict] = {}
    for row in agg_rows:
        stats_by_id[row.roofer_account_id] = {
            "total_pins": row.total_pins,
            "not_home": row.not_home,
            "callback": row.callback,
            "interested": row.interested,
            "inspection_set": row.inspection_set,
            "contract_signed": row.contract_signed,
            "not_interested": row.not_interested,
        }

    # ------------------------------------------------------------------
    # Fetch profile data (company_name, email) for all target members
    # ------------------------------------------------------------------
    profile_stmt = select(
        RooferAccount.id,
        RooferAccount.company_name,
        RooferAccount.email,
    ).where(
        RooferAccount.id.in_(target_ids)
    )
    profile_result = await db.execute(profile_stmt)
    profiles = profile_result.all()

    # ------------------------------------------------------------------
    # Build LeaderboardMember list — include zero-pin members
    # ------------------------------------------------------------------
    members: list[LeaderboardMember] = []
    for row in profiles:
        stats = stats_by_id.get(row.id, {})
        total = stats.get("total_pins", 0)
        signed = stats.get("contract_signed", 0)
        conversion = signed / total if total > 0 else 0.0

        members.append(
            LeaderboardMember(
                roofer_account_id=row.id,
                company_name=row.company_name,
                email=row.email,
                total_pins=total,
                not_home=stats.get("not_home", 0),
                callback=stats.get("callback", 0),
                interested=stats.get("interested", 0),
                inspection_set=stats.get("inspection_set", 0),
                contract_signed=signed,
                not_interested=stats.get("not_interested", 0),
                conversion_rate=round(conversion, 4),
            )
        )

    # Sort: contract_signed desc, then total_pins desc as tiebreaker
    members.sort(key=lambda m: (m.contract_signed, m.total_pins), reverse=True)

    return LeaderboardResponse(
        current_user_id=current_user.id,
        period=period.value,
        period_start=start,
        members=members,
    )
