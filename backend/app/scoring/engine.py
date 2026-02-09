"""Main scoring engine for lead zones.

Orchestrates the scoring pipeline: spatial aggregation, weight application,
demographic enrichment, and temporal decay. Produces scored LeadZone records.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2 import WKTElement

from app.models.storm_event import StormEvent
from app.models.lead_zone import LeadZone
from app.scoring.spatial import (
    cluster_events_to_h3,
    build_zone_boundary,
    get_intersecting_tracts,
    compute_weighted_demographics,
)
from app.scoring.decay import calculate_decay, MAX_AGE_DAYS
from app.scoring.weights import (
    CURRENT_MODEL_VERSION,
    get_score_band,
    get_predicted_conversion_rate,
)

logger = logging.getLogger(__name__)


async def run_scoring_pipeline(session: AsyncSession) -> dict:
    """Execute the 7-step scoring pipeline to produce LeadZone records.

    Steps:
    1. Query unscored events
    2. Cluster events to H3 hexes
    3. For each hex, spatial join to census tracts
    4. Compute 3 sub-scores (damage_prob, lead_quality, density_bonus)
    5. Compute composite score and apply decay
    6. Create/update LeadZone records
    7. Mark events as scored

    Args:
        session: AsyncSession for database operations

    Returns:
        Stats dict with keys: events_processed, zones_created, zones_updated, errors
    """
    stats = {
        "events_processed": 0,
        "zones_created": 0,
        "zones_updated": 0,
        "errors": 0,
    }

    logger.info("Starting scoring pipeline")

    # Step 1: Query unscored events
    stmt = select(StormEvent).where(StormEvent.scored == False)
    result = await session.execute(stmt)
    unscored_events = list(result.scalars().all())

    if not unscored_events:
        logger.info("No unscored events found")
        return stats

    logger.info(f"Found {len(unscored_events)} unscored events")

    # Step 2: Cluster events to H3 hexes
    clustered_events = cluster_events_to_h3(unscored_events, resolution=7)
    logger.info(f"Clustered events into {len(clustered_events)} H3 hexes")

    # Step 3-6: Process each hex
    processed_event_ids = []

    for h3_index, events in clustered_events.items():
        try:
            # Score this zone
            zone = await score_single_zone(session, h3_index, events)

            if zone is not None:
                # Track which events were processed
                processed_event_ids.extend([e.id for e in events])

                # Update stats
                if hasattr(zone, '_is_new'):
                    if zone._is_new:
                        stats["zones_created"] += 1
                    else:
                        stats["zones_updated"] += 1

        except Exception as e:
            logger.error(f"Error scoring zone {h3_index}: {e}", exc_info=True)
            stats["errors"] += 1

    # Step 7: Mark events as scored
    if processed_event_ids:
        update_stmt = (
            update(StormEvent)
            .where(StormEvent.id.in_(processed_event_ids))
            .values(scored=True)
        )
        await session.execute(update_stmt)
        await session.commit()

        stats["events_processed"] = len(processed_event_ids)
        logger.info(f"Marked {len(processed_event_ids)} events as scored")

    logger.info(
        f"Pipeline complete: {stats['events_processed']} events processed, "
        f"{stats['zones_created']} zones created, {stats['zones_updated']} zones updated, "
        f"{stats['errors']} errors"
    )

    return stats


async def score_single_zone(
    session: AsyncSession,
    h3_index: str,
    events: list[StormEvent]
) -> Optional[LeadZone]:
    """Score a single H3 hex and create/update a LeadZone record.

    Encapsulates steps 3-6 of the pipeline for a single hex.

    Args:
        session: AsyncSession for database operations
        h3_index: H3 hex index to score
        events: List of StormEvent instances in this hex

    Returns:
        LeadZone instance if scoring succeeded, None if failed
    """
    if not events:
        return None

    # Step 3: Build zone boundary and find intersecting census tracts
    boundary_wkt, centroid_wkt = build_zone_boundary(h3_index)
    intersecting_tracts = await get_intersecting_tracts(session, boundary_wkt)

    if not intersecting_tracts:
        logger.warning(f"No census tracts found for zone {h3_index}, skipping")
        return None

    demographics = compute_weighted_demographics(intersecting_tracts)

    # Step 4: Compute sub-scores

    # 4a. damage_prob (0-100): Based on event severity
    max_hail_diameter = max((e.hail_diameter or 0.0 for e in events), default=0.0)
    max_wind_speed = max((e.wind_speed or 0.0 for e in events), default=0.0)
    event_count = len(events)

    # Hail score: max_hail_diameter * 25 (4" hail = 100)
    hail_score = min(max_hail_diameter * 25, 100)

    # Wind score: (max_wind_speed - 50) * 2 (100mph = 100)
    wind_score = min(max((max_wind_speed - 50) * 2, 0), 100)

    # Base damage score: max of hail and wind
    damage_prob = max(hail_score, wind_score)

    # Boost by 10 if corroborated (multiple sources)
    has_corroboration = any(e.corroborated for e in events)
    if has_corroboration:
        damage_prob += 10

    # Boost by event count: min(event_count * 5, 20)
    count_bonus = min(event_count * 5, 20)
    damage_prob += count_bonus

    # Cap at 100
    damage_prob = min(damage_prob, 100)

    # 4b. lead_quality (0-100): Based on demographics
    avg_owner_occupied_pct = demographics["avg_owner_occupied_pct"]
    avg_median_home_value = demographics["avg_median_home_value"]
    avg_median_year_built = demographics["avg_median_year_built"]

    # Owner occupancy contribution: avg_owner_occupied_pct * 0.4 (max 40 pts)
    owner_contrib = avg_owner_occupied_pct * 0.4

    # Home value contribution: min(avg_median_home_value / 5000, 30) (max 30 pts)
    value_contrib = min(avg_median_home_value / 5000, 30)

    # Roof age contribution: older roofs are better leads
    roof_age_contrib = 0.0
    if avg_median_year_built > 0 and avg_median_year_built < 2000:
        roof_age_contrib = min((2000 - avg_median_year_built) * 0.5, 30)

    lead_quality = owner_contrib + value_contrib + roof_age_contrib
    lead_quality = min(lead_quality, 100)

    # 4c. density_bonus (0-100): Based on housing density
    avg_housing_density = demographics["avg_housing_density"]
    density_bonus = min(avg_housing_density / 10, 100)

    # Step 5: Compute composite score + apply decay

    # Raw composite: (damage*0.50 + quality*0.30 + density*0.20)
    raw_composite = (
        damage_prob * CURRENT_MODEL_VERSION.composite_weights.damage_prob +
        lead_quality * CURRENT_MODEL_VERSION.composite_weights.lead_quality +
        density_bonus * CURRENT_MODEL_VERSION.composite_weights.density_bonus
    )

    # Get most recent event timestamp
    most_recent_timestamp = max((e.event_timestamp for e in events))

    # Apply decay
    decay_factor = calculate_decay(most_recent_timestamp)
    composite_score = raw_composite * decay_factor

    # Cap at 100, floor at 0
    composite_score = max(0, min(composite_score, 100))

    # Step 6: Create/update LeadZone record

    # Determine score band
    score_band_enum = get_score_band(composite_score)
    score_band_str = score_band_enum.band_name

    # Get predicted conversion rate
    predicted_conversion = get_predicted_conversion_rate(composite_score)

    # Freeze weights
    weights_snapshot = CURRENT_MODEL_VERSION.to_snapshot()

    # Set expires_at = most_recent_timestamp + 14 days
    expires_at = most_recent_timestamp + timedelta(days=MAX_AGE_DAYS)

    # Check if zone already exists for this h3_index (and is active)
    existing_zone_stmt = select(LeadZone).where(
        LeadZone.h3_index == h3_index,
        LeadZone.active == True
    )
    existing_result = await session.execute(existing_zone_stmt)
    existing_zone = existing_result.scalar_one_or_none()

    if existing_zone:
        # Update existing zone
        existing_zone.boundary = WKTElement(boundary_wkt, srid=4326)
        existing_zone.centroid = WKTElement(centroid_wkt, srid=4326)
        existing_zone.composite_score = composite_score
        existing_zone.damage_prob = damage_prob
        existing_zone.lead_quality = lead_quality
        existing_zone.density_bonus = density_bonus
        existing_zone.predicted_conversion_rate = predicted_conversion
        existing_zone.score_band = score_band_str
        existing_zone.score_weights_snapshot = weights_snapshot
        existing_zone.model_version = CURRENT_MODEL_VERSION.version
        existing_zone.event_count = event_count
        existing_zone.max_hail_diameter = max_hail_diameter
        existing_zone.max_wind_speed = max_wind_speed
        existing_zone.primary_event_timestamp = most_recent_timestamp
        existing_zone.expires_at = expires_at

        # Mark as update for stats tracking
        existing_zone._is_new = False

        logger.debug(f"Updated zone {h3_index} with score {composite_score:.2f}")
        return existing_zone

    else:
        # Create new zone
        new_zone = LeadZone(
            boundary=WKTElement(boundary_wkt, srid=4326),
            centroid=WKTElement(centroid_wkt, srid=4326),
            h3_index=h3_index,
            composite_score=composite_score,
            damage_prob=damage_prob,
            lead_quality=lead_quality,
            density_bonus=density_bonus,
            predicted_conversion_rate=predicted_conversion,
            score_band=score_band_str,
            score_weights_snapshot=weights_snapshot,
            model_version=CURRENT_MODEL_VERSION.version,
            event_count=event_count,
            max_hail_diameter=max_hail_diameter,
            max_wind_speed=max_wind_speed,
            primary_event_timestamp=most_recent_timestamp,
            expires_at=expires_at,
            active=True,
        )

        session.add(new_zone)

        # Mark as new for stats tracking
        new_zone._is_new = True

        logger.debug(f"Created zone {h3_index} with score {composite_score:.2f}")
        return new_zone
