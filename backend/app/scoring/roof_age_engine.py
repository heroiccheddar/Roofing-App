"""Roof age scoring engine.

Generates lead zones from census tract housing age data without requiring
storm events. Identifies neighborhoods with aging roofs likely to need replacement.

This is a separate lead type ('roof_age') with longer expiration (180 days)
and different scoring weights focused on roof age as the primary signal.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from shapely.geometry import Point

from app.models.census_tract import CensusTract
from app.models.lead_zone import LeadZone
from app.scoring.spatial import (
    build_zone_boundary,
    compute_weighted_demographics,
    point_to_h3,
)

logger = logging.getLogger(__name__)
from app.scoring.weights import (
    ROOF_AGE_MODEL_VERSION,
    get_score_band,
    get_predicted_conversion_rate,
)


def compute_roof_age_score(
    demographics: dict[str, Any],
    current_year: int = None,
) -> dict[str, float]:
    """Compute roof age lead score using percentile-normalized demographics.

    Uses pre-computed percentile ranks (0-100) for each feature, combined
    with domain-specific weights to produce a composite score that naturally
    spans the full 0-100 range.

    Args:
        demographics: Output from compute_weighted_demographics()
        current_year: Unused, kept for API compatibility

    Returns:
        Dictionary with composite_score and compatibility fields
    """
    # Percentile feature weights (sum = 1.0)
    # Each pctile_* value is 0-100 within the state
    weights = {
        "roof_age":           0.22,
        "pre1980_housing":    0.08,
        "owner_occupied":     0.10,
        "home_value":         0.08,
        "income":             0.09,
        "low_cost_burden":    0.07,
        "density":            0.06,
        "single_family":      0.04,
        "climate_weathering": 0.06,
        "canopy_risk":        0.04,
        "fema_risk":          0.03,
        "age_clustering":     0.04,
        "hpi_appreciation":   0.03,
        "svi_vulnerability":  0.02,
        "market_activity":    0.04,
    }

    # Weighted sum of percentile values (default 50.0 = neutral)
    composite_score = 0.0
    for feature, weight in weights.items():
        pctile = demographics.get(f"pctile_{feature}", 50.0)
        composite_score += pctile * weight

    composite_score = max(0.0, min(composite_score, 100.0))

    return {
        "roof_age_score": demographics.get("pctile_roof_age", 50.0),
        "owner_score": demographics.get("pctile_owner_occupied", 50.0),
        "value_score": demographics.get("pctile_home_value", 50.0),
        "density_score": demographics.get("pctile_density", 50.0),
        "composite_score": composite_score,
        # Compatibility fields for LeadZone model
        "lead_quality": composite_score,
        "damage_prob": 0.0,
        "density_bonus": demographics.get("pctile_density", 50.0),
    }


async def run_roof_age_pipeline(
    session: AsyncSession,
    max_year_built: int = 2001,
) -> dict[str, int]:
    """Generate roof-age lead zones from census tract data.

    Identifies census tracts with aging housing stock and creates
    lead zones for areas likely to need roof replacement.

    Process:
    1. Query census tracts where median_year_built <= max_year_built
    2. Convert tract centroids to H3 hexagons (resolution 7)
    3. Group tracts by H3 hex
    4. Compute weighted demographics for each hex
    5. Score each hex based on roof age and demographics
    6. Create/update LeadZone records with lead_type='roof_age'

    Args:
        session: AsyncSession for database operations
        max_year_built: Maximum median year built (default: 2001, houses 25+ years old)

    Returns:
        Dictionary with pipeline statistics:
        - tracts_processed: Number of census tracts evaluated
        - zones_created: Number of new lead zones created
        - zones_updated: Number of existing zones updated
        - errors: Number of errors encountered
    """
    stats = {
        "tracts_processed": 0,
        "zones_created": 0,
        "zones_updated": 0,
        "errors": 0,
    }

    # Query census tracts with median_year_built <= max_year_built
    stmt = select(CensusTract).where(
        CensusTract.median_year_built.isnot(None),
        CensusTract.median_year_built <= max_year_built,
    )
    result = await session.execute(stmt)
    tracts = list(result.scalars().all())

    if not tracts:
        return stats

    stats["tracts_processed"] = len(tracts)

    # Group tracts by H3 hex
    h3_to_tracts: dict[str, list[CensusTract]] = {}

    for tract in tracts:
        if not tract.geometry:
            continue

        try:
            # Extract centroid from geometry
            geom = to_shape(tract.geometry)
            centroid = geom.centroid

            # Convert to H3
            h3_index = point_to_h3(centroid.y, centroid.x, resolution=7)

            # Group by H3
            if h3_index not in h3_to_tracts:
                h3_to_tracts[h3_index] = []
            h3_to_tracts[h3_index].append(tract)

        except Exception as e:
            stats["errors"] += 1
            continue

    # Process each H3 hex
    current_time = datetime.now(timezone.utc)
    expires_at = current_time + timedelta(days=180)  # 180-day expiration
    total_hexes = len(h3_to_tracts)
    logger.info(f"Processing {total_hexes} H3 hexes from {stats['tracts_processed']} tracts")

    for idx, (h3_index, tract_group) in enumerate(h3_to_tracts.items()):
        if idx % 50 == 0:
            logger.info(f"  Processing hex {idx + 1}/{total_hexes}...")

        try:
            # Build H3 boundary geometry
            boundary_wkt, centroid_wkt = build_zone_boundary(h3_index)

            # Use pre-grouped tracts directly (avoids expensive per-hex spatial queries)
            demographics = compute_weighted_demographics(tract_group)

            # Skip if no meaningful year built data
            if demographics["avg_median_year_built"] == 0:
                continue

            # Compute roof age score
            scores = compute_roof_age_score(demographics)

            # Get score band and predicted conversion
            score_band = get_score_band(scores["composite_score"])
            predicted_conversion = get_predicted_conversion_rate(scores["composite_score"])

            # Check if zone already exists
            existing_zone_stmt = select(LeadZone).where(
                LeadZone.h3_index == h3_index,
                LeadZone.lead_type == "roof_age",
            )
            existing_result = await session.execute(existing_zone_stmt)
            existing_zone = existing_result.scalar_one_or_none()

            if existing_zone:
                # Update existing zone
                existing_zone.composite_score = scores["composite_score"]
                existing_zone.damage_prob = scores["damage_prob"]
                existing_zone.lead_quality = scores["lead_quality"]
                existing_zone.density_bonus = scores["density_bonus"]
                existing_zone.predicted_conversion_rate = predicted_conversion
                existing_zone.score_band = score_band.band_name
                existing_zone.score_weights_snapshot = ROOF_AGE_MODEL_VERSION.to_snapshot()
                existing_zone.model_version = ROOF_AGE_MODEL_VERSION.version
                existing_zone.expires_at = expires_at
                existing_zone.active = True
                existing_zone.updated_at = current_time

                stats["zones_updated"] += 1

            else:
                # Create new zone
                new_zone = LeadZone(
                    boundary=WKTElement(boundary_wkt, srid=4326),
                    centroid=WKTElement(centroid_wkt, srid=4326),
                    h3_index=h3_index,
                    lead_type="roof_age",
                    composite_score=scores["composite_score"],
                    damage_prob=scores["damage_prob"],
                    lead_quality=scores["lead_quality"],
                    density_bonus=scores["density_bonus"],
                    predicted_conversion_rate=predicted_conversion,
                    score_band=score_band.band_name,
                    score_weights_snapshot=ROOF_AGE_MODEL_VERSION.to_snapshot(),
                    model_version=ROOF_AGE_MODEL_VERSION.version,
                    event_count=0,
                    max_hail_diameter=None,
                    max_wind_speed=None,
                    primary_event_timestamp=None,
                    expires_at=expires_at,
                    active=True,
                )

                session.add(new_zone)
                stats["zones_created"] += 1

        except Exception as e:
            logger.error(f"Error processing hex {h3_index}: {e}")
            stats["errors"] += 1
            continue

        # Batch commit every 50 hexes
        if (idx + 1) % 50 == 0:
            await session.commit()

    # Final commit
    await session.commit()
    logger.info(
        f"Roof age pipeline complete: {stats['zones_created']} created, "
        f"{stats['zones_updated']} updated, {stats['errors']} errors"
    )

    return stats
