"""Load FHFA House Price Index data into census_tracts.

Downloads census tract-level HPI data from FHFA and computes 5-year home price
appreciation percentages. Updates the census_tracts table with hpi_5yr_change values.

Usage:
    cd backend
    python -m scripts.load_fhfa_hpi
    python -m scripts.load_fhfa_hpi --state 13
    python -m scripts.load_fhfa_hpi --state 48
"""

import argparse
import asyncio
import logging

from app.database import AsyncSessionLocal
from app.ingestion.fhfa_hpi_loader import load_fhfa_hpi

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(
        description="Load FHFA House Price Index data into census_tracts table"
    )
    parser.add_argument(
        "--state",
        type=str,
        help="State FIPS code (2 digits) to filter updates. Default: all states",
    )

    args = parser.parse_args()

    logger.info("Starting FHFA HPI data load")
    if args.state:
        logger.info(f"  Filtering to state FIPS: {args.state}")

    async with AsyncSessionLocal() as session:
        stats = await load_fhfa_hpi(session, state_fips=args.state)

    logger.info("FHFA HPI load complete")
    logger.info(f"  Tracts with HPI data: {stats['tracts_with_data']}")
    logger.info(f"  Tracts with 5yr change computed: {stats['tracts_computed']}")
    logger.info(f"  Tracts updated in database: {stats['tracts_updated']}")
    logger.info(f"  Errors: {stats['errors']}")


if __name__ == "__main__":
    asyncio.run(main())
