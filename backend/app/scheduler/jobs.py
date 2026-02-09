"""Scheduled background jobs.

Defines all scheduled tasks: data ingestion polling, deduplication,
scoring engine runs, and zone lifecycle management.
Configured to run via APScheduler.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import update

from app.database import AsyncSessionLocal
from app.ingestion.nws_poller import poll_nws_alerts
from app.ingestion.spc_scraper import scrape_spc_reports
from app.ingestion.dedup import deduplicate_storm_events
from app.scoring.engine import run_scoring_pipeline
from app.models.lead_zone import LeadZone

logger = logging.getLogger(__name__)

# Target states for weather monitoring (Tornado Alley)
TARGET_STATES = ["TX", "OK", "KS", "CO", "NE"]


async def job_poll_nws() -> None:
    """Poll NWS for active severe weather alerts. Runs every 5 minutes."""
    logger.info("Starting scheduled NWS poll")
    try:
        async with AsyncSessionLocal() as session:
            stats = await poll_nws_alerts(
                db_session=session,
                target_states=TARGET_STATES,
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


async def job_run_scoring() -> None:
    """Run scoring pipeline on unscored events. Runs every 10 minutes."""
    logger.info("Starting scheduled scoring run")
    try:
        async with AsyncSessionLocal() as session:
            stats = await run_scoring_pipeline(session)
        logger.info(f"Scoring finished: {stats}")
    except Exception as e:
        logger.error(f"Scoring job failed: {e}", exc_info=True)


async def job_expire_zones() -> None:
    """Deactivate expired lead zones. Runs every hour."""
    logger.info("Starting zone expiry cleanup")
    try:
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            stmt = (
                update(LeadZone)
                .where(LeadZone.active == True, LeadZone.expires_at < now)
                .values(active=False)
            )
            result = await session.execute(stmt)
            await session.commit()
            expired_count = result.rowcount
        logger.info(f"Zone expiry: {expired_count} zones deactivated")
    except Exception as e:
        logger.error(f"Zone expiry job failed: {e}", exc_info=True)
