"""Load US Census data for specified states.

Fetches census tract boundaries and ACS demographic data from Census Bureau API.
Loads into the database for demographic enrichment of lead zones.

Usage:
    # Load default hail corridor states (TX, OK, KS, CO, NE)
    python scripts/load_census_data.py

    # Load specific states
    python scripts/load_census_data.py --states 48 40 20

    # Load specific states with state abbreviations
    python scripts/load_census_data.py --states TX OK KS
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Add backend to path so we can import app modules
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.config import settings
from app.database import AsyncSessionLocal
from app.ingestion.census_loader import load_census_data

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# State abbreviation to FIPS code mapping
STATE_FIPS_MAP = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "FL": "12", "GA": "13",
    "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
    "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24",
    "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29",
    "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34",
    "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45",
    "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50",
    "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56",
}

# Default POC state
DEFAULT_STATES = ["13"]  # GA


def parse_state_codes(state_args: list[str]) -> list[str]:
    """Parse state codes from command line arguments.

    Accepts either FIPS codes (e.g., '48') or state abbreviations (e.g., 'TX').

    Args:
        state_args: List of state FIPS codes or abbreviations

    Returns:
        List of 2-digit FIPS codes

    Raises:
        ValueError: If a state code is invalid
    """
    fips_codes = []

    for state in state_args:
        # Check if it's already a FIPS code (2-digit number)
        if state.isdigit() and len(state) <= 2:
            fips_codes.append(state.zfill(2))
        # Check if it's a state abbreviation
        elif state.upper() in STATE_FIPS_MAP:
            fips_codes.append(STATE_FIPS_MAP[state.upper()])
        else:
            raise ValueError(
                f"Invalid state code: {state}. "
                f"Use 2-digit FIPS code (e.g., '48') or state abbreviation (e.g., 'TX')"
            )

    return fips_codes


async def main(state_fips_codes: list[str]) -> int:
    """Load census data for specified states.

    Args:
        state_fips_codes: List of 2-digit state FIPS codes

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    logger.info("=" * 80)
    logger.info("Census Data Loader")
    logger.info("=" * 80)

    # Validate Census API key is configured
    if not settings.CENSUS_API_KEY:
        logger.error("CENSUS_API_KEY not configured in environment")
        return 1

    # Log states being loaded
    logger.info(f"Loading census data for {len(state_fips_codes)} states: {', '.join(state_fips_codes)}")

    start_time = time.time()

    try:
        # Create database session
        async with AsyncSessionLocal() as session:
            # Load census data
            result = await load_census_data(
                state_fips_codes=state_fips_codes,
                api_key=settings.CENSUS_API_KEY,
                db_session=session,
            )

            elapsed_time = time.time() - start_time

            # Print summary
            logger.info("=" * 80)
            logger.info("Load Summary")
            logger.info("=" * 80)
            logger.info(f"Tracts inserted: {result['loaded']}")
            logger.info(f"Tracts updated:  {result['updated']}")
            logger.info(f"States failed:   {result['errors']}")
            logger.info(f"Total time:      {elapsed_time:.1f} seconds")
            logger.info("=" * 80)

            if result["errors"] > 0:
                logger.warning(f"{result['errors']} state(s) failed to load")
                return 1

            logger.info("Census data load completed successfully")
            return 0

    except KeyboardInterrupt:
        logger.warning("Load interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Fatal error during census data load: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Load US Census tract data for specified states",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Load default hail corridor states (TX, OK, KS, CO, NE)
  python scripts/load_census_data.py

  # Load specific states by FIPS code
  python scripts/load_census_data.py --states 48 40 20

  # Load specific states by abbreviation
  python scripts/load_census_data.py --states TX OK KS CO NE

  # Mix FIPS codes and abbreviations
  python scripts/load_census_data.py --states 48 OK 20 CO
        """,
    )

    parser.add_argument(
        "--states",
        nargs="+",
        default=None,
        help="State FIPS codes or abbreviations (default: TX, OK, KS, CO, NE)",
    )

    args = parser.parse_args()

    # Parse state codes
    try:
        if args.states:
            state_codes = parse_state_codes(args.states)
        else:
            state_codes = DEFAULT_STATES
            logger.info("No states specified, using default hail corridor states")
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    # Run the async main function
    exit_code = asyncio.run(main(state_codes))
    sys.exit(exit_code)
