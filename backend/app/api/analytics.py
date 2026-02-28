"""Analytics dashboard endpoint.

Provides aggregated funnel, summary, and daily activity data for the
authenticated user's visibility scope (org-wide or solo). All queries are
bounded by the requested time period and the user's org membership — the same
scoping rules as the leaderboard in metrics.py.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, cast, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.lead_pin import LeadPin
from app.models.roofer_account import RooferAccount
from app.schemas.analytics import (
    AnalyticsDashboardResponse,
    AnalyticsSummary,
    DailyActivityPoint,
    FunnelStage,
)
from app.schemas.metrics import LeaderboardPeriod

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ---------------------------------------------------------------------------
# Helpers — intentionally local copies to avoid coupling with metrics.py
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

    This helper intentionally duplicates the equivalent in metrics.py to
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


def _days_in_period(period: LeaderboardPeriod, start: datetime | None) -> float:
    """Return the number of elapsed calendar days for avg_pins_per_day.

    Args:
        period: The requested period enum value.
        start: The period start datetime (None for all_time).

    Returns:
        Elapsed days as a float, minimum 1 to avoid division-by-zero.
    """
    now = datetime.now(tz=timezone.utc)

    if period == LeaderboardPeriod.this_week:
        # Days elapsed since Monday (Monday itself counts as day 1)
        return float(now.weekday() + 1)

    if period == LeaderboardPeriod.this_month:
        # Day-of-month is the number of days elapsed including today
        return float(now.day)

    # all_time — use actual span if start is provided, else fall back to 30
    if start is not None:
        return float(max(1, (now - start).days + 1))

    return 30.0


def _fill_daily_gaps(
    rows: list,
    start: datetime | None,
    today: date,
) -> list[DailyActivityPoint]:
    """Merge query results with a full date range, filling missing days with zeros.

    Args:
        rows: SQLAlchemy result rows with .date, .pins_created, .contracts_signed.
        start: Period start datetime. If None, use the earliest date from rows.
        today: The current UTC date (used as the end of the range).

    Returns:
        Sorted list of DailyActivityPoint covering every day in the range.
    """
    # Index query results by date for O(1) lookup
    results_by_date: dict[date, dict] = {}
    for row in rows:
        results_by_date[row.date] = {
            "pins_created": row.pins_created,
            "contracts_signed": row.contracts_signed,
        }

    # Determine the range start date
    if start is not None:
        range_start = start.date()
    elif results_by_date:
        range_start = min(results_by_date.keys())
    else:
        # No data and no period start — nothing to fill
        return []

    points: list[DailyActivityPoint] = []
    cursor = range_start
    while cursor <= today:
        data = results_by_date.get(cursor, {"pins_created": 0, "contracts_signed": 0})
        points.append(
            DailyActivityPoint(
                date=cursor.isoformat(),
                pins_created=data["pins_created"],
                contracts_signed=data["contracts_signed"],
            )
        )
        cursor += timedelta(days=1)

    return points


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=AnalyticsDashboardResponse)
async def get_analytics_dashboard(
    period: LeaderboardPeriod = Query(LeaderboardPeriod.this_week),
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsDashboardResponse:
    """Return analytics dashboard data for the current period.

    Aggregates funnel disposition counts, a daily activity time series,
    and summary metrics for the authenticated user's visibility scope.
    For org members: covers all teammates. For solo accounts: covers only
    the authenticated user.

    Args:
        period: Time window — this_week, this_month, or all_time.
        current_user: Authenticated roofer account.
        db: Database session.

    Returns:
        AnalyticsDashboardResponse with summary, daily_activity, and funnel.
    """
    now = datetime.now(tz=timezone.utc)
    start = _period_start(period)

    # Determine which account IDs are in scope
    org_ids = await _get_org_member_ids(current_user, db)
    target_ids: list[UUID] = org_ids if org_ids is not None else [current_user.id]

    logger.debug(
        "analytics/dashboard: period=%s, user=%s, target_ids_count=%d",
        period.value,
        current_user.id,
        len(target_ids),
    )

    # ------------------------------------------------------------------
    # Summary + Funnel query — single aggregation over the period
    # ------------------------------------------------------------------
    agg_stmt = select(
        func.count(LeadPin.id).label("total_pins"),
        func.count(case((LeadPin.disposition == "callback", 1))).label("callback"),
        func.count(case((LeadPin.disposition == "interested", 1))).label("interested"),
        func.count(case((LeadPin.disposition == "inspection_set", 1))).label("inspection_set"),
        func.count(case((LeadPin.disposition == "contract_signed", 1))).label("contract_signed"),
    ).where(LeadPin.roofer_account_id.in_(target_ids))

    if start is not None:
        agg_stmt = agg_stmt.where(LeadPin.created_at >= start)

    agg_result = await db.execute(agg_stmt)
    agg_row = agg_result.one()

    total_pins: int = agg_row.total_pins or 0
    callback: int = agg_row.callback or 0
    interested: int = agg_row.interested or 0
    inspection_set: int = agg_row.inspection_set or 0
    contract_signed: int = agg_row.contract_signed or 0

    # Derived summary fields
    conversion_rate = round(contract_signed / total_pins, 4) if total_pins > 0 else 0.0
    days = _days_in_period(period, start)
    avg_pins_per_day = round(total_pins / days, 2)

    summary = AnalyticsSummary(
        total_pins=total_pins,
        contracts_signed=contract_signed,
        conversion_rate=conversion_rate,
        callbacks_pending=callback,
        inspections_set=inspection_set,
        avg_pins_per_day=avg_pins_per_day,
    )

    # ------------------------------------------------------------------
    # Daily activity query — grouped by calendar date
    # ------------------------------------------------------------------
    daily_stmt = select(
        cast(LeadPin.created_at, Date).label("date"),
        func.count(LeadPin.id).label("pins_created"),
        func.count(case((LeadPin.disposition == "contract_signed", 1))).label("contracts_signed"),
    ).where(
        LeadPin.roofer_account_id.in_(target_ids)
    ).group_by(
        cast(LeadPin.created_at, Date)
    ).order_by("date")

    if start is not None:
        daily_stmt = daily_stmt.where(LeadPin.created_at >= start)

    daily_result = await db.execute(daily_stmt)
    daily_rows = daily_result.all()

    daily_activity = _fill_daily_gaps(daily_rows, start, now.date())

    # ------------------------------------------------------------------
    # Funnel — ordered from broadest (all pins) to narrowest (contract)
    # ------------------------------------------------------------------
    funnel: list[FunnelStage] = [
        FunnelStage(stage="Pins Dropped", count=total_pins),
        FunnelStage(stage="Callback", count=callback),
        FunnelStage(stage="Interested", count=interested),
        FunnelStage(stage="Inspection Set", count=inspection_set),
        FunnelStage(stage="Contract Signed", count=contract_signed),
    ]

    return AnalyticsDashboardResponse(
        period=period.value,
        summary=summary,
        daily_activity=daily_activity,
        funnel=funnel,
    )
