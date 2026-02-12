"""Load EPA EJSCREEN data into census_tracts.

Downloads EPA EJSCREEN environmental justice indicators and enriches
census tract records with air quality, lead paint risk, Superfund proximity,
wastewater discharge, and overall EJ index data.

Usage:
    cd backend
    python -m scripts.load_ejscreen
    python -m scripts.load_ejscreen --states "13,48"
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
from app.ingestion.ejscreen_loader import load_ejscreen_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(
        description="Load EPA EJSCREEN data into census_tracts"
    )
    parser.add_argument(
        "--states",
        type=str,
        default="13",
        help="Comma-separated list of state FIPS codes (default: 13 for Georgia)",
    )
    args = parser.parse_args()

    state_fips_codes = [s.strip() for s in args.states.split(",")]

    logger.info(f"Loading EJSCREEN data for states: {state_fips_codes}")

    async with AsyncSessionLocal() as session:
        stats = await load_ejscreen_data(
            session=session,
            state_fips_codes=state_fips_codes,
        )

    logger.info(f"EJSCREEN load complete: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
