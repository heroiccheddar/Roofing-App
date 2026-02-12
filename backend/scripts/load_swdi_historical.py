"""Load NOAA SWDI historical hail data into census_tracts.

Aggregates 3 years of radar-derived hail (MESH) data from SWDI API
to census tract level for hail exposure scoring.

Usage:
    cd backend
    python -m scripts.load_swdi_historical
    python -m scripts.load_swdi_historical --states "13,48"
    python -m scripts.load_swdi_historical --states "13" --years-back 5
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
from app.ingestion.swdi_historical_loader import load_swdi_historical

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(
        description="Load NOAA SWDI historical hail data into census_tracts"
    )
    parser.add_argument(
        "--states",
        type=str,
        default="13",
        help="Comma-separated list of state FIPS codes (default: 13 for Georgia)",
    )
    parser.add_argument(
        "--years-back",
        type=int,
        default=3,
        help="Number of years of historical data to fetch (default: 3)",
    )

    args = parser.parse_args()

    # Parse state FIPS codes
    state_fips_codes = [s.strip() for s in args.states.split(",")]

    logger.info(
        f"Starting SWDI historical hail load for states: {state_fips_codes} "
        f"({args.years_back} years back)"
    )

    async with AsyncSessionLocal() as session:
        stats = await load_swdi_historical(
            state_fips_codes=state_fips_codes,
            session=session,
            years_back=args.years_back,
        )

    logger.info(f"SWDI historical load complete: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
