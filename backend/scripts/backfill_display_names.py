"""Backfill display_name for existing lead zones using Mapbox reverse geocoding.

Groups zones by rounded coordinates to minimize API calls.
Uses lightweight SQL (id + centroid coords only) to avoid OOM on small machines.

Usage:
    python -m scripts.backfill_display_names
"""

import asyncio
import sys
import time
from collections import defaultdict

from sqlalchemy import select, update, text

from app.database import AsyncSessionLocal
from app.models.lead_zone import LeadZone
from app.services.geocoding import reverse_geocode
from app.config import settings

# Rate limiting: stay under Mapbox 600 req/min
RATE_LIMIT_DELAY = 0.11

# Round to 3 decimals (~110m precision) to group nearby zones
COORD_PRECISION = 3

BATCH_COMMIT_SIZE = 200


def log(msg: str) -> None:
    """Print with immediate flush for SSH output visibility."""
    print(msg, flush=True)


async def backfill_display_names():
    if not settings.MAPBOX_TOKEN:
        log("ERROR: MAPBOX_TOKEN not configured.")
        return

    # Lightweight query: only id + centroid coords, no geometry blobs
    async with AsyncSessionLocal() as session:
        stmt = text("""
            SELECT id, ST_Y(centroid) AS lat, ST_X(centroid) AS lon
            FROM lead_zones
            WHERE display_name IS NULL
        """)
        result = await session.execute(stmt)
        rows = result.all()

    if not rows:
        log("All zones already have display_name")
        return

    log(f"Found {len(rows)} zones without display_name")

    # Group by rounded coordinates
    coord_to_zone_ids: dict[tuple[float, float], list] = defaultdict(list)
    for zone_id, lat, lon in rows:
        if lat is None or lon is None:
            continue
        key = (round(lat, COORD_PRECISION), round(lon, COORD_PRECISION))
        coord_to_zone_ids[key].append(zone_id)

    unique_coords = list(coord_to_zone_ids.keys())
    log(f"Reduced to {len(unique_coords)} unique coordinate groups")

    # Geocode each unique coordinate and update DB incrementally
    updated = 0
    skipped = 0
    batch_count = 0

    async with AsyncSessionLocal() as session:
        for idx, (lat, lon) in enumerate(unique_coords):
            if idx > 0:
                time.sleep(RATE_LIMIT_DELAY)

            name = reverse_geocode(
                lon=lon, lat=lat, mapbox_token=settings.MAPBOX_TOKEN,
            )

            zone_ids = coord_to_zone_ids[(lat, lon)]

            if name is None:
                skipped += len(zone_ids)
            else:
                await session.execute(
                    update(LeadZone)
                    .where(LeadZone.id.in_(zone_ids))
                    .values(display_name=name)
                )
                updated += len(zone_ids)
                batch_count += 1

            # Commit every BATCH_COMMIT_SIZE geocoded locations
            if batch_count >= BATCH_COMMIT_SIZE:
                await session.commit()
                log(f"  Progress: {idx + 1}/{len(unique_coords)} coords, {updated} zones updated")
                batch_count = 0

            if (idx + 1) % 500 == 0:
                log(f"  Geocoded {idx + 1}/{len(unique_coords)} locations...")

        # Final commit
        await session.commit()

    log(f"Backfill complete: {updated} updated, {skipped} skipped (geocoding failed)")


if __name__ == "__main__":
    asyncio.run(backfill_display_names())
