"""Load USFS NLCD Tree Canopy Cover aggregated to census tracts.

Downloads tree canopy coverage data from a local GeoTIFF and computes
zonal statistics (mean, max, std) per census tract.

Prerequisites:
    Download the NLCD TCC GeoTIFF from:
    https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/

Usage:
    cd backend
    python -m scripts.load_tree_canopy --geotiff path/to/nlcd_tcc_conus_2021.tif --state 13
    python -m scripts.load_tree_canopy --geotiff data/nlcd_tcc.tif  # defaults to GA
"""

import argparse
import asyncio
import logging

from app.database import AsyncSessionLocal
from app.ingestion.tree_canopy_loader import load_tree_canopy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(
        description="Load USFS NLCD Tree Canopy Cover aggregated to census tracts"
    )
    parser.add_argument(
        "--geotiff",
        type=str,
        required=True,
        help="Path to NLCD Tree Canopy Cover GeoTIFF file",
    )
    parser.add_argument(
        "--state",
        type=str,
        default="13",
        help="State FIPS code to load (e.g., 13 for Georgia). Default: 13",
    )

    args = parser.parse_args()

    logger.info(f"Loading tree canopy from {args.geotiff} for state {args.state}")

    async with AsyncSessionLocal() as session:
        stats = await load_tree_canopy(
            geotiff_path=args.geotiff,
            state_fips=args.state,
            session=session,
        )

    logger.info(f"Tree canopy load complete:")
    logger.info(f"  Tracts loaded: {stats['tracts_loaded']}")
    logger.info(f"  Tracts with data: {stats['tracts_with_data']}")
    logger.info(f"  Tracts updated: {stats['tracts_updated']}")
    logger.info(f"  Errors: {stats['errors']}")
    if 'avg_canopy_mean' in stats:
        logger.info(f"  Avg canopy mean: {stats['avg_canopy_mean']}%")
        logger.info(f"  Max canopy mean: {stats['max_canopy_mean']}%")
        logger.info(f"  Avg risk score: {stats['avg_risk_score']}")


if __name__ == "__main__":
    asyncio.run(main())
