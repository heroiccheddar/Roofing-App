"""Storm event deduplication and corroboration.

Deduplicates storm events from multiple sources (NWS, SPC, SWDI) using
spatial proximity (ST_DWithin 15km) and temporal proximity (±30 minutes).
When events from different sources overlap, marks them as corroborated.
"""

import logging
from datetime import timedelta

from sqlalchemy import select, update, and_, not_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storm_event import StormEvent

logger = logging.getLogger(__name__)

# Dedup thresholds
SPATIAL_THRESHOLD_METERS = 15_000  # 15 km
TEMPORAL_THRESHOLD_MINUTES = 30  # ±30 minutes


async def deduplicate_storm_events(db_session: AsyncSession) -> dict:
    """Find and flag corroborated storm events across sources.

    Two events are considered corroborated when they:
    - Come from different sources (nws, spc, swdi)
    - Are within 15km of each other (ST_DWithin on geography)
    - Occurred within ±30 minutes of each other

    Does NOT delete duplicates — instead marks events as corroborated
    and records which sources confirm each other. This preserves all
    raw data while signaling higher confidence to the scoring engine.

    Args:
        db_session: Async database session

    Returns:
        dict: {"checked": N, "corroborated": N, "groups": N}
    """
    stats = {"checked": 0, "corroborated": 0, "groups": 0}

    # Find all unchecked events (not yet corroborated)
    unchecked_query = select(StormEvent).where(
        StormEvent.corroborated == False  # noqa: E712
    )
    result = await db_session.execute(unchecked_query)
    unchecked_events = result.scalars().all()
    stats["checked"] = len(unchecked_events)

    if not unchecked_events:
        logger.info("No unchecked events to deduplicate")
        return stats

    logger.info(f"Checking {len(unchecked_events)} events for corroboration")

    # For each unchecked event, find nearby events from different sources
    for event in unchecked_events:
        try:
            # Query for events from different sources that are spatially
            # and temporally close
            time_window_start = event.event_timestamp - timedelta(
                minutes=TEMPORAL_THRESHOLD_MINUTES
            )
            time_window_end = event.event_timestamp + timedelta(
                minutes=TEMPORAL_THRESHOLD_MINUTES
            )

            nearby_query = select(StormEvent).where(
                and_(
                    StormEvent.id != event.id,
                    StormEvent.source != event.source,
                    StormEvent.event_timestamp >= time_window_start,
                    StormEvent.event_timestamp <= time_window_end,
                    func.ST_DWithin(
                        func.cast(StormEvent.location, text("geography")),
                        func.cast(
                            func.ST_SetSRID(
                                func.ST_MakePoint(
                                    func.ST_X(event.location),
                                    func.ST_Y(event.location),
                                ),
                                4326,
                            ),
                            text("geography"),
                        ),
                        SPATIAL_THRESHOLD_METERS,
                    ),
                )
            )

            nearby_result = await db_session.execute(nearby_query)
            nearby_events = nearby_result.scalars().all()

            if nearby_events:
                # This event is corroborated by at least one other source
                corroboration_sources = [
                    {"source": e.source, "id": str(e.id)} for e in nearby_events
                ]

                event.corroborated = True
                event.corroboration_sources = corroboration_sources
                stats["corroborated"] += 1

                # Also mark the nearby events as corroborated
                for nearby in nearby_events:
                    if not nearby.corroborated:
                        nearby.corroborated = True
                        nearby.corroboration_sources = [
                            {"source": event.source, "id": str(event.id)}
                        ]
                        stats["corroborated"] += 1

                stats["groups"] += 1

        except Exception as e:
            logger.error(
                f"Error checking corroboration for event {event.id}: {e}",
                exc_info=True,
            )

    try:
        await db_session.commit()
        logger.info(
            f"Dedup complete: {stats['checked']} checked, "
            f"{stats['corroborated']} corroborated in {stats['groups']} groups"
        )
    except Exception as e:
        logger.error(f"Error committing dedup results: {e}", exc_info=True)
        await db_session.rollback()

    return stats
