"""CLI script to load Redfin housing market data into census tracts.

Downloads ZIP-code-level housing market metrics from Redfin and allocates them
to census tracts using the HUD USPS ZIP-to-Census-Tract crosswalk.

Usage:
    python load_redfin.py --states 13
    python load_redfin.py --states 13,12,37  # Multiple states

Arguments:
    --states: Comma-separated list of 2-digit state FIPS codes (default: "13" for Georgia)

Example:
    python load_redfin.py --states 13
    # Loads Redfin market data for all Georgia census tracts

The script will:
1. Download HUD ZIP-Tract crosswalk with residential allocation ratios
2. Stream Redfin's ZIP-code market tracker (large TSV.gz file)
3. Allocate ZIP-level metrics to census tracts using residential weights
4. Update census_tracts table with:
   - redfin_median_sale_price
   - redfin_median_dom (days on market)
   - redfin_inventory (active listings)
   - redfin_price_drop_pct
   - redfin_data_month
"""

import argparse
import asyncio
import logging
import os
import sys

# SQLAlchemy Cython extensions workaround for Windows
os.environ.setdefault("DISABLE_SQLALCHEMY_CEXT_RUNTIME", "1")

# psycopg requires SelectorEventLoop on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.database import AsyncSessionLocal
from app.ingestion.redfin_loader import load_redfin_data

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main():
    """Main entry point for Redfin data loader."""
    parser = argparse.ArgumentParser(
        description="Load Redfin housing market data into census tracts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python load_redfin.py --states 13
  python load_redfin.py --states 13,12,37

State FIPS codes:
  13 = Georgia
  12 = Florida
  37 = North Carolina
  48 = Texas
  (See https://www.census.gov/library/reference/code-lists/ansi.html for full list)
        """,
    )

    parser.add_argument(
        "--states",
        type=str,
        default="13",
        help="Comma-separated state FIPS codes (default: 13 for Georgia)",
    )

    args = parser.parse_args()

    # Parse state FIPS codes
    state_fips_codes = [s.strip().zfill(2) for s in args.states.split(",")]

    logger.info("=" * 80)
    logger.info("Redfin Housing Market Data Loader")
    logger.info("=" * 80)
    logger.info(f"Target states: {', '.join(state_fips_codes)}")
    logger.info("")

    # Run the loader
    try:
        async with AsyncSessionLocal() as session:
            stats = await load_redfin_data(
                session=session,
                state_fips_codes=state_fips_codes,
            )

        logger.info("")
        logger.info("=" * 80)
        logger.info("Load Summary")
        logger.info("=" * 80)
        logger.info(f"  ZIPs with Redfin data: {stats['zips_matched']}")
        logger.info(f"  Tracts with allocated data: {stats['tracts_matched']}")
        logger.info(f"  Tracts updated in database: {stats['tracts_updated']}")
        logger.info(f"  Errors: {stats['errors']}")
        logger.info("=" * 80)

        if stats["errors"] > 0:
            logger.warning("Load completed with errors. Check logs above for details.")
            sys.exit(1)
        elif stats["tracts_updated"] == 0:
            logger.warning("No tracts were updated. Check if target states have census data loaded.")
            sys.exit(1)
        else:
            logger.info("Load completed successfully.")
            sys.exit(0)

    except KeyboardInterrupt:
        logger.warning("Load interrupted by user.")
        sys.exit(130)

    except Exception as e:
        logger.error(f"Load failed with error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
