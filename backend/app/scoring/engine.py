"""Storm rescore engine for lead zones (RoofIQ v11).

Handles the storm-specific portion of the scoring pipeline.  It is invoked
only when new storm events arrive and is responsible for:

1. Querying unscored StormEvent rows.
2. Clustering those events to H3 hexes (resolution 7).
3. For each hex, computing storm_boost from event severity/context.
4. Upserting ONE LeadZone per hex (no lead_type duplication):
   - If the zone already has base_score (base engine ran first):
       composite = base_score * 0.80 + storm_boost * 0.20
   - If no base_score yet (storm arrives before base scoring runs):
       compute base sub-scores on-the-fly from intersecting census tracts,
       then blend with storm_boost
5. Setting has_active_storm=True and lead_type='storm_boosted'.
6. Marking processed events as scored.

This engine does NOT touch non-storm zone fields like base_scored_at or the
180-day expiry — those belong to run_base_scoring_pipeline in base_engine.py.
"""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from geoalchemy2 import WKTElement
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.lead_zone import LeadZone
from app.models.storm_event import StormEvent
from app.scoring.base_engine import compute_base_sub_scores
from app.scoring.decay import MAX_AGE_DAYS, calculate_decay
from app.scoring.spatial import (
    build_zone_boundary,
    cluster_events_to_h3,
    compute_weighted_demographics,
    get_intersecting_tracts,
)
from app.scoring.weights import (
    CURRENT_MODEL_VERSION,
    UNIFIED_MODEL_VERSION,
    get_predicted_conversion_rate,
    get_score_band,
)
from app.services.geocoding import reverse_geocode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Storm boost computation
# ---------------------------------------------------------------------------

def compute_storm_boost(
    events: list[StormEvent],
    demographics: dict,
) -> tuple[float, float, float]:
    """Compute storm_boost (0-100) from event severity and local context.

    This is what was formerly called damage_prob in the v9 engine.
    The naming change reflects that it now acts as an additive boost on top
    of base_score rather than being one of three equal composite sub-scores.

    Args:
        events:       Storm events in this H3 hex.
        demographics: Output of compute_weighted_demographics().

    Returns:
        Tuple of (storm_boost, max_hail_diameter, max_wind_speed).
    """
    max_hail_diameter = max((e.hail_diameter or 0.0 for e in events), default=0.0)
    max_wind_speed    = max((e.wind_speed    or 0.0 for e in events), default=0.0)
    event_count       = len(events)

    # Event severity score
    hail_score  = min(max_hail_diameter * 25, 100)              # 4" hail = 100
    wind_score  = min(max((max_wind_speed - 50) * 2, 0), 100)  # 100 mph = 100
    event_damage = max(hail_score, wind_score)

    # Corroboration bonus (+10)
    if any(e.corroborated for e in events):
        event_damage += 10

    # Event count bonus (up to +20)
    event_damage += min(event_count * 5, 20)

    # NRI regional risk modifier (0-15 pts)
    nri_hail_freq = demographics.get("avg_nri_hail_afreq", 0.0)
    nri_swnd_freq = demographics.get("avg_nri_swnd_afreq", 0.0)
    nri_trnd_freq = demographics.get("avg_nri_trnd_afreq", 0.0)
    nri_combined  = nri_hail_freq * 5.0 + nri_swnd_freq * 2.5 + nri_trnd_freq * 10.0
    nri_risk_bonus = min(nri_combined, 15)

    # Historical hail exposure modifier (0-15 pts)
    hail_exposure      = demographics.get("avg_hail_exposure_score", 0.0)
    hail_exposure_bonus = min(
        hail_exposure * 0.15,
        CURRENT_MODEL_VERSION.historical_exposure_weights.hail_exposure_max_bonus,
    )

    # FEMA disaster modifier (0-10 pts)
    fema_score  = demographics.get("avg_fema_disaster_score", 0.0)
    fema_bonus  = min(
        fema_score * 0.10,
        CURRENT_MODEL_VERSION.historical_exposure_weights.fema_disaster_max_bonus,
    )

    # Tree canopy modifier (0-8 pts) — high canopy amplifies storm damage
    canopy_risk   = demographics.get("avg_tree_canopy_risk_score", 0.0)
    canopy_bonus  = min(
        canopy_risk * 0.08,
        CURRENT_MODEL_VERSION.tree_canopy_weights.storm_canopy_max_bonus,
    )

    # Verified historical damage bonus (0-10 pts, log scale)
    verified_damage       = demographics.get("avg_verified_damage_5yr_usd", 0)
    verified_damage_bonus = min(
        math.log10(max(verified_damage, 1)) * 2.5,
        CURRENT_MODEL_VERSION.verified_damage_weights.verified_damage_max_bonus,
    )

    # Climate wind exposure bonus (0-5 pts)
    climate_weathering    = demographics.get("avg_climate_weathering_score", 0)
    climate_wind_bonus    = min(
        climate_weathering * 0.05,
        CURRENT_MODEL_VERSION.climate_weathering_weights.storm_climate_max_bonus,
    )

    # SVI vulnerability bonus (0-5 pts) — higher SVI = more disaster-vulnerable
    svi_overall = demographics.get("avg_svi_overall", 0)
    svi_bonus   = min(
        svi_overall * 5.0,
        CURRENT_MODEL_VERSION.svi_weights.storm_svi_max_bonus,
    )

    storm_boost = min(
        event_damage
        + nri_risk_bonus
        + hail_exposure_bonus
        + fema_bonus
        + canopy_bonus
        + verified_damage_bonus
        + climate_wind_bonus
        + svi_bonus,
        100.0,
    )

    return storm_boost, max_hail_diameter, max_wind_speed


# ---------------------------------------------------------------------------
# Single-zone update
# ---------------------------------------------------------------------------

async def score_single_zone(
    session: AsyncSession,
    h3_index: str,
    events: list[StormEvent],
) -> Optional[LeadZone]:
    """Compute storm_boost and upsert a LeadZone for one H3 hex.

    Looks up any existing active zone by h3_index (no lead_type filter).
    Preserves base_score / sub-scores when the zone was previously base-scored.
    Falls back to on-the-fly census tract scoring when base_score is absent.

    Args:
        session:  AsyncSession for database operations.
        h3_index: H3 hex index to process.
        events:   Storm events clustered into this hex.

    Returns:
        LeadZone instance if successful, None if the hex had no census tracts.
    """
    if not events:
        return None

    boundary_wkt, centroid_wkt = build_zone_boundary(h3_index)
    intersecting_tracts = await get_intersecting_tracts(session, boundary_wkt)

    if not intersecting_tracts:
        logger.warning(f"No census tracts found for storm zone {h3_index}, skipping")
        return None

    demographics = compute_weighted_demographics(intersecting_tracts)

    # --- Storm signal ---
    storm_boost, max_hail_diameter, max_wind_speed = compute_storm_boost(events, demographics)
    event_count = len(events)
    most_recent_timestamp = max(e.event_timestamp for e in events)

    # Apply temporal decay to storm_boost (older events should contribute less)
    decay_factor = calculate_decay(most_recent_timestamp)
    storm_boost_decayed = storm_boost * decay_factor
    storm_boost_decayed = max(0.0, min(storm_boost_decayed, 100.0))

    weights_snapshot = UNIFIED_MODEL_VERSION.to_snapshot()
    model_version    = UNIFIED_MODEL_VERSION.version

    score_band_enum      = get_score_band
    predicted_conversion = get_predicted_conversion_rate

    # Look up existing active zone for this hex — one zone per hex
    existing_stmt = select(LeadZone).where(
        LeadZone.h3_index == h3_index,
        LeadZone.active   == True,
    )
    existing_result = await session.execute(existing_stmt)
    existing_zone   = existing_result.scalar_one_or_none()

    current_time = datetime.now(timezone.utc)

    if existing_zone:
        # --- UPDATE path ---

        # Re-use existing base_score when available; otherwise compute on the fly
        if existing_zone.base_score is not None:
            base_score         = existing_zone.base_score
            roof_condition     = existing_zone.roof_condition
            market_quality     = existing_zone.market_quality
            risk_exposure      = existing_zone.risk_exposure
            canvass_efficiency = existing_zone.canvass_efficiency
        else:
            # Base engine hasn't run yet — compute sub-scores on the fly
            sub_scores         = compute_base_sub_scores(demographics)
            base_score         = sub_scores["base_score"]
            roof_condition     = sub_scores["roof_condition"]
            market_quality     = sub_scores["market_quality"]
            risk_exposure      = sub_scores["risk_exposure"]
            canvass_efficiency = sub_scores["canvass_efficiency"]

        composite_score = (
            base_score           * UNIFIED_MODEL_VERSION.base_weight_with_storm +
            storm_boost_decayed  * UNIFIED_MODEL_VERSION.storm_boost_weight
        )
        composite_score = max(0.0, min(composite_score, 100.0))

        sb  = get_score_band(composite_score)
        pcr = get_predicted_conversion_rate(composite_score)

        # Storm expiry: max of current expiry and 14 days from event
        storm_expires_at = most_recent_timestamp + timedelta(days=MAX_AGE_DAYS)
        new_expires_at   = max(
            existing_zone.expires_at or storm_expires_at,
            storm_expires_at,
        )

        existing_zone.composite_score           = composite_score
        existing_zone.base_score                = base_score
        existing_zone.roof_condition            = roof_condition
        existing_zone.market_quality            = market_quality
        existing_zone.risk_exposure             = risk_exposure
        existing_zone.canvass_efficiency        = canvass_efficiency
        existing_zone.storm_boost               = storm_boost_decayed
        existing_zone.has_active_storm          = True
        existing_zone.lead_type                 = "storm_boosted"
        # Backward-compat fields
        existing_zone.damage_prob               = storm_boost_decayed
        existing_zone.lead_quality              = market_quality
        existing_zone.density_bonus             = canvass_efficiency
        # Storm event metadata
        existing_zone.event_count               = event_count
        existing_zone.max_hail_diameter         = max_hail_diameter
        existing_zone.max_wind_speed            = max_wind_speed
        existing_zone.primary_event_timestamp   = most_recent_timestamp
        existing_zone.predicted_conversion_rate = pcr
        existing_zone.score_band                = sb.band_name
        existing_zone.score_weights_snapshot    = weights_snapshot
        existing_zone.model_version             = model_version
        existing_zone.expires_at                = new_expires_at
        existing_zone.updated_at                = current_time

        existing_zone._is_new = False
        logger.debug(
            f"Storm-updated zone {h3_index}: composite={composite_score:.1f} "
            f"base={base_score:.1f} boost={storm_boost_decayed:.1f}"
        )
        return existing_zone

    else:
        # --- CREATE path ---
        # Compute base sub-scores on the fly (base engine hasn't run yet)
        sub_scores         = compute_base_sub_scores(demographics)
        base_score         = sub_scores["base_score"]
        roof_condition     = sub_scores["roof_condition"]
        market_quality     = sub_scores["market_quality"]
        risk_exposure      = sub_scores["risk_exposure"]
        canvass_efficiency = sub_scores["canvass_efficiency"]

        composite_score = (
            base_score          * UNIFIED_MODEL_VERSION.base_weight_with_storm +
            storm_boost_decayed * UNIFIED_MODEL_VERSION.storm_boost_weight
        )
        composite_score = max(0.0, min(composite_score, 100.0))

        sb  = get_score_band(composite_score)
        pcr = get_predicted_conversion_rate(composite_score)

        expires_at = most_recent_timestamp + timedelta(days=MAX_AGE_DAYS)

        # Geocode display name for new zones
        display_name = None
        if settings.MAPBOX_TOKEN:
            try:
                from shapely import wkt as shapely_wkt
                centroid_geom = shapely_wkt.loads(centroid_wkt)
                display_name  = reverse_geocode(
                    lon=centroid_geom.x,
                    lat=centroid_geom.y,
                    mapbox_token=settings.MAPBOX_TOKEN,
                )
            except Exception as e:
                logger.warning(f"Failed to geocode storm zone {h3_index}: {e}")

        new_zone = LeadZone(
            boundary=WKTElement(boundary_wkt, srid=4326),
            centroid=WKTElement(centroid_wkt, srid=4326),
            h3_index=h3_index,
            display_name=display_name,
            lead_type="storm_boosted",
            composite_score=composite_score,
            base_score=base_score,
            roof_condition=roof_condition,
            market_quality=market_quality,
            risk_exposure=risk_exposure,
            canvass_efficiency=canvass_efficiency,
            storm_boost=storm_boost_decayed,
            has_active_storm=True,
            # Backward-compat fields
            damage_prob=storm_boost_decayed,
            lead_quality=market_quality,
            density_bonus=canvass_efficiency,
            predicted_conversion_rate=pcr,
            score_band=sb.band_name,
            score_weights_snapshot=weights_snapshot,
            model_version=model_version,
            event_count=event_count,
            max_hail_diameter=max_hail_diameter,
            max_wind_speed=max_wind_speed,
            primary_event_timestamp=most_recent_timestamp,
            base_scored_at=None,  # Will be set when base engine runs
            expires_at=expires_at,
            active=True,
        )

        session.add(new_zone)
        new_zone._is_new = True

        logger.debug(
            f"Storm-created zone {h3_index}: composite={composite_score:.1f} "
            f"base={base_score:.1f} boost={storm_boost_decayed:.1f}"
        )
        return new_zone


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

async def run_storm_rescore_pipeline(session: AsyncSession) -> dict:
    """Process unscored storm events and upsert LeadZone records.

    Steps:
    1. Query StormEvent rows where scored=False.
    2. Cluster events to H3 hexes.
    3. For each hex: compute storm_boost, upsert LeadZone.
    4. Mark processed events as scored=True.

    Args:
        session: AsyncSession for database operations.

    Returns:
        Stats dict with keys:
            events_processed, zones_created, zones_updated, errors, zone_ids
    """
    stats: dict = {
        "events_processed": 0,
        "zones_created":    0,
        "zones_updated":    0,
        "errors":           0,
        "zone_ids":         [],
    }

    logger.info("Starting storm rescore pipeline")

    # Step 1: Query unscored events
    stmt   = select(StormEvent).where(StormEvent.scored == False)
    result = await session.execute(stmt)
    unscored_events = list(result.scalars().all())

    if not unscored_events:
        logger.info("No unscored storm events found")
        return stats

    logger.info(f"Found {len(unscored_events)} unscored storm events")

    # Step 2: Cluster to H3
    clustered_events = cluster_events_to_h3(unscored_events, resolution=7)
    logger.info(f"Clustered into {len(clustered_events)} H3 hexes")

    # Step 3: Score each hex
    processed_event_ids: list = []

    for h3_index, events in clustered_events.items():
        try:
            zone = await score_single_zone(session, h3_index, events)

            if zone is not None:
                processed_event_ids.extend([e.id for e in events])
                stats["zone_ids"].append(zone.id)

                if getattr(zone, "_is_new", False):
                    stats["zones_created"] += 1
                else:
                    stats["zones_updated"] += 1

        except Exception as e:
            logger.error(f"Error scoring storm zone {h3_index}: {e}", exc_info=True)
            stats["errors"] += 1

    # Step 4: Mark events as scored
    if processed_event_ids:
        update_stmt = (
            update(StormEvent)
            .where(StormEvent.id.in_(processed_event_ids))
            .values(scored=True)
        )
        await session.execute(update_stmt)
        await session.commit()

        stats["events_processed"] = len(processed_event_ids)
        logger.info(f"Marked {len(processed_event_ids)} storm events as scored")

    logger.info(
        f"Storm rescore pipeline complete: {stats['events_processed']} events, "
        f"{stats['zones_created']} created, {stats['zones_updated']} updated, "
        f"{stats['errors']} errors"
    )

    return stats


# ---------------------------------------------------------------------------
# Backward-compat alias
# ---------------------------------------------------------------------------

#: Alias kept so any existing call-sites importing run_scoring_pipeline
#: continue to work without modification while the rename propagates.
run_scoring_pipeline = run_storm_rescore_pipeline
