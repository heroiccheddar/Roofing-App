"""Load FEMA Disaster Declarations into census_tracts.

Fetches federal disaster declarations from OpenFEMA API and maps them
to census tracts based on county FIPS codes.

Usage:
    cd backend
    python -m scripts.load_fema_disasters
    python -m scripts.load_fema_disasters --states GA TX
    python -m scripts.load_fema_disasters --states GA --years 5
"""

import argparse
import asyncio
import logging

from app.database import AsyncSessionLocal
from app.ingestion.fema_disaster_loader import load_fema_disasters

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(
        description="Load FEMA disaster declarations into census_tracts table"
    )
    parser.add_argument(
        "--states",
        nargs="+",
        default=["GA"],
        help="State abbreviations to load (e.g., GA TX OK). Default: GA",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=10,
        help="Number of years back to fetch disasters. Default: 10",
    )

    args = parser.parse_args()

    logger.info(f"Starting FEMA disaster load for states: {', '.join(args.states)}")
    logger.info(f"Looking back {args.years} years")

    async with AsyncSessionLocal() as session:
        stats = await load_fema_disasters(
            state_abbrevs=args.states,
            session=session,
            years_back=args.years,
        )

    logger.info(f"FEMA disaster load complete: {stats}")
    logger.info(f"  States processed: {stats['states_processed']}")
    logger.info(f"  Total declarations: {stats['total_declarations']}")
    logger.info(f"  Counties with disasters: {stats['total_counties']}")
    logger.info(f"  Tracts updated: {stats['tracts_updated']}")
    logger.info(f"  Errors: {stats['errors']}")


if __name__ == "__main__":
    asyncio.run(main())
