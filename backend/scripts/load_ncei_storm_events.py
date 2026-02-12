"""Load NCEI Storm Events data into census_tracts.

Downloads and aggregates NWS-verified storm events with property damage
estimates to census tract level for verified storm damage risk assessment.

Usage:
    cd backend
    python -m scripts.load_ncei_storm_events
    python -m scripts.load_ncei_storm_events --states 13 48
    python -m scripts.load_ncei_storm_events --states 13 --years 5
"""

import argparse
import asyncio
import logging

from app.database import AsyncSessionLocal
from app.ingestion.ncei_storm_events_loader import load_ncei_storm_events

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(
        description="Load NCEI Storm Events data with property damage into census_tracts"
    )
    parser.add_argument(
        "--states",
        nargs="+",
        default=["13"],
        help="One or more state FIPS codes (default: 13 for Georgia)",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Number of years of historical data to fetch (default: 5)",
    )

    args = parser.parse_args()

    logger.info(
        f"Starting NCEI Storm Events load for states: {args.states} "
        f"({args.years} years back)"
    )

    async with AsyncSessionLocal() as session:
        stats = await load_ncei_storm_events(
            state_fips_codes=args.states,
            session=session,
            years_back=args.years,
        )

    logger.info(f"NCEI Storm Events load complete: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
