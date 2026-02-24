"""Base scoring engine for unified roofing lead intelligence (RoofIQ v11).

Scores ALL census tracts in Georgia (state_fips='13') regardless of roof age,
producing one LeadZone per H3 hex with four orthogonal sub-scores:

    roof_condition     -- roof degradation likelihood
    market_quality     -- financial attractiveness of the area
    risk_exposure      -- environmental / storm damage vulnerability
    canvass_efficiency -- how productive a canvassing run will be

A single base_score is derived from those four sub-scores and re-normalized
across all zones with a sigmoid stretch so scores fill the full 0-100 range.

If a zone already carries an active storm boost (has_active_storm=True), the
final composite blends base_score * 0.80 + storm_boost * 0.20 so the storm
signal is preserved while the richer base model enriches the zone.

This engine intentionally does NOT touch storm event records or the scored
flag on StormEvent rows — that is the responsibility of run_storm_rescore_pipeline
in engine.py.
"""

import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.census_tract import CensusTract
from app.models.lead_zone import LeadZone
from app.scoring.spatial import (
    build_zone_boundary,
    compute_weighted_demographics,
    point_to_h3,
    polygon_to_h3_cells,
)
from app.scoring.weights import (
    UNIFIED_MODEL_VERSION,
    get_predicted_conversion_rate,
    get_score_band,
    renormalize_scores,
)
from app.services.geocoding import reverse_geocode

logger = logging.getLogger(__name__)

# Expiration horizon for base-scored zones (no storm expiry pressure)
BASE_SCORE_TTL_DAYS = 180


# ---------------------------------------------------------------------------
# Sub-score computation
# ---------------------------------------------------------------------------

def _weighted_pctile_sum(
    demographics: dict[str, Any],
    weights: dict[str, float],
) -> float:
    """Return a weighted sum of percentile values from compute_weighted_demographics().

    Any feature key not present in demographics defaults to the neutral
    percentile (50.0), which keeps missing data from unfairly penalising a zone.

    Args:
        demographics: Output of compute_weighted_demographics()
        weights:      Dict mapping feature name -> weight (no pctile_ prefix).
                      Weights are expected to sum to 1.0.

    Returns:
        Weighted sum clamped to [0, 100].
    """
    score = 0.0
    for feature, weight in weights.items():
        pctile = demographics.get(f"pctile_{feature}", 50.0)
        score += pctile * weight
    return max(0.0, min(score, 100.0))


def compute_base_sub_scores(demographics: dict[str, Any]) -> dict[str, float]:
    """Compute the four sub-scores and base_score for a single H3 hex.

    Uses UNIFIED_MODEL_VERSION weight dicts so the formula is always
    consistent with what is stored in score_weights_snapshot.

    Args:
        demographics: Output of compute_weighted_demographics()

    Returns:
        Dictionary with keys:
            roof_condition, market_quality, risk_exposure, canvass_efficiency,
            base_score (raw, before sigmoid normalization)
    """
    cw = UNIFIED_MODEL_VERSION.composite_weights

    roof_condition = _weighted_pctile_sum(
        demographics,
        UNIFIED_MODEL_VERSION.roof_condition_weights.weights,
    )
    market_quality = _weighted_pctile_sum(
        demographics,
        UNIFIED_MODEL_VERSION.market_quality_weights.weights,
    )
    risk_exposure = _weighted_pctile_sum(
        demographics,
        UNIFIED_MODEL_VERSION.risk_exposure_weights.weights,
    )
    canvass_efficiency = _weighted_pctile_sum(
        demographics,
        UNIFIED_MODEL_VERSION.canvass_efficiency_weights.weights,
    )

    base_score = (
        roof_condition    * cw.roof_condition    +
        market_quality    * cw.market_quality    +
        risk_exposure     * cw.risk_exposure     +
        canvass_efficiency * cw.canvass_efficiency
    )
    base_score = max(0.0, min(base_score, 100.0))

    return {
        "roof_condition":     roof_condition,
        "market_quality":     market_quality,
        "risk_exposure":      risk_exposure,
        "canvass_efficiency": canvass_efficiency,
        "base_score":         base_score,
    }


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

async def run_base_scoring_pipeline(session: AsyncSession, skip_geocoding: bool = False) -> dict:
    """Score all census tracts in Georgia and upsert one LeadZone per H3 hex.

    Two-pass approach mirrors roof_age_engine.py:
      Pass 1 — compute raw sub-scores and raw base_score for every hex.
      Pass 2 — sigmoid-normalize base_score across the full zone set, then
               write/update LeadZone rows in batches of 500.

    Zones that already have has_active_storm=True retain their storm fields;
    the composite is re-blended: base_score * 0.80 + storm_boost * 0.20.

    Args:
        session: AsyncSession for database operations
        skip_geocoding: Skip Mapbox reverse geocoding for new zones (for bulk runs)

    Returns:
        Stats dict with keys:
            tracts_processed, zones_created, zones_updated,
            total_scored, errors
    """
    stats: dict[str, int] = {
        "tracts_processed": 0,
        "zones_created":    0,
        "zones_updated":    0,
        "total_scored":     0,
        "errors":           0,
    }

    # ------------------------------------------------------------------
    # Query ALL census tracts in Georgia — no year-built filter
    # ------------------------------------------------------------------
    stmt = select(CensusTract).where(
        CensusTract.state_fips == "13",
    )
    result = await session.execute(stmt)
    tracts = list(result.scalars().all())

    if not tracts:
        logger.warning("No Georgia census tracts found — base scoring pipeline returning empty")
        return stats

    stats["tracts_processed"] = len(tracts)
    logger.info(f"Base scoring: loaded {len(tracts)} Georgia census tracts")

    # ------------------------------------------------------------------
    # Group tracts by H3 hex (resolution 7)
    # ------------------------------------------------------------------
    h3_to_tracts: dict[str, list[CensusTract]] = {}

    for tract in tracts:
        if not tract.geometry:
            continue
        try:
            geom = to_shape(tract.geometry)
            hex_cells = polygon_to_h3_cells(geom, resolution=7)
            for h3_index in hex_cells:
                if h3_index not in h3_to_tracts:
                    h3_to_tracts[h3_index] = []
                h3_to_tracts[h3_index].append(tract)
        except Exception:
            stats["errors"] += 1

    total_hexes = len(h3_to_tracts)
    logger.info(f"Pass 1: computing raw sub-scores for {total_hexes} H3 hexes")

    # ------------------------------------------------------------------
    # Pass 1: raw sub-scores + zone geometry for every hex
    # zone_results: list of (h3_index, boundary_wkt, centroid_wkt, sub_scores)
    # ------------------------------------------------------------------
    zone_results: list[tuple[str, str, str, dict[str, float]]] = []

    for idx, (h3_index, tract_group) in enumerate(h3_to_tracts.items()):
        if idx % 500 == 0:
            logger.info(f"  Scoring hex {idx + 1}/{total_hexes}...")

        try:
            boundary_wkt, centroid_wkt = build_zone_boundary(h3_index)
            demographics = compute_weighted_demographics(tract_group)

            sub_scores = compute_base_sub_scores(demographics)
            zone_results.append((h3_index, boundary_wkt, centroid_wkt, sub_scores))

        except Exception as e:
            logger.error(f"Error scoring hex {h3_index}: {e}")
            stats["errors"] += 1

    # ------------------------------------------------------------------
    # Sigmoid normalization of base_score across all zones
    # ------------------------------------------------------------------
    raw_base_scores = [r[3]["base_score"] for r in zone_results]

    if raw_base_scores:
        raw_avg = statistics.mean(raw_base_scores)
        raw_std = statistics.stdev(raw_base_scores) if len(raw_base_scores) > 1 else 0.0
        logger.info(
            f"Raw base_score: n={len(raw_base_scores)} avg={raw_avg:.1f} "
            f"std={raw_std:.1f} min={min(raw_base_scores):.1f} max={max(raw_base_scores):.1f}"
        )

    normalized_base_scores = renormalize_scores(raw_base_scores)

    if normalized_base_scores:
        norm_avg = statistics.mean(normalized_base_scores)
        norm_std = statistics.stdev(normalized_base_scores) if len(normalized_base_scores) > 1 else 0.0
        logger.info(
            f"Normalized base_score: n={len(normalized_base_scores)} avg={norm_avg:.1f} "
            f"std={norm_std:.1f} min={min(normalized_base_scores):.1f} max={max(normalized_base_scores):.1f}"
        )

    # ------------------------------------------------------------------
    # Pass 2: write zones with normalized base_score
    # ------------------------------------------------------------------
    current_time = datetime.now(timezone.utc)
    expires_at = current_time + timedelta(days=BASE_SCORE_TTL_DAYS)
    weights_snapshot = UNIFIED_MODEL_VERSION.to_snapshot()
    model_version = UNIFIED_MODEL_VERSION.version

    logger.info(f"Pass 2: writing {len(zone_results)} zones with normalized scores...")

    band_counts = {"hot": 0, "warm": 0, "cool": 0, "skip": 0}

    for idx, ((h3_index, boundary_wkt, centroid_wkt, sub_scores), norm_base) in enumerate(
        zip(zone_results, normalized_base_scores)
    ):
        try:
            # Look up any existing active zone for this hex (one zone per hex)
            existing_stmt = select(LeadZone).where(
                LeadZone.h3_index == h3_index,
                LeadZone.active == True,
            )
            existing_result = await session.execute(existing_stmt)
            existing_zone = existing_result.scalar_one_or_none()

            # Determine composite_score — preserve storm boost when present
            if existing_zone and existing_zone.has_active_storm and existing_zone.storm_boost is not None:
                composite_score = (
                    norm_base * UNIFIED_MODEL_VERSION.base_weight_with_storm +
                    existing_zone.storm_boost * UNIFIED_MODEL_VERSION.storm_boost_weight
                )
                composite_score = max(0.0, min(composite_score, 100.0))
                lead_type = "storm_boosted"
            else:
                composite_score = norm_base
                lead_type = "standard"

            score_band = get_score_band(composite_score)
            predicted_conversion = get_predicted_conversion_rate(composite_score)
            band_counts[score_band.band_name] += 1

            # Backward-compat fields derived from new sub-score names:
            #   damage_prob    <- storm_boost (or 0 when no storm)
            #   lead_quality   <- market_quality
            #   density_bonus  <- canvass_efficiency
            storm_boost_val = existing_zone.storm_boost if (existing_zone and existing_zone.storm_boost is not None) else None
            damage_prob_compat = storm_boost_val if storm_boost_val is not None else 0.0
            lead_quality_compat = sub_scores["market_quality"]
            density_bonus_compat = sub_scores["canvass_efficiency"]

            if existing_zone:
                # UPDATE path — preserve all storm-related fields, refresh base scores
                existing_zone.composite_score      = composite_score
                existing_zone.base_score           = norm_base
                existing_zone.roof_condition       = sub_scores["roof_condition"]
                existing_zone.market_quality       = sub_scores["market_quality"]
                existing_zone.risk_exposure        = sub_scores["risk_exposure"]
                existing_zone.canvass_efficiency   = sub_scores["canvass_efficiency"]
                existing_zone.damage_prob          = damage_prob_compat
                existing_zone.lead_quality         = lead_quality_compat
                existing_zone.density_bonus        = density_bonus_compat
                existing_zone.lead_type            = lead_type
                existing_zone.predicted_conversion_rate = predicted_conversion
                existing_zone.score_band           = score_band.band_name
                existing_zone.score_weights_snapshot = weights_snapshot
                existing_zone.model_version        = model_version
                existing_zone.base_scored_at       = current_time
                existing_zone.expires_at           = expires_at
                existing_zone.active               = True
                existing_zone.updated_at           = current_time
                stats["zones_updated"] += 1

            else:
                # CREATE path — geocode display name for new zones
                display_name = None
                if settings.MAPBOX_TOKEN and not skip_geocoding:
                    try:
                        from shapely import wkt as shapely_wkt
                        centroid_geom = shapely_wkt.loads(centroid_wkt)
                        display_name = reverse_geocode(
                            lon=centroid_geom.x,
                            lat=centroid_geom.y,
                            mapbox_token=settings.MAPBOX_TOKEN,
                        )
                    except Exception:
                        pass  # Non-critical; backfill handles existing zones

                new_zone = LeadZone(
                    boundary=WKTElement(boundary_wkt, srid=4326),
                    centroid=WKTElement(centroid_wkt, srid=4326),
                    h3_index=h3_index,
                    display_name=display_name,
                    lead_type=lead_type,
                    composite_score=composite_score,
                    base_score=norm_base,
                    roof_condition=sub_scores["roof_condition"],
                    market_quality=sub_scores["market_quality"],
                    risk_exposure=sub_scores["risk_exposure"],
                    canvass_efficiency=sub_scores["canvass_efficiency"],
                    # Storm fields are None/False for brand-new base-only zones
                    storm_boost=None,
                    has_active_storm=False,
                    # Backward-compat columns
                    damage_prob=damage_prob_compat,
                    lead_quality=lead_quality_compat,
                    density_bonus=density_bonus_compat,
                    predicted_conversion_rate=predicted_conversion,
                    score_band=score_band.band_name,
                    score_weights_snapshot=weights_snapshot,
                    model_version=model_version,
                    event_count=0,
                    max_hail_diameter=None,
                    max_wind_speed=None,
                    primary_event_timestamp=None,
                    base_scored_at=current_time,
                    expires_at=expires_at,
                    active=True,
                )
                session.add(new_zone)
                stats["zones_created"] += 1

        except Exception as e:
            logger.error(f"Error writing hex {h3_index}: {e}")
            stats["errors"] += 1
            continue

        # Batch commit every 500 zones to bound memory usage
        if (idx + 1) % 500 == 0:
            await session.commit()
            logger.info(f"  Committed {idx + 1}/{len(zone_results)} zones...")

    await session.commit()

    stats["total_scored"] = stats["zones_created"] + stats["zones_updated"]

    logger.info(
        f"Base scoring pipeline complete: {stats['zones_created']} created, "
        f"{stats['zones_updated']} updated, {stats['errors']} errors"
    )
    logger.info(
        f"Band distribution: hot={band_counts['hot']} warm={band_counts['warm']} "
        f"cool={band_counts['cool']} skip={band_counts['skip']}"
    )

    return stats
