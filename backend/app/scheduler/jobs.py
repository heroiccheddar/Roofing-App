"""Scheduled background jobs.

Defines all scheduled tasks: data ingestion polling, deduplication,
scoring engine runs, and zone lifecycle management.
Configured to run via APScheduler.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from app.config import settings
from app.database import AsyncSessionLocal
from app.ingestion.nws_poller import poll_nws_alerts
from app.ingestion.spc_scraper import scrape_spc_reports
from app.ingestion.dedup import deduplicate_storm_events
from app.scoring.engine import run_storm_rescore_pipeline
from app.scoring.base_engine import run_base_scoring_pipeline
from app.models.lead_zone import LeadZone

logger = logging.getLogger(__name__)

# Target states now configurable via settings


async def job_poll_nws() -> None:
    """Poll NWS for active severe weather alerts. Runs every 5 minutes."""
    logger.info("Starting scheduled NWS poll")
    try:
        async with AsyncSessionLocal() as session:
            stats = await poll_nws_alerts(
                db_session=session,
                target_states=settings.target_states_list,
            )
        logger.info(f"NWS poll finished: {stats}")
    except Exception as e:
        logger.error(f"NWS poll job failed: {e}", exc_info=True)


async def job_scrape_spc() -> None:
    """Scrape SPC storm reports. Runs every 6 hours."""
    logger.info("Starting scheduled SPC scrape")
    try:
        async with AsyncSessionLocal() as session:
            stats = await scrape_spc_reports(
                db_session=session,
                days_back=1,
            )
        logger.info(f"SPC scrape finished: {stats}")
    except Exception as e:
        logger.error(f"SPC scrape job failed: {e}", exc_info=True)


async def job_deduplicate() -> None:
    """Run deduplication/corroboration across sources. Runs every 30 minutes."""
    logger.info("Starting scheduled deduplication")
    try:
        async with AsyncSessionLocal() as session:
            stats = await deduplicate_storm_events(db_session=session)
        logger.info(f"Deduplication finished: {stats}")
    except Exception as e:
        logger.error(f"Dedup job failed: {e}", exc_info=True)


async def job_run_base_scoring() -> None:
    """Run base scoring pipeline on all census tracts. Runs daily at 2 AM UTC."""
    logger.info("Starting daily base scoring run")
    try:
        async with AsyncSessionLocal() as session:
            stats = await run_base_scoring_pipeline(session)
        logger.info(f"Base scoring finished: {stats}")
    except Exception as e:
        logger.error(f"Base scoring job failed: {e}", exc_info=True)


async def job_run_storm_scoring() -> None:
    """Run storm rescore pipeline on unscored events. Runs every 10 minutes."""
    logger.info("Starting scheduled storm rescore")
    try:
        async with AsyncSessionLocal() as session:
            stats = await run_storm_rescore_pipeline(session)
        logger.info(f"Storm rescore finished: {stats}")
    except Exception as e:
        logger.error(f"Storm rescore job failed: {e}", exc_info=True)


async def job_expire_zones() -> None:
    """Deactivate expired lead zones and decay stale storm boosts. Runs every hour."""
    logger.info("Starting zone expiry cleanup")
    try:
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            # Deactivate zones whose expiry timestamp has passed
            stmt = (
                update(LeadZone)
                .where(LeadZone.active == True, LeadZone.expires_at < now)
                .values(active=False)
            )
            result = await session.execute(stmt)
            await session.commit()
            expired_count = result.rowcount
        logger.info(f"Zone expiry: {expired_count} zones deactivated")

        # Transition storm-boosted zones back to standard when storm has
        # decayed (14+ days since primary event). Only update zones that
        # already have a base_score; zones without one will be handled by
        # the next base scoring run.
        storm_decay_cutoff = now - timedelta(days=14)
        async with AsyncSessionLocal() as session:
            storm_transition_stmt = (
                update(LeadZone)
                .where(
                    LeadZone.has_active_storm == True,
                    LeadZone.primary_event_timestamp < storm_decay_cutoff,
                    LeadZone.base_score.isnot(None),
                )
                .values(
                    has_active_storm=False,
                    storm_boost=0.0,
                    damage_prob=0.0,  # backward compat
                    lead_type='standard',
                    # composite_score = base_score (no storm component)
                    composite_score=LeadZone.base_score,
                )
            )
            transition_result = await session.execute(storm_transition_stmt)
            await session.commit()
            transitioned = transition_result.rowcount
        if transitioned:
            logger.info(f"Storm decay: {transitioned} zones transitioned to standard")
    except Exception as e:
        logger.error(f"Zone expiry job failed: {e}", exc_info=True)
