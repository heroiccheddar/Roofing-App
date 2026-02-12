"""Seed synthetic storm data for field testing.

Inserts clearly-tagged fake storm events in the Atlanta GA area,
then runs the scoring engine to generate lead zones.

ALL synthetic data is tagged for easy identification and removal:
  - storm_events.nws_event_id starts with 'SYNTHETIC-'
  - storm_events.raw_data contains {"synthetic": true}
  - storm_events.source = 'synthetic'

Usage:
    # Seed synthetic data and run scoring
    python -m scripts.seed_synthetic_data

    # Remove all synthetic data
    python -m scripts.seed_synthetic_data --cleanup
"""

import argparse
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update

from app.database import AsyncSessionLocal
from app.models.storm_event import StormEvent
from app.models.lead_zone import LeadZone
from app.scoring.engine import run_scoring_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Synthetic storm events across metro Atlanta and surrounding GA counties.
# Mix of hail and wind events at varying intensities to produce
# hot/warm/cool zones when scored.
SYNTHETIC_EVENTS = [
    # --- Severe hail cluster: NW Atlanta (Marietta/Kennesaw) ---
    {
        "event_type": "hail",
        "lat": 33.9526, "lon": -84.5499,  # Marietta
        "hail_diameter": 2.75,  # tennis ball
        "wind_speed": None,
        "hours_ago": 6,
    },
    {
        "event_type": "hail",
        "lat": 33.9481, "lon": -84.5802,  # west Marietta
        "hail_diameter": 2.00,  # hen egg
        "wind_speed": None,
        "hours_ago": 6.5,
    },
    {
        "event_type": "wind",
        "lat": 33.9420, "lon": -84.5250,  # east Marietta
        "hail_diameter": None,
        "wind_speed": 75,
        "hours_ago": 7,
    },
    # --- Moderate hail: Lawrenceville / Gwinnett ---
    {
        "event_type": "hail",
        "lat": 33.9562, "lon": -83.9880,  # Lawrenceville
        "hail_diameter": 1.75,  # golf ball
        "wind_speed": None,
        "hours_ago": 12,
    },
    {
        "event_type": "hail",
        "lat": 33.9250, "lon": -84.0100,  # near Snellville
        "hail_diameter": 1.50,
        "wind_speed": None,
        "hours_ago": 13,
    },
    # --- Wind damage: South Atlanta (College Park / Hapeville) ---
    {
        "event_type": "wind",
        "lat": 33.6534, "lon": -84.4494,  # College Park
        "hail_diameter": None,
        "wind_speed": 85,
        "hours_ago": 18,
    },
    {
        "event_type": "wind",
        "lat": 33.6610, "lon": -84.4102,  # Hapeville
        "hail_diameter": None,
        "wind_speed": 70,
        "hours_ago": 18.5,
    },
    # --- Mixed event: Decatur / Stone Mountain ---
    {
        "event_type": "hail",
        "lat": 33.7748, "lon": -84.2963,  # Decatur
        "hail_diameter": 1.25,  # quarter size
        "wind_speed": None,
        "hours_ago": 24,
    },
    {
        "event_type": "wind",
        "lat": 33.8081, "lon": -84.1702,  # Stone Mountain
        "hail_diameter": None,
        "wind_speed": 65,
        "hours_ago": 25,
    },
    # --- Older event, moderate decay: Roswell ---
    {
        "event_type": "hail",
        "lat": 34.0232, "lon": -84.3616,  # Roswell
        "hail_diameter": 2.00,
        "wind_speed": None,
        "hours_ago": 72,  # 3 days ago - ~50% decay
    },
    # --- Weak / fringe event: Peachtree City ---
    {
        "event_type": "hail",
        "lat": 33.3968, "lon": -84.5962,  # Peachtree City
        "hail_diameter": 0.88,  # nickel size
        "wind_speed": None,
        "hours_ago": 36,
    },
    # --- Isolated severe: Canton ---
    {
        "event_type": "hail",
        "lat": 34.2368, "lon": -84.4908,  # Canton
        "hail_diameter": 3.00,  # baseball
        "wind_speed": None,
        "hours_ago": 10,
    },
]


async def seed_synthetic() -> None:
    """Insert synthetic storm events and run scoring."""
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        # Check if synthetic data already exists
        existing = await session.execute(
            select(StormEvent).where(StormEvent.source == "synthetic").limit(1)
        )
        if existing.scalar_one_or_none():
            logger.warning(
                "Synthetic data already exists. Run with --cleanup first to remove it."
            )
            return

        # Insert storm events
        for i, evt in enumerate(SYNTHETIC_EVENTS):
            event_time = now - timedelta(hours=evt["hours_ago"])
            storm_event = StormEvent(
                id=uuid.uuid4(),
                source="synthetic",
                event_type=evt["event_type"],
                location=f"SRID=4326;POINT({evt['lon']} {evt['lat']})",
                warning_polygon=None,
                hail_diameter=evt.get("hail_diameter"),
                wind_speed=evt.get("wind_speed"),
                event_timestamp=event_time,
                nws_event_id=f"SYNTHETIC-{i:04d}-{uuid.uuid4().hex[:8]}",
                radar_confidence=0.85,
                corroborated=False,
                raw_data={"synthetic": True, "seed_index": i},
                scored=False,
            )
            session.add(storm_event)

        await session.commit()
        logger.info(f"Inserted {len(SYNTHETIC_EVENTS)} synthetic storm events")

    # Run scoring pipeline to generate lead zones
    async with AsyncSessionLocal() as session:
        stats = await run_scoring_pipeline(session)
        logger.info(f"Scoring complete: {stats}")

    logger.info("=== Synthetic data seeded successfully ===")
    logger.info(
        "To remove all synthetic data later:\n"
        "  python -m scripts.seed_synthetic_data --cleanup"
    )


async def cleanup_synthetic() -> None:
    """Remove all synthetic storm events and their generated lead zones."""
    async with AsyncSessionLocal() as session:
        # Find IDs of lead zones generated from synthetic events
        # These are zones whose primary_event_timestamp matches synthetic events
        # Simpler approach: delete zones that were generated from synthetic events
        # by finding zones linked to H3 hexes that only have synthetic events.
        #
        # Most reliable: delete zones created after synthetic events were inserted,
        # and delete the synthetic events themselves.

        # Step 1: Get synthetic event count
        result = await session.execute(
            select(StormEvent).where(StormEvent.source == "synthetic")
        )
        synthetic_events = list(result.scalars().all())

        if not synthetic_events:
            logger.info("No synthetic data found. Nothing to clean up.")
            return

        logger.info(f"Found {len(synthetic_events)} synthetic storm events")

        # Step 2: Delete lead zones that were created from synthetic events.
        # Since synthetic events have source='synthetic', and the scoring engine
        # creates zones, we identify zones by checking if they have no
        # non-synthetic events in their H3 hex.
        # Simplest safe approach: delete all active zones created after
        # the earliest synthetic event was inserted, then re-score real events.
        earliest_created = min(e.created_at for e in synthetic_events)

        zone_delete = delete(LeadZone).where(
            LeadZone.created_at >= earliest_created
        )
        zone_result = await session.execute(zone_delete)
        zones_deleted = zone_result.rowcount

        # Step 3: Delete synthetic storm events
        event_delete = delete(StormEvent).where(StormEvent.source == "synthetic")
        event_result = await session.execute(event_delete)
        events_deleted = event_result.rowcount

        # Step 4: Reset scored flag on any real events that might need re-scoring
        await session.execute(
            update(StormEvent).where(StormEvent.scored == True).values(scored=False)
        )

        await session.commit()

        logger.info(f"Deleted {events_deleted} synthetic storm events")
        logger.info(f"Deleted {zones_deleted} lead zones (generated from synthetic data)")
        logger.info("Real events (if any) have been marked for re-scoring.")
        logger.info("=== Cleanup complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed or remove synthetic storm data for field testing"
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove all synthetic data instead of seeding",
    )
    args = parser.parse_args()

    if args.cleanup:
        asyncio.run(cleanup_synthetic())
    else:
        asyncio.run(seed_synthetic())
