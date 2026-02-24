"""Backfill last_canvassed_at for lead zones from existing sessions and feedback.

For each zone that has canvass sessions or feedback but no last_canvassed_at,
sets it to the most recent of canvass_session.created_at or zone_feedback.created_at.

Usage:
    python -m scripts.backfill_staleness
"""

import asyncio
import logging

from sqlalchemy import select, update, func

from app.database import AsyncSessionLocal
from app.models.lead_zone import LeadZone
from app.models.canvass_session import CanvassSession
from app.models.zone_feedback import ZoneFeedback

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 500


async def backfill_staleness():
    async with AsyncSessionLocal() as session:
        # Subquery: max created_at from canvass_sessions per zone
        canvass_sub = (
            select(
                CanvassSession.lead_zone_id,
                func.max(CanvassSession.created_at).label("max_canvass_at"),
            )
            .group_by(CanvassSession.lead_zone_id)
            .subquery()
        )

        # Subquery: max created_at from zone_feedback per zone
        feedback_sub = (
            select(
                ZoneFeedback.lead_zone_id,
                func.max(ZoneFeedback.created_at).label("max_feedback_at"),
            )
            .group_by(ZoneFeedback.lead_zone_id)
            .subquery()
        )

        # Get zones with activity but no last_canvassed_at
        stmt = (
            select(
                LeadZone.id,
                canvass_sub.c.max_canvass_at,
                feedback_sub.c.max_feedback_at,
            )
            .outerjoin(canvass_sub, LeadZone.id == canvass_sub.c.lead_zone_id)
            .outerjoin(feedback_sub, LeadZone.id == feedback_sub.c.lead_zone_id)
            .where(LeadZone.last_canvassed_at.is_(None))
            .where(
                (canvass_sub.c.max_canvass_at.isnot(None))
                | (feedback_sub.c.max_feedback_at.isnot(None))
            )
        )

        result = await session.execute(stmt)
        rows = result.all()
        logger.info(f"Found {len(rows)} zones needing last_canvassed_at backfill")

        updated = 0
        for row in rows:
            zone_id, canvass_at, feedback_at = row
            candidates = [t for t in [canvass_at, feedback_at] if t is not None]
            if not candidates:
                continue
            most_recent = max(candidates)

            await session.execute(
                update(LeadZone)
                .where(LeadZone.id == zone_id)
                .values(last_canvassed_at=most_recent)
            )
            updated += 1

            if updated % BATCH_SIZE == 0:
                await session.commit()
                logger.info(f"  Updated {updated}/{len(rows)} zones...")

        await session.commit()
        logger.info(f"Backfill complete: {updated} zones updated")


if __name__ == "__main__":
    asyncio.run(backfill_staleness())
