"""Backfill display_name for existing lead zones using Mapbox reverse geocoding.

Groups zones by rounded coordinates to minimize API calls.
8,473 zones -> ~500-1,500 unique locations -> ~3 min runtime.

Usage:
    python -m scripts.backfill_display_names
"""

import asyncio
import logging
import time
from collections import defaultdict

from sqlalchemy import select, update
from geoalchemy2.shape import to_shape

from app.database import AsyncSessionLocal
from app.models.lead_zone import LeadZone
from app.services.geocoding import reverse_geocode
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Rate limiting: stay under Mapbox 600 req/min
RATE_LIMIT_DELAY = 0.11

# Round to 3 decimals (~110m precision) to group nearby zones
COORD_PRECISION = 3


async def backfill_display_names():
    if not settings.MAPBOX_TOKEN:
        logger.error("MAPBOX_TOKEN not configured. Set it in .env.")
        return

    # Load zones without display_name
    async with AsyncSessionLocal() as session:
        stmt = select(LeadZone).where(LeadZone.display_name.is_(None))
        result = await session.execute(stmt)
        zones = list(result.scalars().all())

    if not zones:
        logger.info("All zones already have display_name")
        return

    logger.info(f"Found {len(zones)} zones without display_name")

    # Group by rounded coordinates
    coord_to_zone_ids: dict[tuple[float, float], list] = defaultdict(list)
    for zone in zones:
        try:
            centroid = to_shape(zone.centroid)
            key = (round(centroid.y, COORD_PRECISION), round(centroid.x, COORD_PRECISION))
            coord_to_zone_ids[key].append(zone.id)
        except Exception as e:
            logger.error(f"Failed to extract centroid for zone {zone.id}: {e}")

    unique_coords = list(coord_to_zone_ids.keys())
    logger.info(f"Reduced to {len(unique_coords)} unique coordinate groups")

    # Geocode each unique coordinate
    geocoded: dict[tuple[float, float], str | None] = {}
    for idx, (lat, lon) in enumerate(unique_coords):
        if idx > 0:
            time.sleep(RATE_LIMIT_DELAY)
        if idx > 0 and idx % 100 == 0:
            logger.info(f"  Geocoded {idx}/{len(unique_coords)} locations...")

        geocoded[(lat, lon)] = reverse_geocode(
            lon=lon, lat=lat, mapbox_token=settings.MAPBOX_TOKEN,
        )

    logger.info("Geocoding complete. Updating database...")

    # Bulk update
    updated = 0
    skipped = 0
    async with AsyncSessionLocal() as session:
        for (lat, lon), zone_ids in coord_to_zone_ids.items():
            name = geocoded.get((lat, lon))
            if name is None:
                skipped += len(zone_ids)
                continue
            await session.execute(
                update(LeadZone)
                .where(LeadZone.id.in_(zone_ids))
                .values(display_name=name)
            )
            updated += len(zone_ids)
        await session.commit()

    logger.info(f"Backfill complete: {updated} updated, {skipped} skipped (geocoding failed)")


if __name__ == "__main__":
    asyncio.run(backfill_display_names())
