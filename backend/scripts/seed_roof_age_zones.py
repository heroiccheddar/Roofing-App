"""Generate roof-age lead zones from census tract data.

Creates lead zones based on housing age without requiring storm events.
Useful for identifying neighborhoods with aging roofs likely to need replacement.

Roof age zones:
- Have lead_type='roof_age'
- Expire after 180 days (vs 14 days for storm zones)
- No storm-related fields (damage_prob=0, event_count=0, etc.)
- Scored based on median_year_built, owner occupancy, home value, density

Usage:
    # Generate zones for homes built before 2001 (25+ years old)
    python -m scripts.seed_roof_age_zones

    # Generate zones for homes built before 1995 (30+ years old)
    python -m scripts.seed_roof_age_zones --max-year 1995

    # Remove all roof_age zones
    python -m scripts.seed_roof_age_zones --cleanup
"""

import argparse
import asyncio
import logging

from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.lead_zone import LeadZone
from app.scoring.roof_age_engine import run_roof_age_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def seed_roof_age_zones(max_year_built: int = 2001) -> None:
    """Generate roof-age lead zones from census tract data.

    Args:
        max_year_built: Maximum median year built to include (default: 2001)
    """
    logger.info(f"Starting roof age zone generation (max_year_built <= {max_year_built})...")

    async with AsyncSessionLocal() as session:
        stats = await run_roof_age_pipeline(session, max_year_built=max_year_built)

    logger.info("=== Roof Age Zone Generation Complete ===")
    logger.info(f"Census tracts processed: {stats['tracts_processed']}")
    logger.info(f"Lead zones created: {stats['zones_created']}")
    logger.info(f"Lead zones updated: {stats['zones_updated']}")
    logger.info(f"Errors encountered: {stats['errors']}")

    if stats['zones_created'] > 0 or stats['zones_updated'] > 0:
        logger.info(
            f"\nTotal roof_age zones: {stats['zones_created'] + stats['zones_updated']}"
        )
        logger.info(
            "These zones will expire in 180 days and have lead_type='roof_age'"
        )


async def cleanup_roof_age_zones() -> None:
    """Remove all roof_age lead zones."""
    async with AsyncSessionLocal() as session:
        # Delete all lead zones with lead_type='roof_age'
        result = await session.execute(
            delete(LeadZone).where(LeadZone.lead_type == "roof_age")
        )

        zones_deleted = result.rowcount
        await session.commit()

        logger.info(f"Deleted {zones_deleted} roof_age lead zones")
        logger.info("=== Cleanup complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate or remove roof-age lead zones from census data"
    )
    parser.add_argument(
        "--max-year",
        type=int,
        default=2001,
        help="Maximum median year built to include (default: 2001 = 25+ year old homes)",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove all roof_age zones instead of generating them",
    )
    args = parser.parse_args()

    if args.cleanup:
        asyncio.run(cleanup_roof_age_zones())
    else:
        asyncio.run(seed_roof_age_zones(max_year_built=args.max_year))
