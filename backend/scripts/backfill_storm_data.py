"""One-shot backfill script for storm data ingestion.

Usage:
    python -m scripts.backfill_storm_data

Runs all ingestion sources once (NWS poll, SPC scrape, dedup),
then prints a summary. Useful for initial data seeding or manual refresh.
"""

import asyncio
import logging

from app.database import AsyncSessionLocal
from app.ingestion.nws_poller import poll_nws_alerts
from app.ingestion.spc_scraper import scrape_spc_reports
from app.ingestion.dedup import deduplicate_storm_events

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

TARGET_STATES = ["TX", "OK", "KS", "CO", "NE"]


async def main() -> None:
    logger.info("Starting storm data backfill")

    # 1. Poll NWS alerts
    logger.info("--- NWS Active Alerts ---")
    async with AsyncSessionLocal() as session:
        nws_stats = await poll_nws_alerts(
            db_session=session,
            target_states=TARGET_STATES,
        )
    logger.info(f"NWS: {nws_stats}")

    # 2. Scrape SPC reports (today + yesterday)
    logger.info("--- SPC Storm Reports ---")
    async with AsyncSessionLocal() as session:
        spc_stats = await scrape_spc_reports(
            db_session=session,
            days_back=1,
        )
    logger.info(f"SPC: {spc_stats}")

    # 3. Run deduplication
    logger.info("--- Deduplication ---")
    async with AsyncSessionLocal() as session:
        dedup_stats = await deduplicate_storm_events(db_session=session)
    logger.info(f"Dedup: {dedup_stats}")

    # Summary
    logger.info("=== Backfill Complete ===")
    logger.info(f"NWS:   {nws_stats['new']} new events")
    logger.info(f"SPC:   {spc_stats['new']} new events")
    logger.info(f"Dedup: {dedup_stats['corroborated']} corroborated in {dedup_stats['groups']} groups")


if __name__ == "__main__":
    asyncio.run(main())
