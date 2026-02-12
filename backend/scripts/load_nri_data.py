"""Load FEMA National Risk Index data into census_tracts.

Usage:
    cd backend
    python -m scripts.load_nri_data
"""

import asyncio
import logging

from app.database import AsyncSessionLocal
from app.ingestion.nri_loader import load_nri_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Starting FEMA NRI data load...")
    async with AsyncSessionLocal() as session:
        stats = await load_nri_data(session)
    logger.info(f"NRI load complete: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
