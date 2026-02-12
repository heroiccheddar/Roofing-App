"""Load Microsoft Building Footprints aggregated to census tracts.

Usage:
    cd backend
    python -m scripts.load_building_footprints
    python -m scripts.load_building_footprints --state 48  # Texas only
"""

import argparse
import asyncio
import logging

from app.database import AsyncSessionLocal
from app.ingestion.building_footprint_loader import load_building_footprints, FOOTPRINT_URLS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main(state_fips_codes: list[str]):
    """Load building footprints for specified states.

    Args:
        state_fips_codes: List of 2-digit state FIPS codes to load
    """
    logger.info(f"Loading building footprints for states: {state_fips_codes}")

    async with AsyncSessionLocal() as session:
        stats = await load_building_footprints(state_fips_codes, session)

    logger.info(f"Building footprint load complete: {stats}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Load Microsoft Building Footprints aggregated to census tracts"
    )
    parser.add_argument(
        "--state",
        type=str,
        help="Single state FIPS to load (e.g., 48 for Texas). If not provided, loads all states.",
    )
    args = parser.parse_args()

    if args.state:
        states = [args.state]
    else:
        states = list(FOOTPRINT_URLS.keys())

    asyncio.run(main(states))
