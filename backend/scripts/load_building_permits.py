"""Load Census Building Permits Survey data into census_tracts.

Usage:
    cd backend
    python -m scripts.load_building_permits
    python -m scripts.load_building_permits --states "13,48" --year 2024
"""

import argparse
import asyncio
import logging
import os
import sys

os.environ.setdefault("DISABLE_SQLALCHEMY_CEXT_RUNTIME", "1")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.database import AsyncSessionLocal
from app.ingestion.building_permits_loader import load_building_permits

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(
        description="Load Census Building Permits Survey data into census_tracts"
    )
    parser.add_argument(
        "--states",
        type=str,
        default="13",
        help="Comma-separated list of state FIPS codes (default: 13 for Georgia)",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2024,
        help="BPS survey year (default: 2024)",
    )
    args = parser.parse_args()

    state_fips_codes = [s.strip() for s in args.states.split(",")]

    logger.info(f"Loading building permits data for states: {state_fips_codes}, year: {args.year}")

    async with AsyncSessionLocal() as session:
        stats = await load_building_permits(
            session=session,
            state_fips_codes=state_fips_codes,
            year=args.year,
        )

    logger.info(f"Building permits load complete: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
