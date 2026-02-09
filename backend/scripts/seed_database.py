"""Full database seed script: census + storms + dedup + scoring.

Usage:
    cd backend
    python -m scripts.seed_database                    # everything
    python -m scripts.seed_database --census-only      # just census tracts
    python -m scripts.seed_database --storms-only      # just storms + dedup + scoring
    python -m scripts.seed_database --score-only       # just re-run scoring on existing events
    python -m scripts.seed_database --days-back 7      # fetch 7 days of SPC history
"""

import argparse
import asyncio
import logging
import sys

from app.config import settings
from app.database import AsyncSessionLocal
from app.ingestion.census_loader import load_census_data
from app.ingestion.nws_poller import poll_nws_alerts
from app.ingestion.spc_scraper import scrape_spc_reports
from app.ingestion.dedup import deduplicate_storm_events
from app.scoring.engine import run_scoring_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Tornado Alley states
TARGET_STATES = ["TX", "OK", "KS", "CO", "NE"]
STATE_FIPS = ["48", "40", "20", "08", "31"]  # TX, OK, KS, CO, NE


async def seed_census() -> dict:
    """Load census tract boundaries + demographics for target states."""
    api_key = settings.CENSUS_API_KEY
    if not api_key:
        logger.error("CENSUS_API_KEY not set in .env — cannot load census data")
        return {"loaded": 0, "updated": 0, "errors": 1}

    logger.info(f"Loading census data for states: {STATE_FIPS}")
    async with AsyncSessionLocal() as session:
        result = await load_census_data(
            state_fips_codes=STATE_FIPS,
            api_key=api_key,
            db_session=session,
        )
    return result


async def seed_storms(days_back: int = 3) -> dict:
    """Ingest NWS active alerts + SPC historical reports."""
    stats = {"nws": {}, "spc": {}}

    # 1. NWS active alerts
    logger.info("--- NWS Active Alerts ---")
    async with AsyncSessionLocal() as session:
        stats["nws"] = await poll_nws_alerts(
            db_session=session,
            target_states=TARGET_STATES,
        )
    logger.info(f"NWS: {stats['nws']}")

    # 2. SPC historical reports
    logger.info(f"--- SPC Storm Reports ({days_back} days back) ---")
    async with AsyncSessionLocal() as session:
        stats["spc"] = await scrape_spc_reports(
            db_session=session,
            days_back=days_back,
        )
    logger.info(f"SPC: {stats['spc']}")

    return stats


async def run_dedup() -> dict:
    """Run cross-source deduplication."""
    logger.info("--- Deduplication ---")
    async with AsyncSessionLocal() as session:
        stats = await deduplicate_storm_events(db_session=session)
    logger.info(f"Dedup: {stats}")
    return stats


async def run_scoring() -> dict:
    """Run the scoring pipeline to create lead zones."""
    logger.info("--- Scoring Pipeline ---")
    async with AsyncSessionLocal() as session:
        stats = await run_scoring_pipeline(session)
    logger.info(f"Scoring: {stats}")
    return stats


async def main(args: argparse.Namespace) -> None:
    census_result = None
    storm_stats = None
    dedup_stats = None
    score_stats = None

    if args.score_only:
        score_stats = await run_scoring()
    elif args.census_only:
        census_result = await seed_census()
    elif args.storms_only:
        storm_stats = await seed_storms(args.days_back)
        dedup_stats = await run_dedup()
        score_stats = await run_scoring()
    else:
        # Full pipeline
        census_result = await seed_census()
        storm_stats = await seed_storms(args.days_back)
        dedup_stats = await run_dedup()
        score_stats = await run_scoring()

    # Summary
    logger.info("=" * 50)
    logger.info("SEED COMPLETE")
    logger.info("=" * 50)

    if census_result:
        logger.info(
            f"Census:  {census_result['loaded']} loaded, "
            f"{census_result['updated']} updated, "
            f"{census_result['errors']} errors"
        )

    if storm_stats:
        nws = storm_stats.get("nws", {})
        spc = storm_stats.get("spc", {})
        logger.info(f"NWS:     {nws.get('new', 0)} new events")
        logger.info(f"SPC:     {spc.get('new', 0)} new events")

    if dedup_stats:
        logger.info(
            f"Dedup:   {dedup_stats.get('corroborated', 0)} corroborated "
            f"in {dedup_stats.get('groups', 0)} groups"
        )

    if score_stats:
        logger.info(f"Scoring: {score_stats}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the StormLeads database")
    parser.add_argument("--census-only", action="store_true", help="Only load census data")
    parser.add_argument("--storms-only", action="store_true", help="Only ingest storms + score")
    parser.add_argument("--score-only", action="store_true", help="Only re-run scoring")
    parser.add_argument("--days-back", type=int, default=3, help="Days of SPC history (default: 3)")
    args = parser.parse_args()
    asyncio.run(main(args))
