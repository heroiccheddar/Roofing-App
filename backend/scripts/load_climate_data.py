"""Load NASA POWER Climate Data into census_tracts.

Fetches satellite-derived climate parameters from NASA POWER API and computes
roof weathering metrics for census tracts.

Usage:
    cd backend
    python -m scripts.load_climate_data
    python -m scripts.load_climate_data --states 13 48
    python -m scripts.load_climate_data --states 13
"""

import argparse
import asyncio
import logging

from app.database import AsyncSessionLocal
from app.ingestion.nasa_power_loader import load_climate_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(
        description="Load NASA POWER climate data into census_tracts table"
    )
    parser.add_argument(
        "--states",
        nargs="+",
        default=["13"],
        help="State FIPS codes to load (e.g., 13 48 40). Default: 13 (Georgia)",
    )

    args = parser.parse_args()

    logger.info(f"Starting NASA POWER climate load for states: {', '.join(args.states)}")
    logger.info("Grid optimization enabled (0.5-degree cells)")

    async with AsyncSessionLocal() as session:
        stats = await load_climate_data(
            state_fips_codes=args.states,
            session=session,
        )

    logger.info(f"NASA POWER climate load complete: {stats}")
    logger.info(f"  States processed: {stats['states_processed']}")
    logger.info(f"  Total tracts: {stats['total_tracts']}")
    logger.info(f"  API calls made: {stats['api_calls']}")
    logger.info(f"  Tracts updated: {stats['tracts_updated']}")
    logger.info(f"  Errors: {stats['errors']}")

    # Calculate efficiency metrics
    if stats['total_tracts'] > 0 and stats['api_calls'] > 0:
        reduction_pct = (1 - stats['api_calls'] / stats['total_tracts']) * 100
        logger.info(
            f"  Grid optimization: {reduction_pct:.1f}% reduction in API calls "
            f"({stats['total_tracts']} tracts -> {stats['api_calls']} calls)"
        )


if __name__ == "__main__":
    asyncio.run(main())
